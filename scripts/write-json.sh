#!/bin/bash
# Unvalidated arbitrary-path writes are retired; use the validated CAS backend.
printf '%s\n' 'Unrestricted JSON writer retired; use workspace_profiles.py save.' >&2
exit 64
