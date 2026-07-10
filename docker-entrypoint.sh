#!/bin/sh
set -e

mode="${1:-api}"

case "$mode" in
  api)
    if [ "$#" -gt 0 ]; then
      shift
    fi
    exec uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
    ;;
  batch)
    shift
    exec python app.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
