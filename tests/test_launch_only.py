"""Real helpers, fake compositor; run ONLY via tests/isolated.sh."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]

class LaunchOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.clients = self.root / 'clients.json'
        self.log = self.root / 'calls.jsonl'
        self.clients.write_text(json.dumps({'workspace': 1, 'clients': [
            {'address': '0xaa', 'pid': 1, 'initialClass': 'editor', 'workspace': {'id': 1}}]}))
        self.log.write_text('')
        envfile = self.root / 'env.sh'
        envfile.write_text(f'hyprctl() {{ node {REPO}/tests/fake-hyprctl.cjs "$@"; }}\nexport -f hyprctl\n')
        bindir = self.root / 'bin'
        bindir.mkdir()
        fake = bindir / 'hyprctl'
        fake.write_text(f'#!/bin/bash\nexec node {REPO}/tests/fake-hyprctl.cjs "$@"\n')
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'], BASH_ENV=str(envfile), TEST_CLIENTS=str(self.clients),
                        TEST_LOG=str(self.log), HYPRLAND_INSTANCE_SIGNATURE='fake')

    def activate(self, mode='workspaceAll', workspaces=None):
        plan = {'name': 'Test', 'timeoutSeconds': 0.15, 'closeMode': mode, 'workspaces': workspaces or [
            {'workspace': 1, 'preset': 'Empty', 'commands': []}]}
        return subprocess.run(['bash', str(REPO / 'scripts/activate-profile.sh'), str(self.state), json.dumps(plan)],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_legacy_close_modes_never_close_change_layout_or_infer_ownership(self):
        for mode in ['workspaceAll', 'trackedOnly', 'keepExisting']:
            with self.subTest(mode=mode):
                # Unreadable legacy ownership must be irrelevant forever.
                old = self.state / 'active-profile.json'
                old.write_text('not JSON')
                before = self.clients.read_text()
                result = self.activate(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.clients.read_text(), before)
                self.assertEqual(old.read_text(), 'not JSON')
                calls = self.log.read_text()
                self.assertNotIn('close', calls)
                self.assertNotIn('keyword', calls)
                self.assertNotIn('kill', calls)

    def test_invalid_later_step_rejected_before_any_compositor_calls(self):
        result = self.activate(workspaces=[{'workspace': 1, 'preset': 'ok', 'commands': []},
                                          {'workspace': -2, 'preset': 'bad', 'commands': []}])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_existing_exact_class_on_target_is_not_relaunched(self):
        result = self.activate(workspaces=[{'workspace': 1, 'preset': 'Existing', 'commands': [
            {'command': 'never execute this', 'matchClass': 'editor'}]}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), '')

    def test_existing_class_elsewhere_reports_location_without_launch(self):
        result = self.activate(workspaces=[{'workspace': 23, 'preset': 'Existing', 'commands': [
            {'command': 'never execute this', 'matchClass': 'editor'}]}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workspace 1', result.stderr)
        self.assertEqual(self.log.read_text(), '')

    def test_launch_uses_explicit_workspace_preserves_layout_and_no_ownership(self):
        for entry in ['fake-launch', {'command': 'fake-launch', 'matchClass': 'new-app'}]:
            self.clients.write_text(json.dumps({'workspace': 9, 'clients': []}))
            self.log.write_text('')
            result = self.activate(workspaces=[{'workspace': 23, 'preset': 'New', 'commands': [entry]}])
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in self.log.read_text().splitlines()]
            self.assertEqual(len(calls), 1)
            self.assertIn('[workspace 23 silent]', calls[0][1])
            self.assertIn('hl.dsp.exec_cmd', calls[0][1])
            self.assertFalse((self.state / 'active-profile.json').exists())

    def test_timeout_stops_following_launches_and_writes_failed_progress(self):
        self.env['TEST_NO_WINDOW'] = '1'
        result = self.activate(workspaces=[{'workspace': 23, 'preset': 'New', 'commands': ['first', 'second']}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Timed out', result.stderr)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.assertEqual(json.loads((self.state / 'activation-progress.json').read_text())[0]['status'], 'failed')

    def test_unrelated_class_does_not_confirm_matched_launch(self):
        self.env['TEST_NEW_CLASS'] = 'unrelated'
        result = self.activate(workspaces=[{'workspace': 23, 'preset': 'New', 'commands': [
            {'command': 'fake-launch', 'matchClass': 'expected'}]}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Timed out', result.stderr)
        self.assertFalse((self.state / 'active-profile.json').exists())

    def test_ambiguous_arrivals_without_match_fail_conservatively(self):
        self.env['TEST_EXTRA_WINDOW'] = '1'
        result = self.activate(workspaces=[{'workspace': 23, 'preset': 'New', 'commands': ['fake-launch']}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ambiguous', result.stderr)

    def test_saved_profile_and_preset_use_same_launch_coordinator_with_duplicate_entries(self):
        data = {'version':1, 'presets':[{'name':'Twice', 'windows':[
            {'type':'custom','value':'fake-launch'}, {'type':'custom','value':'fake-launch'}]}],
            'profiles':[{'name':'Daily','default':True,'closeMode':'workspaceAll','workspaces':[{'workspace':25,'preset':'Twice'}]}], 'shortcuts':[]}
        (self.state / 'state.json').write_text(json.dumps(data))
        backend = str(REPO / 'scripts/workspace_profiles.py')
        loaded = subprocess.run(['python3',backend,'load',str(self.state)],capture_output=True,text=True,env=self.env)
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        revision = json.loads(loaded.stdout)['revision']
        for family, name in [('profile','Daily'),('preset','Twice')]:
            self.log.write_text('')
            request = {'family':family,'name':name,'workspace':25,'revision':revision}
            result = subprocess.run(['python3',backend,'run',str(self.state),json.dumps(request)],capture_output=True,text=True,env=self.env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(self.log.read_text().splitlines()), 2, 'identical commands must remain separate')
        import fcntl
        with (self.state / 'activation.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for family, name in [('profile','Daily'),('preset','Twice')]:
                request = {'family':family,'name':name,'workspace':25,'revision':revision}
                result = subprocess.run(['python3',backend,'run',str(self.state),json.dumps(request)],capture_output=True,text=True,env=self.env)
                self.assertEqual(result.returncode, 75, result.stderr)

    def test_invalid_timeout_rejected_before_compositor_calls(self):
        for timeout in [-1, 0, 1000, '8', float('nan')]:
            plan = {'name':'Bad', 'timeoutSeconds':timeout, 'workspaces':[{'workspace':1,'preset':'P','commands':['never']} ]}
            result = subprocess.run(['python3',str(REPO/'scripts/workspace_profiles.py'),'activate',str(self.state),json.dumps(plan)],
                                    env=self.env,capture_output=True,text=True,timeout=2)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('timeout',result.stderr)
            self.assertEqual(self.log.read_text(),'')

if __name__ == '__main__':
    unittest.main()
