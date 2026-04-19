#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/Jellyfin.Plugin.YouTubeChannelCache"
OUTPUT_DIR="$PROJECT_DIR/bin/Release/net9.0"
DIST_DIR="$ROOT_DIR/dist"
PACKAGE_NAME="Jellyfin.Plugin.YouTubeChannelCache"
PACKAGE_PATH="$DIST_DIR/$PACKAGE_NAME.zip"

mkdir -p "$DIST_DIR"

if command -v dotnet >/dev/null 2>&1; then
  (cd "$PROJECT_DIR" && dotnet restore && dotnet build -c Release --no-restore)
elif command -v docker >/dev/null 2>&1; then
  docker run --rm \
    -v "$ROOT_DIR:/work" \
    -w /work/Jellyfin.Plugin.YouTubeChannelCache \
    mcr.microsoft.com/dotnet/sdk:9.0 \
    sh -lc "dotnet restore && dotnet build -c Release --no-restore"
else
  echo "Neither dotnet nor docker is available. Install one of them and rerun." >&2
  exit 1
fi

rm -f "$PACKAGE_PATH"
(cd "$OUTPUT_DIR" && zip -q -r "$PACKAGE_PATH" Jellyfin.Plugin.YouTubeChannelCache.dll meta.json)

echo "$PACKAGE_PATH"
