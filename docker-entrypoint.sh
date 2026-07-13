#!/bin/sh
set -e

mode="${1:-eval}"

case "$mode" in
  eval|evaluator)
    if [ "$#" -gt 0 ]; then
      shift
    fi
    exec python evaluator.py "$@"
    ;;
  api)
    if [ "$#" -gt 0 ]; then
      shift
    fi
    exec uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
    ;;
  batch)
    if [ "$#" -gt 0 ]; then
      shift
    fi
    exec python app.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
