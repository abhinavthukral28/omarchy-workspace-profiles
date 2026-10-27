pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons

// One instance per QML engine, NOT one instance per monitor/widget.
QtObject {
  id: service
  readonly property string identity: "abhinav.workspace-profiles"
  readonly property string stateDirectory: (Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")) + "/omarchy/" + identity
  readonly property string backend: decodeURIComponent(String(Qt.resolvedUrl("../scripts/workspace_profiles.py")).replace(/^file:\/\//, ""))
  property var data: ({version: 1, presets: [], profiles: [], shortcuts: []})
  property string revision: ""
  property bool ready: false
  property string error: ""
  readonly property bool loading: reader.running
  readonly property bool saving: writer.running || saveQueue.length > 0
  property var saveQueue: []
  property var writing: null
  property int requestSequence: 0
  signal saveFinished(string requestId, bool success)
  function nextRequestId() { requestSequence += 1; return String(requestSequence) }
  property bool activationRunning: false
  property string activationError: ""
  property var activationSteps: []
  property var views: []
  property var activeView: null

  function registerView(view) { views = views.concat([view]) }
  function unregisterView(view) {
    views = views.filter(function(v) { return v !== view })
    if (activeView === view) activeView = null
  }
  function panelView() { return activeView || (views.length ? views[views.length - 1] : null) }
  function reload() {
    if (saving || loading || activationRunning) return "busy"
    reader.command = ["python3", backend, "load", stateDirectory]
    reader.running = true
    return "ok"
  }
  function acceptSnapshot(raw) {
    var snapshot = JSON.parse(raw)
    data = snapshot.data
    revision = snapshot.revision
    ready = true
    error = ""
  }
  function saveDraft(raw, baseRevision, requestId) {
    if (!ready || loading) return "not ready"
    if (activationRunning) return "busy"
    if (baseRevision !== revision) { error = "Draft is stale. Reload and merge it before saving."; return "stale" }
    try { JSON.parse(raw) } catch (e) { error = "Invalid JSON: " + e; return "invalid" }
    saveQueue = saveQueue.concat([{raw: raw, revision: baseRevision, requestId: String(requestId || "")}])
    startNextSave()
    return "queued"
  }
  function startNextSave() {
    if (writer.running || !saveQueue.length) return
    writing = saveQueue[0]
    saveQueue = saveQueue.slice(1)
    // Another view may have queued a draft based on an old snapshot. Never
    // let a valid but stale whole-document edit overwrite the preceding save.
    if (writing.revision !== revision) {
      error = "Queued draft is stale; reload and merge before saving."
      saveFinished(writing.requestId, false)
      writing = null
      Qt.callLater(startNextSave)
      return
    }
    writer.command = ["python3", backend, "save", stateDirectory, writing.revision, "-"]
    writer.running = true
  }
  function activate(family, name, workspace) {
    if (activationRunning || saving || loading) return "busy"
    if (!ready) return "not ready"
    var items = data[family + "s"] || []
    var found = items.some(function(item) { return item.name === name })
    if (!found) return "not found"
    var request = {family: family, name: name, revision: revision}
    if (workspace !== undefined && workspace !== null) request.workspace = workspace
    activationError = ""
    activationSteps = []
    activationRunning = true
    launcher.command = ["python3", backend, "run", stateDirectory, JSON.stringify(request)]
    launcher.running = true
    return "ok"
  }
  function activateSlot(family, slot) {
    for (var i=0; i<data.shortcuts.length; i++) {
      var s = data.shortcuts[i]
      if (s.family === family && s.slot === slot) return activate(family, s.name)
    }
    return "not found"
  }
  Component.onCompleted: reload()

  property Process readerProcess: Process {
    id: reader
    stdout: StdioCollector { id: readOut; waitForEnd: true }
    stderr: StdioCollector { id: readErr; waitForEnd: true }
    onExited: function(code, status) {
      if (code === 0 && status === 0) {
        try { service.acceptSnapshot(readOut.text) }
        catch (e) { service.ready = false; service.error = "Invalid backend response: " + e }
      } else {
        service.ready = false
        service.error = readErr.text.trim() || "Could not read state. Editing and launching are disabled."
      }
    }
  }
  property Process writerProcess: Process {
    id: writer
    stdinEnabled: true
    onStarted: write(JSON.stringify(JSON.parse(service.writing.raw)) + "\n")
    stdout: StdioCollector { id: writeOut; waitForEnd: true }
    stderr: StdioCollector { id: writeErr; waitForEnd: true }
    onExited: function(code, status) {
      var success = false
      if (code === 0 && status === 0) {
        try { service.acceptSnapshot(writeOut.text); success = true }
        catch (e) { service.ready = false; service.error = "Invalid save response: " + e }
      } else service.error = writeErr.text.trim() || "Save failed; your draft is retained in the editor."
      service.saveFinished(service.writing.requestId, success)
      service.writing = null
      // Let Process.running settle before starting the next request.
      Qt.callLater(service.startNextSave)
    }
  }
  property Process launcherProcess: Process {
    id: launcher
    stderr: StdioCollector { id: launchErr; waitForEnd: true }
    onExited: function(code, status) {
      service.activationRunning = false
      service.activationError = code === 0 && status === 0 ? "" : (launchErr.text.trim() || "Activation failed; inspect windows before retrying.")
      progress.reload()
    }
  }
  property FileView progressView: FileView {
    id: progress
    path: service.stateDirectory + "/activation-progress.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try { service.activationSteps = JSON.parse(text()) } catch (e) { /* retain known progress */ }
    }
  }
  property Commons.ShellIpc ipcHandler: Commons.ShellIpc {
    target: service.identity
    function open(): void { var v=service.panelView(); if (v) v.open() }
    function close(): void { var v=service.panelView(); if (v) v.close() }
    function toggle(): void { var v=service.panelView(); if (v) v.toggle() }
    function activateProfile(name: string): string { return service.activate("profile", name) }
    function activatePreset(name: string): string { return service.activate("preset", name) }
    function activatePresetOn(name: string, workspace: int): string { return service.activate("preset", name, workspace) }
    function activatePresetSlot(slot: int): string { return service.activateSlot("preset", slot) }
    function activateProfileSlot(slot: int): string { return service.activateSlot("profile", slot) }
    function status(): string { return JSON.stringify({ready:service.ready, saving:service.saving, activationRunning:service.activationRunning, error:service.error, activationError:service.activationError}) }
  }
}
