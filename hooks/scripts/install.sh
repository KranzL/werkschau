#!/bin/bash
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${PLUGIN_ROOT}/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on PATH. Install Python 3.10+ and re-run." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found on PATH. Install from https://cli.github.com and run 'gh auth login'." >&2
  exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [ "${PY_MAJOR}" -lt 3 ] || { [ "${PY_MAJOR}" -eq 3 ] && [ "${PY_MINOR}" -lt 10 ]; }; then
  echo "Python ${PY_VERSION} is too old. Werkschau needs 3.10+." >&2
  echo "Install a newer Python (e.g., 'brew install python@3.12') and re-run." >&2
  exit 1
fi

echo "Setting up Werkschau (Python ${PY_VERSION})..."

if [ ! -d "${VENV}" ]; then
  echo "  Creating virtualenv at ${VENV}"
  python3 -m venv "${VENV}"
fi

"${VENV}/bin/pip" install --quiet --upgrade pip
"${VENV}/bin/pip" install --quiet -e "${PLUGIN_ROOT}/scripts"

if ! "${VENV}/bin/werkschau" --help >/dev/null 2>&1; then
  echo "Install completed but the 'werkschau' CLI does not run. This usually means" >&2
  echo "a broken virtualenv. Try: rm -rf '${VENV}' && bash $0" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "Werkschau installed, but 'gh' is not authenticated yet. Run 'gh auth login' before /werkschau."
else
  echo ""
  echo "Werkschau installed."
fi

echo ""
echo "Try it:"
echo "  /werkschau <github-username> --since 7d"
echo ""
echo "Or directly:"
echo "  ${VENV}/bin/werkschau extract --user <github-username> --since 7d"
