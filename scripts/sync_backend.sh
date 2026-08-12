#!/usr/bin/env bash
# backend/app.py is the single source of truth. api/app.py is a required-by-
# Vercel copy of it (see api/README or the root README's "Project structure"
# section for why it can't just be imported across directories — this
# project's vercel.json uses the legacy `builds` config, which only bundles
# each builder's own output, not sibling directories).
#
# Run this after editing backend/app.py, before committing:
#   ./scripts/sync_backend.sh
#
# CI (.github/workflows/tests.yml) runs this same script in --check mode and
# fails the build if the two files have drifted, so a forgotten sync can't
# silently reach main.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--check" ]]; then
  if ! diff -q backend/app.py api/app.py > /dev/null 2>&1; then
    echo "api/app.py is out of sync with backend/app.py."
    echo "Run ./scripts/sync_backend.sh (without --check) and commit the result."
    exit 1
  fi
  echo "api/app.py matches backend/app.py."
else
  cp backend/app.py api/app.py
  echo "Copied backend/app.py -> api/app.py"
fi
