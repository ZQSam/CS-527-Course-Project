#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
case "$PWD" in
  /mnt/[a-z]/*) printf 'Run project commands from the WSL Linux filesystem.\n' >&2; exit 2 ;;
esac
exec docker run --rm --init --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD,target=/workspace" --workdir /workspace \
  --env TZ=America/Los_Angeles \
  cs527-fl:d4j2.0.0-gzoltar1.7.3 "$@"
