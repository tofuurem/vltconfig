#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

container="vltconfig-integration-${PPID}-$$"
root_token="vltconfig-dev-only-root-token"

cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
  if [[ -n "${temporary_directory:-}" ]]; then
    rm -rf "$temporary_directory"
  fi
}
trap cleanup EXIT INT TERM

docker run --detach \
  --name "$container" \
  --publish 127.0.0.1::8200 \
  --env "VAULT_DEV_ROOT_TOKEN_ID=$root_token" \
  --env VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
  --env VAULT_ADDR=http://127.0.0.1:8200 \
  hashicorp/vault:2.0.3 server -dev >/dev/null

for _attempt in {1..40}; do
  if docker exec "$container" vault status >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! docker exec "$container" vault status >/dev/null 2>&1; then
  echo "Disposable Vault did not become ready in time." >&2
  exit 1
fi

port_mapping="$(docker port "$container" 8200/tcp)"
host_port="${port_mapping##*:}"
export VLTCONFIG_INTEGRATION_VAULT_ADDRESS="http://127.0.0.1:$host_port"
export VLTCONFIG_INTEGRATION_VAULT_ROOT_TOKEN="$root_token"

if [[ "${1:-}" == "--wheel-smoke" ]]; then
  set -- dist/vltconfig-*.whl
  if [[ "$#" -ne 1 || ! -f "$1" ]]; then
    echo "Expected exactly one vltconfig wheel in dist/." >&2
    exit 1
  fi
  wheel="$repo_root/$1"
  temporary_directory="$(mktemp -d)"
  wheel_environment="$temporary_directory/wheel"
  uv venv "$wheel_environment"
  uv pip install --python "$wheel_environment/bin/python" "$wheel"
  "$wheel_environment/bin/python" -I \
    "$repo_root/tests/packaging/smoke_cli_vault.py"
  exit 0
fi

test_targets=(tests/integration)
if (($# > 0)); then
  test_targets=("$@")
fi

uv run --frozen pytest "${test_targets[@]}" -q --no-cov
