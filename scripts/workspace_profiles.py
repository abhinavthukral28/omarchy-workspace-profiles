#!/usr/bin/env python3
"""Launch-only workspace profiles. No close, ownership or config mutation API."""
import fcntl
import json
from pathlib import Path
import sys
import subprocess
import os
import tempfile
import time
import shlex


def atomic_json(path, value):
    from state_model import MAX_BYTES
    path = Path(path)
    serialized = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    require(len(serialized.encode()) <= MAX_BYTES, 'Formatted state exceeds 2 MiB')
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_plan(plan):
    require(isinstance(plan, dict) and isinstance(plan.get('name'), str) and plan['name'].strip(), 'Invalid plan name')
    timeout = plan.get('timeoutSeconds', 8)
    require(type(timeout) in (int, float) and 0.1 <= timeout <= 60, 'Invalid timeout (0.1–60 seconds required)')
    require(isinstance(plan.get('workspaces'), list) and plan['workspaces'], 'Invalid workspace list')
    seen = set()
    for step in plan['workspaces']:
        require(isinstance(step, dict), 'Invalid workspace step')
        ws = step.get('workspace')
        require(type(ws) is int and 1 <= ws <= 2147483647 and ws not in seen, 'Invalid or duplicate workspace')
        seen.add(ws)
        require(isinstance(step.get('preset'), str) and step['preset'].strip(), 'Invalid preset name')
        require(isinstance(step.get('commands'), list), 'Invalid command list')
        for entry in step['commands']:
            command = entry if isinstance(entry, str) else entry.get('command') if isinstance(entry, dict) else None
            require(isinstance(command, str) and command.strip() and '\0' not in command, 'Invalid command')
            if isinstance(entry, dict) and 'matchClass' in entry:
                require(isinstance(entry['matchClass'], str) and entry['matchClass'].strip() and '\0' not in entry['matchClass'], 'Invalid matchClass')


def hyprctl(*args):
    result = subprocess.run(['hyprctl', *args], capture_output=True, text=True, timeout=5)
    require(result.returncode == 0, 'hyprctl failed: ' + (result.stderr or result.stdout).strip())
    return result.stdout


def matching_clients(clients, match):
    # Exact current OR initial class, never a regular expression or ownership.
    return [c for c in clients if c.get('class') == match or c.get('initialClass') == match]


def command_for_window(window):
    value = window['value']
    if window['type'] == 'terminal':
        # Child shell protects trailing ;, &, comments, exit and exec from
        # consuming the outer hold/prompt grammar.
        held = ('bash -c ' + shlex.quote(value)
                + '; __ec=$?; printf "\\n[exited %s - press Enter to close]\\n" "$__ec"; read -r _')
        return 'omarchy-launch-terminal bash -c ' + shlex.quote(held)
    if window['type'] == 'webapp':
        return 'omarchy-launch-webapp ' + shlex.quote(value)
    return value


def lua_string(value):
    # Long strings avoid shell/Lua quote injection, including user newlines.
    equals = '='
    while ']' + equals + ']' in value:
        equals += '='
    return '[' + equals + '[' + value + ']' + equals + ']'


def launch_window(workspace, entry, timeout):
    before = json.loads(hyprctl('clients', '-j'))
    match = entry.get('matchClass') if isinstance(entry, dict) else None
    if match:
        clients = matching_clients(before, match)
        if any(c.get('workspace', {}).get('id') == workspace for c in clients):
            return
        if clients:
            locations = ', '.join('workspace ' + str(c.get('workspace', {}).get('id')) for c in clients)
            raise ValueError(f'{match} already exists on {locations}; not moved or relaunched')
    command = entry['command'] if isinstance(entry, dict) else entry
    shell = f'[workspace {workspace} silent] bash -c ' + shlex.quote(command)
    hyprctl('dispatch', 'hl.dsp.exec_cmd(' + lua_string(shell) + ')')
    addresses = {c.get('address') for c in before}
    deadline = time.monotonic() + timeout
    while True:
        after = json.loads(hyprctl('clients', '-j'))
        new = [c for c in after if c.get('workspace', {}).get('id') == workspace
               and c.get('address') not in addresses]
        if match:
            if matching_clients(new, match):
                return
        elif len(new) == 1:
            # Observation only, NOT attribution or ownership. No record saved.
            return
        elif len(new) > 1:
            raise ValueError(f'Window arrival on workspace {workspace} is ambiguous; stopped')
        if time.monotonic() >= deadline:
            raise ValueError(f'Timed out waiting for window on workspace {workspace}; command may still start later. Inspect before retrying.')
        time.sleep(0.05)



