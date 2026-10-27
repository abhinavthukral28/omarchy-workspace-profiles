# Workspace Profiles

A **launch-only** fork of kdm's Presets widget for Omarchy. Plugin and IPC identity:
`abhinav.workspace-profiles`. Title: **Workspace Profiles**.

A preset is an ordered list of commands. A profile maps explicit global workspace
numbers to presets. This is **not session restoration**: no saved window geometry,
monitor topology, scroll position, application state, ownership or unconditional
window ordering is restored.

## Safety contract

- Existing windows are never closed, killed, moved or adopted as owned. There is
  no ownership database or closing implementation.
- Every imported profile is normalized to `closeMode: "keepExisting"` and
  `default: false`. The UI has no close-mode/default controls. The compatibility
  activation helper also ignores every legacy close mode permanently.
- Existing workspace layout is left alone: no forced scrolling layout, workspace
  rule edits, focus switching, configuration reloads or binding changes.
- No first-run setup, automatic shortcut installation, boot hook installation,
  or startup/default activation. Opening/loading the widget only reads state.
- Presets, profiles, row clicks and IPC all use the same coordinator. While one
  activation runs, other requests return `busy`; they are **not silently queued**.
- Commands run sequentially with an explicit Hyprland exec workspace rule
  (`[workspace N silent]`) and an 8-second window-observation timeout per entry.
  A failed command/timeout stops the rest of the plan and reports an error.
  Already-started applications are **not** terminated or rolled back. A timed-out
  application may still open later: inspect your windows before retrying.

**Commands are executable code, not sandboxed data.** Custom and terminal values
are intentional Bash commands with your full user permissions. They can change
files, access the network, close applications themselves, or prompt for privilege.
The plugin's launch-only policy does not sandbox commands or prevent an app's own
single-instance/window-placement behavior. Only import commands you have reviewed.
No personal commands or profiles are bundled.

## Window matching: opt-in and exact

A window entry can contain an optional `matchClass` string. It is compared exactly
against Hyprland's `class` or `initialClass` — never evaluated as a regex or code.

1. If a matching client already exists **on the target workspace**, the entry is
   considered present, without launching another copy.
2. If matching clients exist only elsewhere, activation stops and reports their
   workspace location. It does not move, focus or duplicate them.
3. Otherwise launch, then wait for a new matching client on the target workspace.
   Unrelated classes cannot confirm success.

Use an application-specific class, not a generic browser or terminal class, when
multiple windows must remain distinct. An overly broad `matchClass` can consider
the wrong same-class window present. It does not validate a page, URL, document,
remote host or application's health. A matching terminal does not prove its child
command succeeded.

Entries without `matchClass` remain compatible: each entry is launched separately,
including identical command strings, and waits for one new client address on its
target workspace. Multiple simultaneous arrivals fail as ambiguous. A single
unrelated arrival on that workspace can still satisfy this **best-effort
observation**, so it is not reliable attribution, ownership or universal dedup.
Reactivating unmatched entries generally adds more windows. Applications that
reuse/focus existing windows may time out; configure an exact class when suitable.

## Use and customization

Requirements: an Omarchy shell with `qs.Ui` and `Commons.ShellIpc` (tested against
the locally installed Omarchy 4.5.0rc1 / Quickshell 0.3.2 APIs), Lua-enabled
Hyprland with `hl.dsp.exec_cmd`, Python 3, Bash and `hyprctl`. No packages are
installed by this repository.

After a separately reviewed installation, the bar icon opens a panel with Presets
and Profiles tabs. Click a preset to launch on the **currently active global
workspace** (captured once at activation); click a profile to launch on its saved
workspace numbers. Global workspace IDs are not per-monitor displayed slot
numbers; monitor affinity remains the compositor's responsibility.

