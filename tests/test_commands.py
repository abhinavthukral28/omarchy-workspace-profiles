import importlib.util
import subprocess
import tempfile
from pathlib import Path
import os
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backend', REPO / 'scripts/workspace_profiles.py')
assert spec is not None and spec.loader is not None
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class Commands(unittest.TestCase):
    def test_terminal_shell_grammar_runs_in_child_and_exit_exec_still_hold(self):
        self.assertTrue(callable(getattr(backend, 'command_for_window', None)), 'terminal builder missing')
        with tempfile.TemporaryDirectory() as temp:
            launcher = Path(temp) / 'omarchy-launch-terminal'
            launcher.write_text('#!/bin/bash\nexec "$@"\n')
            launcher.chmod(0o755)
            env = dict(os.environ, PATH=temp + ':' + os.environ['PATH'])
            for value in ["printf 'hello';", "printf 'hello' &", "printf 'hello' # comment", "printf 'hello'\n", "printf 'hello'; exit 7", "exec printf 'hello'", "printf '%s' \"it's hello\""]:
                with self.subTest(value=value):
                    command = backend.command_for_window({'type':'terminal','value':value})
                    result = subprocess.run(['bash','-c',command], input='\n', capture_output=True, text=True, env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('hello', result.stdout)
                    self.assertIn('press Enter to close', result.stdout)
                    if 'exit 7' in value:
                        self.assertIn('exited 7', result.stdout)

if __name__ == '__main__':
    unittest.main()
