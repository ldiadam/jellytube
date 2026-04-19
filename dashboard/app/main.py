from __future__ import annotations

import asyncio
import json
import os
import signal
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


CONFIG_PATH = Path(os.environ.get("YOUTUBE_DASHBOARD_CONFIG", "/config/config.json"))
LOG_PATH = Path(os.environ.get("YOUTUBE_DASHBOARD_LOG", "/config/sync.log"))
OUTPUT_DIR = Path(os.environ.get("YOUTUBE_OUTPUT_DIR", "/youtube"))
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Channel(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    url: str
    label: str = ""
    enabled: bool = True


class AppConfig(BaseModel):
    channels: list[Channel] = Field(default_factory=list)
    intervalHours: float = 6
    autoSync: bool = True
    cookiesPath: str = "/youtube/youtube-cookies.txt"
    archivePath: str = "/youtube/archive.txt"
    outputTemplate: str = "/youtube/%(channel|Unknown Channel)s/%(upload_date>%Y)s/%(upload_date>%Y-%m-%d)s - %(title).180B [%(id)s].%(ext)s"
    formatSelector: str = "bv*+ba/b"
    playlistEnd: int = 0
    sleepSeconds: int = 0


class ConfigUpdate(BaseModel):
    channels: list[Channel] | None = None
    intervalHours: float | None = None
    autoSync: bool | None = None
    cookiesPath: str | None = None
    archivePath: str | None = None
    outputTemplate: str | None = None
    formatSelector: str | None = None
    playlistEnd: int | None = None
    sleepSeconds: int | None = None


class ChannelCreate(BaseModel):
    url: str
    label: str = ""
    enabled: bool = True


class CookiesPayload(BaseModel):
    content: str


class RuntimeState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.process: asyncio.subprocess.Process | None = None
        self.current_channel: str | None = None
        self.running = False
        self.stop_requested = False
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None
        self.last_success: bool | None = None
        self.last_error: str | None = None
        self.next_run_at: datetime | None = None
        self.last_run_seconds: float | None = None


state = RuntimeState()
app = FastAPI(title="YouTube Cache Sync Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def ensure_dirs() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        config = AppConfig()
        save_config(config)
        return config

    return AppConfig.model_validate_json(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: AppConfig) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")


def append_log(line: str) -> None:
    ensure_dirs()
    stamp = utc_now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {line.rstrip()}\n")


def tail_log(max_lines: int = 400) -> str:
    if not LOG_PATH.exists():
        return ""

    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def file_count() -> dict[str, int]:
    if not OUTPUT_DIR.exists():
        return {"videos": 0, "metadata": 0, "thumbnails": 0}

    video_exts = {".mp4", ".mkv", ".webm", ".m4v"}
    thumb_exts = {".jpg", ".jpeg", ".png", ".webp"}
    counts = {"videos": 0, "metadata": 0, "thumbnails": 0}
    for path in OUTPUT_DIR.rglob("*"):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        if suffix in video_exts:
            counts["videos"] += 1
        elif suffix == ".json":
            counts["metadata"] += 1
        elif suffix in thumb_exts:
            counts["thumbnails"] += 1

    return counts


def cookies_status(config: AppConfig) -> dict[str, Any]:
    path = Path(config.cookiesPath)
    exists = path.exists()
    first_line = ""
    if exists:
        with suppress(Exception):
            first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]

    return {
        "path": config.cookiesPath,
        "exists": exists,
        "looksNetscape": first_line.startswith("# Netscape HTTP Cookie File"),
        "size": path.stat().st_size if exists else 0,
        "modifiedAt": iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)) if exists else None,
    }


def build_command(config: AppConfig, channel: Channel) -> list[str]:
    command = [
        "yt-dlp",
        "--download-archive",
        config.archivePath,
        "--ignore-errors",
        "--no-overwrites",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--embed-metadata",
        "--js-runtimes",
        "node:/usr/local/bin/node",
        "--remote-components",
        "ejs:github",
        "-f",
        config.formatSelector,
        "--merge-output-format",
        "mp4",
        "-o",
        config.outputTemplate,
    ]

    if config.sleepSeconds > 0:
        command.extend(["--sleep-requests", str(config.sleepSeconds)])

    if config.playlistEnd > 0:
        command.extend(["--playlist-end", str(config.playlistEnd)])

    cookies_path = Path(config.cookiesPath)
    if cookies_path.exists():
        command.extend(["--cookies", config.cookiesPath])

    command.append(channel.url)
    return command


async def pipe_stream(stream: asyncio.StreamReader, prefix: str) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break

        append_log(f"{prefix}{line.decode(errors='replace').rstrip()}")


