#!/bin/bash
PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${PLUGIN_ROOT}/.venv"

if [ ! -f "${VENV}/bin/werkschau" ]; then
  cat <<EOF
{"systemMessage": "Werkschau is installed but Python dependencies are not set up yet. When the user invokes /werkschau, run: bash ${PLUGIN_ROOT}/hooks/scripts/install.sh (takes about 15 seconds, creates a local venv at ${VENV}). Do not ask the user to run pip or python commands manually."}
EOF
fi
