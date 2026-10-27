import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / 'scripts/workspace_profiles.py'

class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def call(self, *args):
        return subprocess.run(['python3', str(BACKEND), *args], capture_output=True, text=True)

    def load(self):
        result = self.call('load', str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_legacy_read_normalizes_safety_without_writing_or_autostart(self):
        (self.root / 'presets.json').write_text('[{"name":"Work","windows":[]}]')
        legacy = '[{"name":"Daily","default":true,"closeMode":"workspaceAll","workspaces":[{"workspace":23,"preset":"Work"}]}]'
        (self.root / 'profiles.json').write_text(legacy)
        snapshot = self.load()
        profile = snapshot['data']['profiles'][0]
        self.assertFalse(profile['default'])
        self.assertEqual(profile['closeMode'], 'keepExisting')
        self.assertEqual((self.root / 'profiles.json').read_text(), legacy)
        self.assertFalse((self.root / 'state.json').exists())

    def test_corrupt_existing_file_blocks_load_and_save_preserves_bytes(self):
        destination = self.root / 'presets.json'
        for invalid in ['{', '{}', '[null]', '[{"name":"X","windows":[{"type":"custom","value":""}]}]', '[{"name":"X","windows":[],"notes":NaN}]']:
            with self.subTest(invalid=invalid):
                destination.write_text(invalid)
                loaded = self.call('load', str(self.root))
                self.assertNotEqual(loaded.returncode, 0)
                self.assertIn('presets.json', loaded.stderr)
                saved = self.call('save', str(self.root), 'bad-revision', json.dumps({'version':1, 'presets':[], 'profiles':[], 'shortcuts':[]}))
                self.assertNotEqual(saved.returncode, 0)
                self.assertEqual(destination.read_text(), invalid)
                self.assertFalse((self.root / 'state.json').exists())

    def test_atomic_save_normalizes_and_rejects_stale_external_snapshot(self):
        first = self.load()
        data = first['data']
        data['presets'].append({'name':'Work', 'windows':[]})
        data['profiles'].append({'name':'Daily', 'default':True, 'closeMode':'workspaceAll', 'workspaces':[]})
        result = self.call('save', str(self.root), first['revision'], json.dumps(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(saved, self.load())
        self.assertEqual(saved['data']['profiles'][0]['closeMode'], 'keepExisting')
        self.assertFalse(saved['data']['profiles'][0]['default'])
        self.assertNotEqual(saved['revision'], first['revision'])
        stale = self.call('save', str(self.root), first['revision'], json.dumps(first['data']))
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn('changed', stale.stderr)
        self.assertEqual(self.load(), saved)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['state.json', 'state.lock'])

    def test_invalid_references_duplicates_and_slots_are_not_persisted(self):
        first = self.load()
        invalids = [
            {'presets':[{'name':'A','windows':[]},{'name':' a ','windows':[]}]},
            {'profiles':[{'name':'P','workspaces':[{'workspace':1,'preset':'Missing'}]}]},
            {'shortcuts':[{'family':'preset','slot':10,'name':'Missing'}]},
            {'presets':[{'name':'A','windows':[{'type':'custom','value':'x','matchClass': ['bad']}]}]}
        ]
        for invalid in invalids:
            data = dict(first['data'], **invalid)
            result = self.call('save', str(self.root), first['revision'], json.dumps(data))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Unknown action', result.stderr)
            self.assertFalse((self.root / 'state.json').exists())

    def test_concurrent_writers_allow_one_revision_without_lost_update(self):
        initial = self.load()
        children = []
        for name in ('First', 'Second'):
            data = dict(initial['data'], presets=[{'name':name,'windows':[]}])
            children.append(subprocess.Popen(['python3',str(BACKEND),'save',str(self.root),initial['revision'],json.dumps(data)],
                                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
        results = [(p.communicate(timeout=5), p.returncode) for p in children]
        self.assertEqual(sorted(code for _,code in results), [0,1])
        winner = next(json.loads(streams[0]) for streams,code in results if code == 0)
        self.assertEqual(self.load(), winner)
        self.assertIn('changed', next(streams[1] for streams,code in results if code != 0))

    def test_large_drafts_can_be_saved_over_stdin_without_argv_limits(self):
        first = self.load()
        data = dict(first['data'], notes='x' * 150000)
        result = subprocess.run(['python3',str(BACKEND),'save',str(self.root),first['revision'],'-'],
                                input=json.dumps(data)+'\n',capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['notes'],data['notes'])

    def test_non_json_values_and_oversized_formatted_state_do_not_replace_snapshot(self):
        initial = self.load()
        for data in [dict(initial['data'], notes=float('nan')), dict(initial['data'], notes='x' * (2*1024*1024-80))]:
            result = subprocess.run(['python3',str(BACKEND),'save',str(self.root),initial['revision'],'-'],
                                    input=json.dumps(data)+'\n',capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((self.root/'state.json').exists())
            self.assertEqual(self.load(),initial)

if __name__ == '__main__':
    unittest.main()
