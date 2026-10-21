#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
case "$PWD" in
  /mnt/[a-z]/*) printf 'Build from the WSL Linux filesystem, e.g. ~/cs527-llm-fl.\n' >&2; exit 2 ;;
esac
mkdir -p results/environment
image=cs527-fl:d4j2.0.0-gzoltar1.7.3
docker version > results/environment/docker-version.txt 2>&1
docker build --platform linux/amd64 --progress plain \
  --build-arg "LOCAL_UID=$(id -u)" --build-arg "LOCAL_GID=$(id -g)" \
  -f docker/Dockerfile -t "$image" . \
  2>&1 | tee results/environment/build.log
docker image inspect "$image" > results/environment/image-inspect.json
bash scripts/run.sh python3 scripts/inspect_environment.py
