#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

expected_version="$(
  python -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])'
)"
wheel="$repo_root/dist/vltconfig-$expected_version-py3-none-any.whl"
if [[ ! -f "$wheel" ]]; then
  echo "Expected the vltconfig $expected_version wheel in dist/." >&2
  exit 1
fi

export VLTCONFIG_EXPECTED_VERSION="$expected_version"
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
