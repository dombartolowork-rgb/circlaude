#!/bin/bash
# Rebuild Orbit's WhatsApp bridge for Windows and Apple Silicon Macs.
#
# Usage:
#   tools/whatsapp/build.sh            rebuild from the source as it is
#   tools/whatsapp/build.sh --update   move to the latest whatsmeow first
#
# Run --update when anyone's pairing page says "This needs an update": that is
# WhatsApp retiring the whatsmeow version we ship (a 405, "client outdated").
# Then bump the plugin version, commit, and everyone gets it on their next
# Orbit update. Their link restarts on the new build at the next wa-connect or
# login.
#
# Needs Go (~/.local/go/bin/go on Dom's Mac). No C compiler: the database is
# modernc.org/sqlite, pure Go, which is what makes the Windows build possible
# from a Mac.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GO="${GO:-$(command -v go || echo "$HOME/.local/go/bin/go")}"
OUT="$HERE/bin"

cd "$HERE/bridge"

if [ "${1:-}" = "--update" ]; then
  "$GO" get go.mau.fi/whatsmeow@latest
  "$GO" mod tidy
fi

export CGO_ENABLED=0
"$GO" vet .

mkdir -p "$OUT"
GOOS=windows GOARCH=amd64 "$GO" build -trimpath -ldflags "-s -w -H windowsgui" \
  -o "$OUT/whatsapp-bridge-windows-amd64.exe" .
GOOS=darwin GOARCH=arm64 "$GO" build -trimpath -ldflags "-s -w" \
  -o "$OUT/whatsapp-bridge-darwin-arm64" .

ls -la "$OUT"
grep 'go.mau.fi/whatsmeow ' go.mod
