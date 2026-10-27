#!/bin/bash
# Migration-compatible entrypoint: legacy closeMode is NEVER acted upon.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/workspace_profiles.py" activate "$@"
