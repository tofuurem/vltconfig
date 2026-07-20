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
temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT INT TERM

base_environment="$temporary_directory/base"
yaml_environment="$temporary_directory/yaml"

uv venv "$base_environment"
uv pip install --python "$base_environment/bin/python" "$wheel"
"$base_environment/bin/python" -I "$repo_root/tests/packaging/smoke_installed.py"

uv venv "$yaml_environment"
uv pip install --python "$yaml_environment/bin/python" \
  "$wheel" "ruamel.yaml==0.19.1"
"$yaml_environment/bin/python" -I \
  "$repo_root/tests/packaging/smoke_yaml_installed.py"