**Edit JSON** opens a plain-text configuration editor. This deliberately replaces
the upstream multi-step editor, webapp discovery, name fields and risky onboarding
flow with one small, auditable customization boundary. Add/edit/delete/reorder
presets, windows, profiles and shortcut slots in this document; **Validate & save**
checks the full model before committing. Invalid drafts remain in the editor.
Names are case-insensitively unique; profile preset references, duplicate workspace
numbers and slots are checked before saving. Renaming an item requires updating
its references in the same document. Return inside the JSON editor inserts a
newline; it does not launch the selected profile. Launch buttons support Tab and
Return/Enter through Omarchy's button control.

Example document (generic placeholders; replace commands and workspace numbers):

```json
{
  "version": 1,
  "presets": [
    {
      "name": "Notes",
      "windows": [
        {
          "type": "custom",
          "value": "foot --app-id=workspace-notes",
          "label": "Notes terminal",
          "matchClass": "workspace-notes"
        },
        {
          "type": "terminal",
          "value": "printf 'hello';"
        }
      ]
    }
  ],
  "profiles": [
    {
      "name": "Reading",
      "default": false,
      "closeMode": "keepExisting",
      "workspaces": [{"workspace": 2, "preset": "Notes"}]
    }
  ],
  "shortcuts": [{"family": "profile", "slot": 1, "name": "Reading"}]
}
```

Window types:

- `custom`: Bash command, preserved as written.
- `terminal`: `omarchy-launch-terminal` runs the command in a **child** Bash,
  then the outer Bash displays its exit code and waits for Enter. Trailing `;`,
  `&`, comments, quotes, newlines, `exit` and `exec` do not consume the hold logic.
- `webapp`: `omarchy-launch-webapp` receives the value as one quoted argument.
  This launches a URL; it does not inspect/install desktop files.

Use **Reload state** to discover manual/external edits. Do not discard a draft
without copying it somewhere if needed. The editor does not automatically merge
concurrent drafts. A stale draft is rejected rather than overwriting another
monitor's accepted edit. Individual commands/labels can be inspected directly in
JSON; there are no hidden bundled launch commands.

### Manual IPC integration

No bindings are installed. If you separately choose to configure shortcuts, the
explicit IPC calls are:

```sh
omarchy-shell abhinav.workspace-profiles toggle
omarchy-shell abhinav.workspace-profiles activateProfile 'Reading'
omarchy-shell abhinav.workspace-profiles activatePreset 'Notes'
omarchy-shell abhinav.workspace-profiles activatePresetOn 'Notes' 2
omarchy-shell abhinav.workspace-profiles activatePresetSlot 1
omarchy-shell abhinav.workspace-profiles activateProfileSlot 1
omarchy-shell abhinav.workspace-profiles status
```

Slots are independent 1–9 preset/profile namespaces stored in JSON; assigning one
does not create a keybinding. `ok` means the request was accepted asynchronously,
not that every app is ready. Errors/progress appear in the panel; `status` exposes
readiness, busy flags and the last error. Panel IPC uses the most recently opened
surviving view, or the last registered monitor view if none was opened; it does
not promise pointer-monitor routing. Loading the singleton requires an enabled
bar widget. No `activateDefaultProfile` endpoint exists.

## Storage, migration and recovery

State is identity-isolated under:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/abhinav.workspace-profiles/
  state.json                  # canonical version-1 document
  state.lock                  # cross-process save lock
  activation.lock             # cross-process preset/profile coordinator lock
  activation-progress.json    # latest progress; not ownership
