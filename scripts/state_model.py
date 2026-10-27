"""State schema, safe legacy normalization and atomic compare-and-swap storage."""
import copy
import hashlib
import json
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024


def check(ok, message):
    if not ok:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip()) and '\0' not in value and len(value) <= 65536


def normalize(data):
    # Python's JSON parser accepts NaN/Infinity extensions; ordinary QML JSON
    # does not. Reject them, including unknown preserved metadata fields.
    json.dumps(data, allow_nan=False)
    check(isinstance(data, dict) and data.get('version', 1) == 1, 'Unsupported state version')
    data = copy.deepcopy(data)
    data['version'] = 1
    for family in ('presets', 'profiles', 'shortcuts'):
        check(isinstance(data.get(family), list) and len(data[family]) <= 1000, f'{family} must be an array (maximum 1000)')
    names = {}
    for family in ('presets', 'profiles'):
        seen = set()
        for entry in data[family]:
            check(isinstance(entry, dict) and text(entry.get('name')), f'Invalid {family} name')
            key = entry['name'].strip().casefold()
            check(key not in seen, f'Duplicate {family} name: {entry["name"]}')
            seen.add(key)
        names[family] = {entry['name'] for entry in data[family]}
    for preset in data['presets']:
        check(isinstance(preset.get('windows'), list) and len(preset['windows']) <= 1000, 'Invalid window list')
        for window in preset['windows']:
            check(isinstance(window, dict) and window.get('type') in ('custom', 'terminal', 'webapp') and text(window.get('value')), 'Invalid window entry')
            if 'label' in window:
                check(isinstance(window['label'], str), 'Invalid window label')
            if 'matchClass' in window:
                check(text(window['matchClass']), 'Invalid matchClass (exact string required)')
    for profile in data['profiles']:
        profile['default'] = False
        profile['closeMode'] = 'keepExisting'
        check(isinstance(profile.get('workspaces'), list) and len(profile['workspaces']) <= 1000, 'Invalid workspace list')
        seen = set()
        for step in profile['workspaces']:
            check(isinstance(step, dict), 'Invalid workspace entry')
            ws = step.get('workspace')
            check(type(ws) is int and 1 <= ws <= 2147483647 and ws not in seen, 'Invalid or duplicate workspace number')
            seen.add(ws)
            check(step.get('preset') in names['presets'], f'Missing preset: {step.get("preset")}')
    slots, assigned = set(), set()
    for shortcut in data['shortcuts']:
        check(isinstance(shortcut, dict) and shortcut.get('family') in ('preset', 'profile'), 'Invalid shortcut family')
        family = shortcut['family']
        slot = shortcut.get('slot')
        check(type(slot) is int and 1 <= slot <= 9, 'Invalid shortcut slot (1–9)')
        check(shortcut.get('name') in names[family + 's'], 'Missing shortcut reference')
        key, item = (family, slot), (family, shortcut['name'])
        check(key not in slots and item not in assigned, 'Duplicate shortcut')
        slots.add(key)
        assigned.add(item)
    return data


def snapshot(directory):
    directory = Path(directory)
    # A single canonical document avoids cross-file partial transactions.
    files = ['state.json'] if (directory / 'state.json').exists() else ['presets.json', 'profiles.json', 'shortcuts.json']
    raw, parsed = {}, {}
    for name in files:
        path = directory / name
        try:
            check(not path.is_symlink(), f'{path}: symlink state is not supported')
            try:
                value = path.read_bytes()
            except FileNotFoundError:
                value = None
            if value is not None:
                check(len(value) <= MAX_BYTES, f'{path}: state exceeds 2 MiB')
                parsed[name] = json.loads(value)
            raw[name] = value
        except (ValueError, OSError) as error:
            raise ValueError(f'{path}: {error}') from error
    data = parsed.get('state.json', {'version': 1, **{name[:-5]: parsed.get(name, []) for name in files}})
    try:
        data = normalize(data)
    except ValueError as error:
        raise ValueError(f'{directory}/{", ".join(files)}: {error}') from error
    digest = hashlib.sha256()
    for name, value in raw.items():
        digest.update(name.encode() + b'\0' + (b'MISSING' if value is None else value) + b'\0')
    return {'data': data, 'revision': digest.hexdigest()}
