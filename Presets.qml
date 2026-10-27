import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import qs.Commons as Commons
import qs.Ui as Ui
import "internal" as Shared

// Monitor-local view only: persistent state, workers and IPC are singleton-owned.
// Delegates pass canonical indices, never QVariantList-backed modelData.
Ui.Panel {
  id: root
  moduleName: "abhinav.workspace-profiles"
  manageIpc: false
  readonly property var store: Shared.Controller
  readonly property color foreground: bar && bar.barForeground !== undefined ? bar.barForeground
    : bar && bar.foreground !== undefined ? bar.foreground : Commons.Color.foreground
  property string tab: "presets"
  property bool editing: false
  property string draftRevision: ""
  property bool awaitingSave: false
  property string pendingSaveId: ""
  implicitWidth: icon.implicitWidth
  implicitHeight: icon.implicitHeight

  function activateProfileAt(index) {
    if (index < 0 || index >= store.data.profiles.length) return "not found"
    return store.activate("profile", store.data.profiles[index].name)
  }
  function launchPresetAt(index, workspace) {
    if (index < 0 || index >= store.data.presets.length) return "not found"
    return store.activate("preset", store.data.presets[index].name, workspace)
  }
  function editConfiguration() {
    if (!store.ready || store.saving || store.activationRunning) return
    editor.text = JSON.stringify(store.data, null, 2)
    draftRevision = store.revision
    editing = true
  }
  Component.onCompleted: store.registerView(root)
  Component.onDestruction: store.unregisterView(root)
  onOpenedChanged: if (opened) store.activeView = root
  Connections {
    target: root.store
    function onSaveFinished(requestId, success) {
      if (requestId !== root.pendingSaveId) return
      root.awaitingSave = false
      if (success) root.editing = false
    }
  }
  component Label: Text {
    textFormat: Text.PlainText
    color: root.foreground
    font.family: Commons.Style.font.family
    font.pixelSize: Commons.Style.font.body
    wrapMode: Text.WordWrap
    Layout.fillWidth: true
  }
  component Action: Ui.Button {
    bordered: true
    focusable: true
    foreground: root.foreground
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    Layout.preferredHeight: 36
  }
  Ui.Button {
    id: icon
    iconText: ""
    foreground: root.foreground
    selected: root.opened
    tooltipText: "Workspace Profiles — launch only"
    onClicked: root.toggle()
  }
  Ui.KeyboardPanel {
    id: popup
    anchorItem: icon
    owner: root
    bar: root.bar
    open: root.opened
    contentWidth: 620
    contentHeight: 620
    focusTarget: body
    ColumnLayout {
      id: body
      anchors.fill: parent
      anchors.margins: 12
      spacing: 10
      Label { text: "Workspace Profiles"; font.bold: true }
      Label { text: "Launch only · existing windows and layouts are kept. No shortcuts or startup hooks are installed."; font.pixelSize: Commons.Style.font.bodySmall }
      Label { visible: !root.store.ready && !root.store.error; text: "Loading…" }
      Label { visible: root.store.error !== ""; text: root.store.error }
      Label { visible: root.store.activationError !== ""; text: root.store.activationError }
      Label { visible: root.store.activationRunning; text: "Launching… Do not retry while applications are starting." }
      RowLayout {
        Layout.fillWidth: true
        Action { objectName: "presetsTab"; text: "Presets"; selected: root.tab === "presets"; onClicked: { root.tab = "presets"; list.contentY = 0 } }
        Action { objectName: "profilesTab"; text: "Profiles"; selected: root.tab === "profiles"; onClicked: { root.tab = "profiles"; list.contentY = 0 } }
      }
      Flickable {
        id: list
        visible: !root.editing
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: width
        contentHeight: entries.implicitHeight + 4
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        ColumnLayout {
          id: entries
          x: 2
          width: list.width - 4
          spacing: 8
          Label { visible: root.tab === "presets" && !root.store.data.presets.length; text: "No presets. Use Edit JSON to add your own commands." }
          Label { visible: root.tab === "profiles" && !root.store.data.profiles.length; text: "No profiles. A profile maps global workspace numbers to named presets." }
          Repeater {
            model: root.store.data.presets
            delegate: Action {
              required property int index
              required property var modelData
              objectName: "presetLaunch" + index
              visible: root.tab === "presets"
              text: modelData.name
              tooltipText: "Launch on the currently active workspace: " + modelData.name
              enabled: root.store.ready && !root.store.activationRunning && !root.store.saving
              onClicked: root.launchPresetAt(index)
            }
          }
          Repeater {
            model: root.store.data.profiles
            delegate: Action {
              required property int index
              required property var modelData
              objectName: "profileLaunch" + index
              visible: root.tab === "profiles"
              text: modelData.name
              tooltipText: "Launch on explicit saved workspaces; keep existing windows: " + modelData.name
              enabled: root.store.ready && !root.store.activationRunning && !root.store.saving
              onClicked: root.activateProfileAt(index)
            }
          }
          Repeater {
            model: root.store.activationSteps
            delegate: Label {
              required property var modelData
              text: "Workspace " + modelData.workspace + ": " + modelData.status + (modelData.error ? " — " + modelData.error : "")
            }
          }
        }
      }
      Controls.ScrollView {
        visible: root.editing
        Layout.fillWidth: true
        Layout.fillHeight: true
        Controls.TextArea {
          id: editor
          objectName: "configurationEditor"
          textFormat: TextEdit.PlainText
          wrapMode: TextEdit.NoWrap
          enabled: !root.store.saving
          selectByMouse: true
          color: root.foreground
          font.family: Commons.Style.font.family
          background: Rectangle { color: Commons.Color.background; border.color: root.foreground; border.width: 1 }
        }
      }
      Label { visible: root.editing; text: "Commands are trusted shell code. Save validates names, references and exact matchClass strings. Legacy close/default flags are normalized to keepExisting/false."; font.pixelSize: Commons.Style.font.bodySmall }
      RowLayout {
        Layout.fillWidth: true
        Action {
          text: root.editing ? (root.store.saving ? "Saving…" : "Validate & save") : "Edit JSON"
          enabled: root.store.ready && !root.store.saving && !root.store.activationRunning
          onClicked: {
            if (!root.editing) root.editConfiguration()
            else {
              root.pendingSaveId = root.store.nextRequestId()
              root.awaitingSave = root.store.saveDraft(editor.text, root.draftRevision, root.pendingSaveId) === "queued"
            }
          }
        }
        Action {
          text: root.editing ? "Cancel draft" : "Reload state"
          enabled: !root.store.saving && !root.store.activationRunning
          onClicked: { if (root.editing) root.editing = false; else root.store.reload() }
        }
      }
    }
  }
}