```

If `state.json` does not exist, the loader accepts legacy `presets.json`,
`profiles.json`, and `shortcuts.json` arrays **in this new identity's directory**;
missing files mean empty arrays. The first successful explicit save writes one
canonical document atomically. Legacy input files remain untouched, but are no
longer consulted once `state.json` exists. Unknown metadata fields are generally
preserved, except the forced safety flags. Documents are bounded to 2 MiB and
1000 entries per collection/window/workspace list; window value/name strings have
additional schema limits. Ordinary JSON compatibility is prioritized, not an
unversioned arbitrary-object format.

There is no automatic import from upstream's state directory. To migrate, back up
and review the JSON first, then explicitly copy the reviewed arrays to the new
identity's state directory before its first save. **Do not copy ownership files,
boot hooks or onboarding results.** Old copied hooks/bindings in your user config
are not removed or modified by this fork. If you used upstream, separately inspect
and disable its old plugin/hooks/shortcuts with your own approval; this fork does
not register or respond to upstream's IPC identity. The old hook filename retained
in this checkout is an inert error-only migration entrypoint, not an installer.

Corrupt, inaccessible, oversized or schema-invalid state is not treated as empty:
load fails visibly and disables editing/launching, preserving the last good model
and the original file. Repair/restore the file manually from a backup and Reload.
Save revalidates current disk contents and compares a SHA-256 revision under a
file lock before replacing `state.json`. External changes reject stale saves and
stale launch requests. Save payloads travel over stdin, not shell interpolation or
large argv strings. No automatic backup history, conflict merging or recovery
export UI is provided. Atomic replacement protects from partial writes; it is not
a substitute for backups or a transaction against arbitrary non-cooperating
external editors.

## Architecture

- `Presets.qml`: per-monitor view, tab/editor draft state and canonical-index
  delegate callbacks. No data workers, save queues or active IPC handlers in
  views (`Panel.manageIpc` is false).
- `internal/Controller.qml` + `internal/qmldir`: a **proper QML singleton** shared
  by all views imported from this installed plugin URL in the shell's QML engine.
  Owns the data/revision, FIFO save queue, tracked Process objects, activation guard,
  progress and one registered `Commons.ShellIpc` handler. Monitor destruction does
  not destroy the controller or its workers.
- `scripts/state_model.py`: validation, safe legacy normalization and snapshot
  fingerprints. One canonical JSON document avoids cross-file partial saves.
- `scripts/workspace_profiles.py`: atomic CAS saves and a common launch-only
  coordinator for both families. Builds shell commands at one boundary, applies
  explicit workspace rules, observes new windows, reports failures. Stores no
  ownership; never closes anything.
- `scripts/activate-profile.sh`: compatible old launch-plan entrypoint backed by
  the same coordinator. Legacy close modes have no effect.
- `scripts/write-json.sh` and the old hook path: inert, nonzero, explanatory exits.

Customization should change data first, view/theme second, and controller/backend
only for behavior changes. Identity-derived state and IPC do not share upstream's
paths. Backend lock/revision checks defend against separate shell processes; do
not install multiple different plugin copies with the same identity and expect
independent IPC namespaces.

## Tests (isolated, no live desktop access)

```sh
bash tests/run.sh
```

The runner always enters Bubblewrap: read-only `/`, only this checkout writable,
private `/run`, `/tmp`, HOME/XDG paths, private PID/network namespaces, fresh
`/dev`, no compositor/display/session-bus environment. Helpers see only an explicit
fake `hyprctl`; test commands do not launch real applications. Dependencies:
`bwrap`, Python 3, Node.js, installed Omarchy/Quickshell/Qt tooling.

Execution tests cover immutable legacy close safety, exact-class present/elsewhere
matching, explicit targets, duplicate commands, ambiguous arrivals, timeouts and
stop-on-failure, unified process locks, terminal grammar, corruption preservation,
reference/slot/name validation, atomic saves and concurrent stale writers. Real
headless Quickshell loads two views, exercises the actual Process save queue,
150-kB stdin payload, stale queued drafts, fresh independent edits, canonical row
clicks, registry IPC, both activation guards and monitor create/destroy lifecycle.
A second smoke run checks corrupt-state UI blocking. Both require success markers
**and no QML scene/type/binding/QColor diagnostics**. Only KeyboardPanel's display
surface is stubbed; installed controls and backend processes remain real.

This does **not** certify native Wayland popup geometry, monitor placement, actual
application mapping, Chromium handoff, SSH session health or real desktop behavior.
Those require a separately authorized post-install check. See `tests/README.md`
for the TDD changes and coverage migration.

## Attribution

Fork of kdm's MIT-licensed Presets plugin. Original license retained. Legacy media
in `docs/` and `preview.png` is upstream artwork, not evidence of this fork's UI.
