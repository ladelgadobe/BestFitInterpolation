#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$task_root/ci/resolve_images.py" --mode full
python3 "$task_root/scripts/test_qgis_version.py" "$@"
