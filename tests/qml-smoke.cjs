// Real QML + installed controls + real helper processes, no display/socket.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const repo = path.resolve(__dirname, '..');
const corrupt = process.argv.includes('--corrupt');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'profiles-qml-'));
try {
  for (const folder of ['Commons', 'services']) fs.symlinkSync('/usr/share/omarchy/shell/' + folder, path.join(dir, folder));
  fs.mkdirSync(path.join(dir, 'Ui'));
  for (const file of fs.readdirSync('/usr/share/omarchy/shell/Ui')) {
    if (file !== 'KeyboardPanel.qml') fs.symlinkSync('/usr/share/omarchy/shell/Ui/' + file, path.join(dir, 'Ui', file));
  }
  fs.writeFileSync(path.join(dir, 'Ui', 'KeyboardPanel.qml'), `import QtQuick
Item {
  property var anchorItem; property var owner; property var bar; property bool open
  property var focusTarget; property real contentWidth; property real contentHeight
  width: contentWidth; height: contentHeight
  function fittedContentWidth(value) { return value }
  function fittedContentHeight(value, cap) { return Math.min(value, cap) }
}`);
  for (const folder of ['scripts', 'internal']) {
    if (fs.existsSync(path.join(repo, folder))) fs.symlinkSync(path.join(repo, folder), path.join(dir, folder));
  }
  for (const file of ['Presets.qml', 'NameEditor.qml']) if (fs.existsSync(path.join(repo,file))) fs.copyFileSync(path.join(repo,file),path.join(dir,file));
  fs.mkdirSync(path.join(dir,'bin'));
  fs.writeFileSync(path.join(dir,'bin','hyprctl'), `#!/bin/bash\nexec node '${repo}/tests/fake-hyprctl.cjs' "$@"\n`, {mode:0o755});
  fs.writeFileSync(path.join(dir,'clients.json'), JSON.stringify({workspace:23, clients:[]}));
  fs.writeFileSync(path.join(dir,'calls.jsonl'), '');
  const stateFile = path.join(dir,'state/omarchy/abhinav.workspace-profiles/state.json');
  if (corrupt) {
    fs.mkdirSync(path.dirname(stateFile),{recursive:true});
    fs.writeFileSync(stateFile,'broken JSON, preserve me');
  }
  fs.writeFileSync(path.join(dir,'shell.qml'), `
import QtQuick
import Quickshell
import qs.Commons as Commons
import "." as Plugin
ShellRoot {
  id: testRoot
  property int phase: 0
  property var transientView: null
  Component { id: transientType; Plugin.Presets {} }
  property string oldRevision: ""
  QtObject { id: incompleteBar; property color barForeground: "#abcdef" }
  Plugin.Presets { id: left }
  Plugin.Presets { id: right; bar: incompleteBar }
  function demand(ok, message) { if (!ok) throw Error(message) }
  function find(node, name) {
    if (!node) return null
    if (node.objectName === name) return node
    var items = node.data || []
    for (var i=0;i<items.length;i++) { var found = find(items[i], name); if (found) return found }
    var children = node.children || []
    for (var j=0;j<children.length;j++) { var found2 = find(children[j], name); if (found2) return found2 }
    return null
  }
  function findText(node, value) {
    if (!node) return null
    if (node.text === value && typeof node.clicked === "function") return node
    var items = node.data || []
    for (var i=0;i<items.length;i++) { var found = findText(items[i], value); if (found) return found }
    var children = node.children || []
    for (var j=0;j<children.length;j++) { var found2 = findText(children[j], value); if (found2) return found2 }
    return null
  }
  Timer {
    interval: 100; repeat: true; running: true
    onTriggered: {
      demand(left.store !== undefined, "SHARED_CONTROLLER_MISSING")
      var s = left.store
      demand(s === right.store, "monitor widgets must share one singleton")
      if (${corrupt}) {
        if (s.loading) return
        demand(!s.ready && /state.json/.test(s.error), "corrupt state not visible or editing enabled")
        demand(s.saveDraft('{}',s.revision) === "not ready", "corrupt state was editable")
        demand(s.activate("profile","Daily") === "not ready", "corrupt state could launch")
        console.log("WORKSPACE_PROFILES_SMOKE_PASSED")
        Qt.quit()
        return
      }
      if (!s.ready || s.saving || s.loading) return
      if (phase === 0) {
        oldRevision = s.revision
        var data = {version:1, notes:Array(150001).join("x"), presets:[{name:"<b>Work</b>",windows:[]}],
          profiles:[{name:"Daily",default:true,closeMode:"workspaceAll",workspaces:[{workspace:23,preset:"<b>Work</b>"}]}],shortcuts:[]}
        left.editConfiguration()
        right.editConfiguration()
        find(left,"configurationEditor").text = JSON.stringify(data)
        findText(left,"Validate & save").clicked()
        demand(left.awaitingSave, "first editor save rejected")
        data.notes = "stale queued overwrite"
        find(right,"configurationEditor").text = JSON.stringify(data)
        findText(right,"Validate & save").clicked()
        demand(right.awaitingSave, "second editor queue rejected")
        phase = 1
      } else if (phase === 1) {
        demand(right.store.data.presets[0].name === "<b>Work</b>", "other monitor stale")
        demand(s.data.notes.length === 150000 && /stale/.test(s.error), "stale queued write replaced newer state")
        demand(!left.editing && right.editing, "another monitor save discarded a stale editor draft")
        demand(/stale queued overwrite/.test(find(right,"configurationEditor").text), "stale editor content was discarded")
        right.editing = false
        demand(s.data.profiles[0].closeMode === "keepExisting" && !s.data.profiles[0].default, "unsafe imported profile")
        demand(s.saveDraft('{}', oldRevision) === "stale", "stale monitor must not overwrite")
        demand(right.activateProfileAt(0) === "ok", "canonical profile activation failed")
        demand(left.launchPresetAt(0,23) === "busy", "preset bypassed profile lock")
        phase = 2
      } else if (phase === 2 && !s.activationRunning) {
        demand(s.activationError === "", s.activationError)
        demand(left.launchPresetAt(0,23) === "ok", "preset activation failed")
        demand(right.activateProfileAt(0) === "busy", "profile bypassed preset lock")
        phase = 3
      } else if (phase === 3 && !s.activationRunning) {
        demand(s.activationError === "", s.activationError)
        var row = find(right, "profileLaunch0")
        demand(row !== null, "profile delegate missing")
        row.clicked()
        demand(s.activationRunning, "profile click did not resolve canonical index")
        phase = 4
      } else if (phase === 4 && !s.activationRunning) {
        demand(s.activationError === "", s.activationError)
        var tabs = [find(left,"presetsTab"),find(left,"profilesTab")]
        demand(tabs[0] && tabs[1] && tabs[0].width > 100 && Math.abs(tabs[0].width-tabs[1].width)<=1, "unequal tabs")
        demand(tabs[0].bordered && tabs[1].bordered, "missing idle borders")
        var ipc = Commons.IpcRegistry.call(s.identity, "activateProfile", ["Daily"])
        demand(ipc.ran && ipc.output === "ok", "registered IPC does not activate canonical profile")
        demand(Commons.IpcRegistry.handlers.filter(function(h) { return h.enabled && h.target === s.identity }).length === 1, "duplicate enabled IPC handlers")
        phase = 5
      } else if (phase === 5 && !s.activationRunning) {
        var edited = JSON.parse(JSON.stringify(s.data))
        edited.presets.push({name:"Second view edit",windows:[]})
        demand(right.store.saveDraft(JSON.stringify(edited), s.revision) === "queued", "independent current edit rejected")
        phase = 6
      } else if (phase === 6) {
        demand(left.store.data.presets.length === 2, "fresh second-view edit lost")
        transientView = transientType.createObject(left)
        demand(transientView.store === s && s.views.length === 3, "hotplug made another controller")
        demand(transientView.activateProfileAt(0) === "ok", "transient view activation rejected")
        transientView.destroy()
        phase = 7
      } else if (phase === 7 && !s.activationRunning) {
        demand(s.activationError === "", "monitor destruction interrupted shared worker")
        demand(s.views.length === 2, "destroyed monitor retained")
        demand(Commons.IpcRegistry.handlers.filter(function(h) { return h.enabled && h.target === s.identity }).length === 1, "hotplug duplicated IPC")
        console.log("WORKSPACE_PROFILES_SMOKE_PASSED")
        Qt.quit()
      }
    }
  }
  Timer { interval:12000; running:true; onTriggered: { console.log("SMOKE_TIMEOUT phase="+phase); Qt.quit() } }
}`);
  const result = spawnSync('quickshell', ['--no-color','-p',path.join(dir,'shell.qml')], {
    encoding:'utf8', timeout:15000,
    env:{...process.env, PATH:path.join(dir,'bin')+':'+process.env.PATH,
      XDG_STATE_HOME:path.join(dir,'state'), WAYLAND_DISPLAY:'', QT_QPA_PLATFORM:'offscreen',
      QT_QUICK_CONTROLS_STYLE:'Basic', QT_QPA_PLATFORMTHEME:'basic',
      TEST_CLIENTS:path.join(dir,'clients.json'), TEST_LOG:path.join(dir,'calls.jsonl')}
  });
  const output = result.stdout + result.stderr;
  assert.equal(result.status,0,output);
  assert.match(output,/WORKSPACE_PROFILES_SMOKE_PASSED/,output);
  assert.doesNotMatch(output,/WARN scene:|ERROR:|ReferenceError|TypeError|Binding loop|Unable to assign/);
  assert.doesNotMatch(output,/another handler is registered/);
  if (corrupt) assert.equal(fs.readFileSync(stateFile,'utf8'),'broken JSON, preserve me');
  else {
    const saved = JSON.parse(fs.readFileSync(stateFile));
    assert.equal(saved.profiles[0].closeMode,'keepExisting');
    assert.equal(saved.presets.length,2);
    assert.equal(saved.notes.length,150000);
  }
  assert.equal(fs.readFileSync(path.join(dir,'calls.jsonl'),'utf8'),'','empty plans must not touch compositor');
  console.log(corrupt ? 'PASS: corrupt state blocks UI save/launch and preserves original bytes; clean QML diagnostics.' : 'PASS: two monitor views share state, CAS saves, one IPC and one preset/profile coordinator; clean QML diagnostics.');
} finally { fs.rmSync(dir,{recursive:true,force:true}); }
