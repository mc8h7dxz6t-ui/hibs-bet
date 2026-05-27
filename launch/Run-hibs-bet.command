#!/bin/bash
# Double-click this file in Finder to launch hibs-bet.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/HibsBet.command"
