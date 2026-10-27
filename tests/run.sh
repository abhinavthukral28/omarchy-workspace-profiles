#!/bin/bash
# Always start in an isolated, offline HOME with live sockets hidden.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$repo/tests/isolated.sh" bash -euo pipefail -c '
  python3 -m unittest discover -s tests -p "test_*.py" -v
  node --test tests/safety.test.cjs
  node tests/qml-smoke.cjs
  node tests/qml-smoke.cjs --corrupt
  /usr/lib/qt6/bin/qmlformat Presets.qml internal/Controller.qml >/dev/null
  for script in scripts/activate-profile.sh scripts/write-json.sh hooks/kdm-presets-activate-default-profile.sh tests/isolated.sh tests/run.sh; do
    bash -n "$script"
  done
  printf "%s\n" "PASS: QML parser and shell syntax checks"
'
