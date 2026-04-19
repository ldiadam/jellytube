#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/Jellyfin.Plugin.YouTubeChannelCache"
OUTPUT_DIR="$PROJECT_DIR/bin/Release/net9.0"
REMOTE_PLUGIN_DIR="/var/lib/jellyfin/plugins/YouTubeChannelCache"
RESTART_MODE="systemd"
REMOTE_USER_HOST=""
CONTAINER_NAME="jellyfin"
RESTART_CMD=""

usage() {
  cat <<EOF
Usage:
  scripts/deploy-plugin.sh --host user@example.com [options]

Options:
  --host HOST              SSH target, for example root@server or adam@192.0.2.10.
  --path PATH              Remote plugin directory. Default: $REMOTE_PLUGIN_DIR
  --restart systemd        Restart with: sudo systemctl restart jellyfin. Default.
  --restart docker         Restart with: docker restart CONTAINER.
  --restart none           Upload only; do not restart Jellyfin.
  --container NAME         Docker container name for --restart docker. Default: jellyfin
  --restart-cmd CMD        Custom remote restart command.
  -h, --help               Show this help.

Examples:
  scripts/deploy-plugin.sh --host root@my-server
  scripts/deploy-plugin.sh --host adam@my-server --path /srv/jellyfin/config/plugins/YouTubeChannelCache --restart docker --container jellyfin
  scripts/deploy-plugin.sh --host adam@my-server --restart-cmd 'docker compose -f /opt/jellyfin/docker-compose.yml restart jellyfin'
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      REMOTE_USER_HOST="${2:-}"
      shift 2
      ;;
    --path)
      REMOTE_PLUGIN_DIR="${2:-}"
      shift 2
      ;;
    --restart)
      RESTART_MODE="${2:-}"
      shift 2
      ;;
    --container)
      CONTAINER_NAME="${2:-}"
      shift 2
      ;;
    --restart-cmd)
      RESTART_CMD="${2:-}"
      RESTART_MODE="custom"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ -z "$REMOTE_USER_HOST" ]; then
  echo "--host is required." >&2
  usage >&2
  exit 1
fi

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

ssh "$REMOTE_USER_HOST" "mkdir -p '$REMOTE_PLUGIN_DIR'"
scp "$OUTPUT_DIR/Jellyfin.Plugin.YouTubeChannelCache.dll" "$OUTPUT_DIR/meta.json" "$REMOTE_USER_HOST:$REMOTE_PLUGIN_DIR/"

case "$RESTART_MODE" in
  systemd)
    ssh "$REMOTE_USER_HOST" "sudo systemctl restart jellyfin"
    ;;
  docker)
    ssh "$REMOTE_USER_HOST" "docker restart '$CONTAINER_NAME'"
    ;;
  custom)
    ssh "$REMOTE_USER_HOST" "$RESTART_CMD"
    ;;
  none)
    ;;
  *)
    echo "Unknown restart mode: $RESTART_MODE" >&2
    exit 1
    ;;
esac

echo "Deployed to $REMOTE_USER_HOST:$REMOTE_PLUGIN_DIR"
