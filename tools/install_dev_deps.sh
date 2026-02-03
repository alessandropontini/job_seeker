#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python"

if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ ! -d ".venv" ]; then
    echo "Creating virtual environment at .venv"
    python -m venv .venv
  fi

  if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
  else
    echo "Warning: .venv/bin/activate not found; continuing with system python." >&2
  fi

  echo "Note: activate the virtual environment with: source .venv/bin/activate"
fi

echo "Upgrading pip (best effort)"
"${PYTHON_BIN}" -m pip install --upgrade pip || echo "Warning: pip upgrade failed; continuing." >&2

echo "Installing dev dependencies from PyPI"
if "${PYTHON_BIN}" -m pip install -r requirements-dev.txt; then
  echo "PyPI install succeeded."
else
  echo "PyPI install failed. Falling back to wheelhouse." >&2

  if [ -z "${JOB_SCOUT_WHEELHOUSE_URL:-}" ]; then
    echo "Error: JOB_SCOUT_WHEELHOUSE_URL is not set. Provide a wheelhouse URL or local path." >&2
    exit 1
  fi

  WHEELHOUSE_DIR=".wheelhouse"
  WHEELHOUSE_ZIP="wheelhouse.zip"
  WHEELHOUSE_PATH="${JOB_SCOUT_WHEELHOUSE_URL}"

  if [[ "${JOB_SCOUT_WHEELHOUSE_URL}" =~ ^https?:// || "${JOB_SCOUT_WHEELHOUSE_URL}" =~ ^file:// ]]; then
    echo "Downloading wheelhouse from ${JOB_SCOUT_WHEELHOUSE_URL}"
    curl -fL "${JOB_SCOUT_WHEELHOUSE_URL}" -o "${WHEELHOUSE_ZIP}"
    rm -rf "${WHEELHOUSE_DIR}"
    unzip -q "${WHEELHOUSE_ZIP}" -d "${WHEELHOUSE_DIR}"
    WHEELHOUSE_PATH="${WHEELHOUSE_DIR}"
  elif [ -f "${JOB_SCOUT_WHEELHOUSE_URL}" ]; then
    if [[ "${JOB_SCOUT_WHEELHOUSE_URL}" == *.zip ]]; then
      rm -rf "${WHEELHOUSE_DIR}"
      unzip -q "${JOB_SCOUT_WHEELHOUSE_URL}" -d "${WHEELHOUSE_DIR}"
      WHEELHOUSE_PATH="${WHEELHOUSE_DIR}"
    fi
  fi

  echo "Installing dev dependencies from wheelhouse: ${WHEELHOUSE_PATH}"
  "${PYTHON_BIN}" -m pip install --no-index --find-links "${WHEELHOUSE_PATH}" -r requirements-dev.txt
fi

echo "Installed pytest version:"
"${PYTHON_BIN}" -m pytest --version