async def run_sync(reason: str) -> None:
    async with state.lock:
        if state.running:
            raise HTTPException(status_code=409, detail="Sync is already running")

        state.running = True
        state.stop_requested = False
        state.last_started_at = utc_now()
        state.last_finished_at = None
        state.last_success = None
        state.last_error = None
        state.last_run_seconds = None

    config = load_config()
    enabled_channels = [channel for channel in config.channels if channel.enabled]
    append_log(f"Sync started: {reason}. Enabled channels: {len(enabled_channels)}")
    started = utc_now()
    success = True

    try:
        if not enabled_channels:
            append_log("No enabled channels configured.")

        for channel in enabled_channels:
            if state.stop_requested:
                append_log("Stop requested before next channel.")
                success = False
                break

            state.current_channel = channel.url
            append_log(f"Refreshing {channel.label or channel.url}")
            command = build_command(config, channel)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            state.process = process

            stdout_task = asyncio.create_task(pipe_stream(process.stdout, ""))
            stderr_task = asyncio.create_task(pipe_stream(process.stderr, ""))
            exit_code = await process.wait()
            await asyncio.gather(stdout_task, stderr_task)

            state.process = None
            if exit_code != 0:
                success = False
                append_log(f"Channel finished with exit code {exit_code}: {channel.url}")
            else:
                append_log(f"Channel finished: {channel.url}")

        append_log("Sync finished.")
    except Exception as exc:
        success = False
        state.last_error = str(exc)
        append_log(f"Sync failed: {exc}")
    finally:
        finished = utc_now()
        config = load_config()
        state.running = False
        state.current_channel = None
        state.process = None
        state.last_finished_at = finished
        state.last_success = success
        state.last_run_seconds = (finished - started).total_seconds()
        if config.autoSync:
            state.next_run_at = finished + timedelta(hours=config.intervalHours)
        else:
            state.next_run_at = None


async def scheduler_loop() -> None:
    await asyncio.sleep(2)
    while True:
        config = load_config()
        if config.autoSync and not state.running:
            if state.next_run_at is None:
                state.next_run_at = utc_now()

            if utc_now() >= state.next_run_at:
                try:
                    asyncio.create_task(run_sync("scheduled"))
                except HTTPException:
                    pass

        await asyncio.sleep(10)


@app.on_event("startup")
async def startup() -> None:
    ensure_dirs()
    config = load_config()
    if config.autoSync:
        state.next_run_at = utc_now()
    append_log("Dashboard started.")
    asyncio.create_task(scheduler_loop())


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def get_config() -> AppConfig:
    return load_config()


@app.put("/api/config")
async def update_config(update: ConfigUpdate) -> AppConfig:
    config = load_config()
    data = update.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(config, key, value)

    if config.intervalHours <= 0:
        raise HTTPException(status_code=400, detail="intervalHours must be greater than 0")

    save_config(config)
    if config.autoSync and not state.running:
        state.next_run_at = utc_now() + timedelta(hours=config.intervalHours)
    elif not config.autoSync:
        state.next_run_at = None

    append_log("Configuration updated.")
    return config


@app.post("/api/channels")
async def add_channel(channel: ChannelCreate) -> Channel:
    config = load_config()
    created = Channel(url=channel.url.strip(), label=channel.label.strip(), enabled=channel.enabled)
    if not created.url:
        raise HTTPException(status_code=400, detail="Channel URL is required")

    config.channels.append(created)
    save_config(config)
    append_log(f"Added channel: {created.url}")
    return created


@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: str) -> dict[str, bool]:
    config = load_config()
    original_count = len(config.channels)
    config.channels = [channel for channel in config.channels if channel.id != channel_id]
    if len(config.channels) == original_count:
        raise HTTPException(status_code=404, detail="Channel not found")

    save_config(config)
    append_log(f"Deleted channel: {channel_id}")
    return {"ok": True}


@app.post("/api/sync/start")
async def start_sync() -> dict[str, bool]:
    asyncio.create_task(run_sync("manual"))
    return {"ok": True}


@app.post("/api/sync/stop")
async def stop_sync() -> dict[str, bool]:
    state.stop_requested = True
    if state.process and state.process.returncode is None:
        with suppress(ProcessLookupError):
            os.killpg(state.process.pid, signal.SIGTERM)

    append_log("Stop requested.")
    return {"ok": True}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    config = load_config()
    return {
        "running": state.running,
        "currentChannel": state.current_channel,
        "lastStartedAt": iso(state.last_started_at),
        "lastFinishedAt": iso(state.last_finished_at),
        "lastSuccess": state.last_success,
        "lastError": state.last_error,
        "lastRunSeconds": state.last_run_seconds,
        "nextRunAt": iso(state.next_run_at),
        "autoSync": config.autoSync,
        "intervalHours": config.intervalHours,
        "counts": file_count(),
        "cookies": cookies_status(config),
    }


@app.get("/api/logs")
async def get_logs(lines: int = 400) -> dict[str, str]:
    return {"logs": tail_log(lines)}


@app.post("/api/cookies")
async def save_cookies(payload: CookiesPayload) -> dict[str, Any]:
    content = payload.content.strip()
    if not content.startswith("# Netscape HTTP Cookie File"):
        raise HTTPException(status_code=400, detail="Cookies must be Netscape format, starting with '# Netscape HTTP Cookie File'")

    config = load_config()
    path = Path(config.cookiesPath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")
    append_log(f"Cookies updated at {config.cookiesPath}")
    return cookies_status(config)
