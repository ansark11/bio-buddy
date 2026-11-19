#!/usr/bin/env bash
# Fast checks until real tests exist; exits non-zero if any fail. This is <TEST_COMMAND>.
# Backend: every module compiles. Frontend: TypeScript type-checks.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== backend compile"
(cd backend && venv/bin/python -m compileall -q app)
echo "== frontend type-check"
(cd frontend && npx --no-install tsc --noEmit)
echo "== all checks passed"
