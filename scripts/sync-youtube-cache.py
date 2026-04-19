#!/usr/bin/env python3
"""Sync YouTube channel metadata into the plugin cache format."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def string_value(data: dict[str, Any], key: str, fallback: str = "") -> str:
    value = data.get(key)
    return value if isinstance(value, str) else fallback


def int_value(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    return value if isinstance(value, int) else None


def thumbnail_value(data: dict[str, Any]) -> str | None:
    thumbnail = data.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail:
        return thumbnail

    thumbnails = data.get("thumbnails")
    if not isinstance(thumbnails, list):
        return None

    urls = [item.get("url") for item in thumbnails if isinstance(item, dict)]
    urls = [url for url in urls if isinstance(url, str) and url]
    return urls[-1] if urls else None


def published_value(data: dict[str, Any]) -> str | None:
    timestamp = data.get("timestamp")
    if not isinstance(timestamp, int):
        return None

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def run_yt_dlp(yt_dlp: str, channel_url: str, playlist_end: int) -> dict[str, Any]:
    command = [
        yt_dlp,
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-end",
        str(playlist_end),
        channel_url,
    ]

    result = subprocess.run(command, capture_output=True, check=False, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"yt-dlp exited with {result.returncode}")

    return json.loads(result.stdout)


def convert_channel(raw: dict[str, Any], channel_url: str) -> dict[str, Any]:
    entries = raw.get("entries")
    if not isinstance(entries, list):
        entries = []

    videos = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        videos.append(
            {
                "videoId": string_value(entry, "id"),
                "title": string_value(entry, "title"),
                "description": string_value(entry, "description"),
                "publishedUtc": published_value(entry),
                "thumbnailPath": thumbnail_value(entry),
                "filePath": None,
                "durationSeconds": int_value(entry, "duration"),
            }
        )

    return {
        "channelId": string_value(raw, "channel_id", "unknown"),
        "title": string_value(raw, "title"),
        "description": string_value(raw, "description"),
        "url": channel_url,
        "thumbnailPath": thumbnail_value(raw),
        "lastUpdatedUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "videos": videos,
    }


def read_channel_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []

    if args.channels_file:
        for line in args.channels_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    urls.extend(args.channel_url)
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync YouTube channel metadata to Jellyfin plugin cache JSON.")
    parser.add_argument("--cache-dir", required=True, type=Path, help="Cache root directory, e.g. /cache/youtube-channels.")
    parser.add_argument("--channels-file", type=Path, help="Text file with one channel URL per line.")
    parser.add_argument("--channel-url", action="append", default=[], help="Channel URL. Can be passed more than once.")
    parser.add_argument("--yt-dlp", default="yt-dlp", help="yt-dlp executable path.")
    parser.add_argument("--playlist-end", default=100, type=int, help="Maximum videos to read per channel.")
    args = parser.parse_args()

    channel_urls = read_channel_urls(args)
    if not channel_urls:
        print("No channel URLs supplied.", file=sys.stderr)
        return 2

    args.cache_dir.mkdir(parents=True, exist_ok=True)

    for channel_url in channel_urls:
        print(f"Refreshing {channel_url}", file=sys.stderr)
        raw = run_yt_dlp(args.yt_dlp, channel_url, args.playlist_end)
        channel = convert_channel(raw, channel_url)
        channel_id = channel["channelId"] or "unknown"

        channel_dir = args.cache_dir / channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)
        channel_json = channel_dir / "channel.json"
        channel_json.write_text(json.dumps(channel, indent=2), encoding="utf-8")
        print(f"Wrote {channel_json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
