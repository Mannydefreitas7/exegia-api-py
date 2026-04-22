#!/usr/bin/env bash
# Build and publish the exegia package to the private PyPI index.
#
# Usage:
#   ./scripts/publish.sh             # build + publish
#   ./scripts/publish.sh --dry-run   # build only, no upload
#
# Required environment variables (or set in .env.publish):
#   UV_INDEX_EXEGIA_URL     install index URL, e.g. https://your-registry/simple/
#   EXEGIA_PYPI_PUBLISH_URL upload URL,  e.g. https://your-registry/upload/
#   EXEGIA_PYPI_USERNAME    registry username (use "__token__" for token auth)
#   EXEGIA_PYPI_TOKEN       registry token / password

set -euo pipefail

if [[ -f .env.publish ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env.publish
  set +o allexport
fi

DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ "$DRY_RUN" == "false" ]]; then
  : "${UV_INDEX_EXEGIA_URL:?Set UV_INDEX_EXEGIA_URL (see .env.publish.example)}"
  : "${EXEGIA_PYPI_PUBLISH_URL:?Set EXEGIA_PYPI_PUBLISH_URL}"
  : "${EXEGIA_PYPI_USERNAME:?Set EXEGIA_PYPI_USERNAME}"
  : "${EXEGIA_PYPI_TOKEN:?Set EXEGIA_PYPI_TOKEN}"
fi

rm -rf dist/
echo "→ Building exegia ..."
uv build --out-dir dist/
echo ""
ls -lh dist/

if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  echo "Dry run — skipping publish."
  exit 0
fi

echo ""
echo "→ Publishing to $EXEGIA_PYPI_PUBLISH_URL ..."
UV_PUBLISH_URL="$EXEGIA_PYPI_PUBLISH_URL" \
UV_PUBLISH_USERNAME="$EXEGIA_PYPI_USERNAME" \
UV_PUBLISH_PASSWORD="$EXEGIA_PYPI_TOKEN" \
  uv publish dist/*

echo ""
echo "Done."
