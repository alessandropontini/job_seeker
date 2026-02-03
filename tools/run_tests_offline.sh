#!/usr/bin/env bash
set -euo pipefail

if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ ! -d ".venv" ]; then
    python -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export NO_NETWORK=1

bash tools/install_dev_deps.sh

python -m pytest -q
python -m pytest -q
