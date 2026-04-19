#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/Jellyfin.Plugin.YouTubeChannelCache"
OUTPUT_DIR="$PROJECT_DIR/bin/Release/net9.0"
REPO_DIR="$ROOT_DIR/plugin-repository"
PLUGIN_NAME="Jellyfin.Plugin.YouTubeChannelCache"
VERSION="0.1.0.0"
ZIP_NAME="${PLUGIN_NAME}_${VERSION}.zip"
BASE_URL="${1:-}"

if [ -z "$BASE_URL" ]; then
  echo "Usage: scripts/build-plugin-repository.sh https://owner.github.io/repo" >&2
  exit 1
fi

BASE_URL="${BASE_URL%/}"

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

rm -rf "$REPO_DIR"
mkdir -p "$REPO_DIR"

(cd "$OUTPUT_DIR" && zip -q -r "$REPO_DIR/$ZIP_NAME" "${PLUGIN_NAME}.dll" meta.json)

if command -v md5sum >/dev/null 2>&1; then
  CHECKSUM="$(md5sum "$REPO_DIR/$ZIP_NAME" | awk '{print $1}')"
elif command -v md5 >/dev/null 2>&1; then
  CHECKSUM="$(md5 -q "$REPO_DIR/$ZIP_NAME")"
else
  echo "No md5sum or md5 command available." >&2
  exit 1
fi

cat > "$REPO_DIR/manifest.json" <<EOF
[
  {
    "guid": "5d3f0fcb-4412-4f8f-b7b6-d7ab2cd2a101",
    "name": "YouTube Channel Cache",
    "description": "Reads locally cached YouTube channel metadata and video manifests for Jellyfin.",
    "overview": "Local YouTube channel metadata cache reader for Jellyfin.",
    "owner": "rinaldiadam",
    "category": "Metadata",
    "versions": [
      {
        "version": "$VERSION",
        "changelog": "Initial local-cache metadata plugin scaffold for Jellyfin 10.11.",
        "targetAbi": "10.11.0.0",
        "sourceUrl": "$BASE_URL/$ZIP_NAME",
        "checksum": "$CHECKSUM",
        "timestamp": "2026-04-19T00:00:00Z"
      }
    ]
  }
]
EOF

cat > "$REPO_DIR/index.html" <<EOF
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>YouTube Channel Cache Jellyfin Plugin Repository</title>
  </head>
  <body>
    <h1>YouTube Channel Cache Jellyfin Plugin Repository</h1>
    <p>Use this URL in Jellyfin plugin repositories:</p>
    <pre>$BASE_URL/manifest.json</pre>
    <p><a href="manifest.json">manifest.json</a></p>
  </body>
</html>
EOF

echo "$REPO_DIR/manifest.json"
