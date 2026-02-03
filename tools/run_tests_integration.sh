#!/usr/bin/env bash
set -euo pipefail

if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ ! -d ".venv" ]; then
    python -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

bash tools/install_dev_deps.sh

export JOB_SCOUT_RUN_INTEGRATION=1
python -m pytest -q -m integration
