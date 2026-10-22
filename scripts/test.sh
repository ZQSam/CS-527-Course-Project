#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p results/tests
# Native WSL Python: setup parser wheels once with scripts/setup_python.py.
# Running tests needs no Docker, network, or API key.
PYTHONPATH="$PWD/.deps${PYTHONPATH:+:$PYTHONPATH}" python3 -m unittest discover -s tests -v \
  2>&1 | tee results/tests/unit-tests.log
(cd evaluation/person_c && python3 -m unittest discover -s tests -v) \
  2>&1 | tee results/tests/person-c-tests.log