def activate(directory, plan):
    validate_plan(plan)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'activation.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        steps = [dict(workspace=s['workspace'], preset=s['preset'], status='pending') for s in plan['workspaces']]
        progress = directory / 'activation-progress.json'
        atomic_json(progress, steps)
        try:
            for index, step in enumerate(plan['workspaces']):
                steps[index]['status'] = 'running'
                atomic_json(progress, steps)
                for entry in step['commands']:
                    launch_window(step['workspace'], entry, plan.get('timeoutSeconds', 8))
                steps[index]['status'] = 'done'
                atomic_json(progress, steps)
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            for step in steps:
                if step['status'] != 'done':
                    step.update(status='failed', error=str(error))
            atomic_json(progress, steps)
            raise


def run_saved(directory, request):
    from state_model import snapshot
    current = snapshot(directory)
    require(current['revision'] == request.get('revision'), 'State changed; reload before launching')
    family = request.get('family')
    require(family in ('preset', 'profile'), 'Invalid launch family')
    data = current['data']
    entry = next((e for e in data[family + 's'] if e['name'] == request.get('name')), None)
    if entry is None:
        raise ValueError('Named item not found')
    if family == 'preset':
        workspace = request.get('workspace')
        if workspace is None:
            workspace = json.loads(hyprctl('activeworkspace', '-j'))['id']
        mappings = [{'workspace': workspace, 'preset': entry['name']}]
    else:
        mappings = entry['workspaces']
    presets = {p['name']: p for p in data['presets']}
    plan = {'name':entry['name'], 'closeMode':'keepExisting', 'workspaces':[]}
    for mapping in mappings:
        commands = []
        for window in presets[mapping['preset']]['windows']:
            command = {'command':command_for_window(window)}
            if 'matchClass' in window:
                command['matchClass'] = window['matchClass']
            commands.append(command)
        plan['workspaces'].append(dict(mapping, commands=commands))
    activate(directory, plan)


def main():
    try:
        if sys.argv[1] == 'load':
            from state_model import snapshot
            print(json.dumps(snapshot(sys.argv[2])))
        elif sys.argv[1] == 'save':
            from state_model import snapshot, normalize, MAX_BYTES
            directory = Path(sys.argv[2])
            directory.mkdir(parents=True, exist_ok=True)
            raw = sys.stdin.readline(MAX_BYTES + 2) if sys.argv[4] == '-' else sys.argv[4]
            require(len(raw.encode()) <= MAX_BYTES, 'State exceeds 2 MiB')
            with (directory / 'state.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                current = snapshot(directory)  # Corruption is never overwritten.
                require(current['revision'] == sys.argv[3], 'State changed on disk; reload and merge your draft before saving')
                data = normalize(json.loads(raw))
                atomic_json(directory / 'state.json', data)
                print(json.dumps(snapshot(directory)))
        elif sys.argv[1] == 'run':
            run_saved(sys.argv[2], json.loads(sys.argv[3]))
        elif sys.argv[1] == 'activate':
            activate(sys.argv[2], json.loads(sys.argv[3]))
        else:
            raise ValueError('Unknown action')
    except BlockingIOError:
        print('Another activation is running', file=sys.stderr)
        return 75
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
