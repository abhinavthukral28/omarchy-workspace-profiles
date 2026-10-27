// Contract guards supplement execution tests; no upstream destructive APIs remain.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const repo = path.resolve(__dirname,'..');
const read = name => fs.readFileSync(path.join(repo,name),'utf8');

test('fork identity and metadata describe only explicit launch-only use', () => {
  const manifest = JSON.parse(read('manifest.json'));
  assert.equal(manifest.id,'abhinav.workspace-profiles');
  assert.equal(manifest.name,'Workspace Profiles');
  assert.equal(manifest.barWidget.displayName,'Workspace Profiles');
  assert.doesNotMatch(manifest.description,/login|default|close/i);
  for (const name of ['Presets.qml','internal/Controller.qml','scripts/workspace_profiles.py','scripts/state_model.py']) {
    assert.doesNotMatch(read(name),/kdm[.-]presets|kdm\.presets/);
  }
});

test('unsafe onboarding, default and close selectors are removed, not hidden', () => {
  const ui = read('Presets.qml');
  assert.doesNotMatch(ui,/installStartupHook|setProfileDefault|setProfileCloseMode|acceptOnboarding|buildOnboarding|closeModes/);
  const backend = read('scripts/workspace_profiles.py');
  assert.doesNotMatch(backend,/window\.close|dispatch.*kill|layout:scrolling|active-profile\.json|ownership\s*=/);
  assert.doesNotMatch(read('internal/Controller.qml'),/activateDefault|hook install|bindings\.lua/);
});

test('old boot hook and unrestricted write helper are inert migration entrypoints', () => {
  for (const name of ['hooks/kdm-presets-activate-default-profile.sh','scripts/write-json.sh']) {
    const result = spawnSync('bash',[path.join(repo,name),'/nonexistent/never-write','[]'],{encoding:'utf8'});
    assert.notEqual(result.status,0);
    assert.match(result.stderr,/disabled|retired/i);
    assert.doesNotMatch(read(name),/omarchy-shell|hyprctl|mv |cp |mkdir/);
  }
});
