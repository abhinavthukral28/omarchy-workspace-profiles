#!/bin/bash
# Never expose live compositor, session bus, network or writable user HOME.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /run --tmpfs /tmp \
  --unshare-net --unshare-pid --bind "$repo" "$repo" --chdir "$repo" \
  --dir /tmp/home --setenv HOME /tmp/home --setenv XDG_STATE_HOME /tmp/home/.local/state \
  --setenv XDG_CONFIG_HOME /tmp/home/.config --setenv XDG_RUNTIME_DIR /tmp/runtime \
  --dir /tmp/runtime --setenv TMPDIR /tmp --unsetenv WAYLAND_DISPLAY --unsetenv DISPLAY \
  --unsetenv DBUS_SESSION_BUS_ADDRESS --unsetenv HYPRLAND_INSTANCE_SIGNATURE \
  --unsetenv BASH_ENV --setenv PYTHONDONTWRITEBYTECODE 1 --setenv QT_QPA_PLATFORM offscreen \
  --setenv QT_QUICK_CONTROLS_STYLE Basic --setenv QT_QPA_PLATFORMTHEME basic \
  "$@"
