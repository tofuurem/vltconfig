#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

set -- dist/vltconfig-*.whl
if [[ "$#" -ne 1 || ! -f "$1" ]]; then
  echo "Expected exactly one vltconfig wheel in dist/." >&2
  exit 1
fi

wheel="$repo_root/$1"
uv run --isolated --no-project --with "$wheel" \
  python -I "$repo_root/tests/packaging/smoke_installed.py"
