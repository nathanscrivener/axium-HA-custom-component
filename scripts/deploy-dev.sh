#!/usr/bin/env bash
# Deploy the Axium integration from this repo (development branch working tree)
# to the live Home Assistant custom_components folder.
#
# Usage: ./scripts/deploy-dev.sh
#
# Notes:
# - HA runs in Docker with /home/nathan/homeassistant bind-mounted as /config,
#   so deployment is a file copy (symlinks cannot cross the mount boundary).
# - HA only loads new code on restart. This script never restarts HA —
#   the user approves restarts explicitly.
set -euo pipefail

SRC="/home/nathan/axium/HA-Component"
DEST="/home/nathan/homeassistant/custom_components/axium"

# Files that must not be copied into the live config
EXCLUDES=(
  --exclude=.git
  --exclude=__pycache__
  --exclude=.cursor
  --exclude='~'
  --exclude=scripts
  --exclude=backups
  --exclude=memory-bank
)

# Clean strays from previous deploys
rm -rf "${DEST}/__pycache__" "${DEST}/.cursor" "${DEST}/~"

# Copy component files (only the integration payloads)
for f in "${SRC}"/*.py "${SRC}"/manifest.json; do
  cp "$f" "${DEST}/"
done
# Copy supporting dirs if present
[ -d "${SRC}/translations" ] && cp -r "${SRC}/translations/." "${DEST}/translations/"

# Verify sync
if diff -r --exclude=.git --exclude=__pycache__ "${SRC}" "${DEST}" > /tmp/axium-deploy-diff.txt 2>&1; then
  echo "DEPLOY_IN_SYNC"
else
  echo "WARNING: differences remain after deploy:"
  cat /tmp/axium-deploy-diff.txt
  exit 1
fi

echo
echo "Deployed current branch: $(git -C "${SRC}" rev-parse --abbrev-ref HEAD) @ $(git -C "${SRC}" rev-parse --short HEAD)"
echo "HA must be restarted to load the new code (restart requires user approval)."