# Test contract and TDD evidence

Run everything with `bash tests/run.sh`. It invokes `tests/isolated.sh` before any
runtime test. Individual examples:

```sh
bash tests/isolated.sh python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/isolated.sh node --test tests/safety.test.cjs
bash tests/isolated.sh node tests/qml-smoke.cjs
bash tests/isolated.sh node tests/qml-smoke.cjs --corrupt
```

Do not run upstream test shells or helpers against your actual HOME. The wrapper
uses read-only `/`, binds only the checkout writable, creates private `/run`,
`/tmp`, HOME/XDG paths and PID/network namespaces, supplies `/dev`, removes display,
Hyprland and session-bus variables, and disables bytecode writes. `/dev` matters:
a read-only inherited `/dev/null` can produce misleading subprocess failures.
Each compositor test explicitly injects the fake `hyprctl` on PATH. That fake only
updates JSON; it refuses unknown/destructive dispatchers and never executes
configured commands. Terminal grammar tests run only neutral printf commands
through a temporary launcher in the isolated namespace.

## Observed red → green slices during this implementation

The following failures were actually executed before their corresponding runtime
changes, not reconstructed afterward:

1. Legacy `workspaceAll`, `trackedOnly`, and `keepExisting` with corrupt ownership
   all failed in the old helper (`Cannot read window ownership`). The launch-only
   helper now leaves all clients, layout and the old ownership bytes untouched.
2. Invalid later workspace was accepted; existing exact-class entries were
   unsupported. Added full-plan preflight and exact present/elsewhere matching;
   all three tests became green.
3. Explicit target launch, no-match compatibility, unrelated-class rejection,
   timeout progress and ambiguous-arrival tests failed at the unimplemented launch
   boundary. Added bounded, explicitly targeted observation; they became green.
4. Legacy load failed with `Unknown action`; malformed input tests were refined
   to require the actual path in the error (rather than accepting any failure).
   Added schema-checked read-only loading and forced safety normalization.
5. Atomic save and invalid reference/slot tests failed with `Unknown action`.
   Added full-model validation and locked revision-CAS atomic replacement.
6. Terminal grammar test failed because the command builder was missing. The
   child-Bash wrapper passed trailing semicolon/background/comment/newline/quote,
   explicit exit and exec cases, including the outer hold prompt.
7. Saved preset/profile coordinator test failed with `Unknown action`. The unified
   backend then passed duplicate identical entries and cross-family lock checks.
8. The real two-widget QML smoke failed `SHARED_CONTROLLER_MISSING`, emitted the
   old undefined-QColor warning and duplicate-IPC warning. The proper singleton
   and view rewrite passed. The strict diagnostic gate also caught an initial
   singleton `Item.data` collision; using an explicit QtObject controller fixed it.
9. Manifest identity and inert-helper tests failed on the upstream identity and
   executable hook. Renaming the identity and retiring those entrypoints passed.
10. Invalid timeout test accepted an invalid timeout. Bounded timeout preflight
    now rejects it before any compositor calls.
11. Large stdin draft failed JSON parsing (`-` unsupported). Added line-framed
    stdin saving. The QML 150-kB save then separately reproduced a Process
    argument-too-long start failure; moving the real writer payload to stdin
    made the integration smoke green without relaxing diagnostics.
12. Non-JSON/oversized formatted-state test accepted an invalid write. Serialize
    and bound the final bytes before opening a replacement file; it became green.
13. Two live editor drafts reproduced the other monitor's save prematurely
    dismissing the stale editor. Request-correlated completion now dismisses only
    the successful request's editor and retains the rejected draft verbatim.

Additional regression assertions exercise concurrent independent backend writers,
stale queued drafts, fresh edits from another view, installed IpcRegistry routing,
canonical-index delegate clicks, shared preset/profile busy guards, controller
survival when a launching monitor view is destroyed, and corrupt-state UI blocking.

## Coverage migration from upstream

The old close/ownership tests intentionally asserted behavior this fork must never
perform. They were replaced with permanent no-close/no-ownership tests, not changed
to accept destructive behavior. The onboarding/default setup tests and their
runtime fixture were removed because those APIs/controls no longer exist; inert
legacy entrypoints are executed and checked instead. The removed NameEditor and
its key-propagation test belonged to the removed multi-step form. Name uniqueness,
malformed arrays, references, workspaces, shortcut ranges and stale-save guards
are covered at the new schema/coordinator boundaries. The JSON TextArea is plain
text, and launch buttons use the installed Omarchy focusable button control.

The QML harness substitutes only KeyboardPanel's unsupported offscreen display
surface. Installed controls, Commons, FileView, Process, IPC registry and production
Python helpers remain real. Success requires both an explicit lifecycle marker
and absence of QML scene/type/reference/binding/QColor errors. The expected generic
warning that no Hyprland instance is set is not a QML scene diagnostic. No warning
was suppressed to make the test pass.

This is not a native-display or real-application launch certification. Actual
workspace rules, compositor policy, app window reuse, PWA classes, SSH health,
monitor placement and popup rendering require a separately approved live check.
