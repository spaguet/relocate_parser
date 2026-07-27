#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

task="${1:-install-dev}"

case "$task" in
  install) pip install -e . ;;
  install-dev) pip install -e ".[dev]" ;;
  lint) ruff check src tests ;;
  format)
    ruff format src tests
    ruff check --fix src tests
    ;;
  typecheck) mypy src/relocate_helper ;;
  test) pytest tests -v ;;
  up) docker compose up --build -d ;;
  down) docker compose down ;;
  logs) docker compose logs -f app worker ;;
  *)
    echo "Unknown task: $task" >&2
    exit 1
    ;;
esac
