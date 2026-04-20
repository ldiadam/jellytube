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
COOKIES_DIR = Path(os.environ.get("YOUTUBE_COOKIES_DIR", "/config/cookies"))


class Channel(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    url: str
    label: str = ""
    enabled: bool = True
    playlistEnd: int = 0
    formatSelector: str = ""
    lastStartedAt: str | None = None
    lastFinishedAt: str | None = None
    lastSuccess: bool | None = None
    lastExitCode: int | None = None


class CookieProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    path: str
    active: bool = False
    createdAt: str = ""
    updatedAt: str = ""
    size: int = 0
    looksNetscape: bool = False


class AppConfig(BaseModel):
    channels: list[Channel] = Field(default_factory=list)
    cookies: list[CookieProfile] = Field(default_factory=list)
    activeCookieId: str | None = None
    intervalHours: float = 6
    autoSync: bool = True
    archivePath: str = "/youtube/archive.txt"
    outputTemplate: str = "/youtube/%(channel|Unknown Channel)s/%(upload_date>%Y)s/%(upload_date>%Y-%m-%d)s - %(title).180B [%(id)s].%(ext)s"
    formatSelector: str = "bv*+ba/b"
    playlistEnd: int = 0
    sleepSeconds: int = 0
    embedMetadata: bool = True
    writeInfoJson: bool = True
    writeThumbnail: bool = True
    convertThumbnails: bool = True
    mergeOutputFormat: str = "mp4"
    maxRecentFiles: int = 24
    skipUpcomingPremieres: bool = True
    ignorePremiereErrors: bool = True


class ConfigUpdate(BaseModel):
    channels: list[Channel] | None = None
    cookies: list[CookieProfile] | None = None
    activeCookieId: str | None = None
    intervalHours: float | None = None
    autoSync: bool | None = None
    archivePath: str | None = None
    outputTemplate: str | None = None
    formatSelector: str | None = None
    playlistEnd: int | None = None
    sleepSeconds: int | None = None
    embedMetadata: bool | None = None
    writeInfoJson: bool | None = None
    writeThumbnail: bool | None = None
    convertThumbnails: bool | None = None
    mergeOutputFormat: str | None = None
    maxRecentFiles: int | None = None
    skipUpcomingPremieres: bool | None = None
    ignorePremiereErrors: bool | None = None


class ChannelCreate(BaseModel):
    url: str
    label: str = ""
    enabled: bool = True
    playlistEnd: int = 0
    formatSelector: str = ""


class ChannelUpdate(BaseModel):
    url: str | None = None
    label: str | None = None
    enabled: bool | None = None
    playlistEnd: int | None = None
    formatSelector: str | None = None


class CookiesPayload(BaseModel):
    name: str
    content: str
    activate: bool = True


class CookieUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    activate: bool | None = None


class SyncStartPayload(BaseModel):
    channelId: str | None = None


class RuntimeState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.process: asyncio.subprocess.Process | None = None
        self.current_channel: str | None = None
        self.current_channel_id: str | None = None
        self.running = False
        self.stop_requested = False
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None
        self.last_success: bool | None = None
        self.last_error: str | None = None
        self.next_run_at: datetime | None = None
        self.last_run_seconds: float | None = None


state = RuntimeState()
app = FastAPI(title="JellyTube Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def now_iso() -> str:
    return utc_now().isoformat()


def ensure_dirs() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)


def profile_path(profile_id: str) -> Path:
    return COOKIES_DIR / f"{profile_id}.txt"


def looks_netscape(path: Path) -> bool:
    if not path.exists():
        return False

    with suppress(Exception):
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        return first_line.startswith("# Netscape HTTP Cookie File")

    return False


def refresh_cookie_profile(profile: CookieProfile) -> CookieProfile:
    path = Path(profile.path)
    profile.size = path.stat().st_size if path.exists() else 0
    profile.looksNetscape = looks_netscape(path)
    return profile


def normalize_config(config: AppConfig) -> AppConfig:
    for cookie in config.cookies:
        refresh_cookie_profile(cookie)
        cookie.active = cookie.id == config.activeCookieId

    if config.activeCookieId and not any(cookie.id == config.activeCookieId for cookie in config.cookies):
        config.activeCookieId = None

    return config


def load_config() -> AppConfig:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        config = AppConfig()
        save_config(config)
        return config

    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    legacy_cookies_path = raw.get("cookiesPath")
    needs_save = False
    if "skipUpcomingPremieres" not in raw:
        raw["skipUpcomingPremieres"] = True
        needs_save = True
    if "ignorePremiereErrors" not in raw:
        raw["ignorePremiereErrors"] = True
        needs_save = True

    config = AppConfig.model_validate(raw)
    if legacy_cookies_path and not config.cookies:
        profile = CookieProfile(
            name="Migrated YouTube cookies",
            path=str(legacy_cookies_path),
            active=True,
            createdAt=now_iso(),
            updatedAt=now_iso(),
        )
        refresh_cookie_profile(profile)
        config.cookies.append(profile)
        config.activeCookieId = profile.id
        needs_save = True

    if needs_save:
        save_config(config)

    return normalize_config(config)


def save_config(config: AppConfig) -> None:
    ensure_dirs()
    config = normalize_config(config)
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


def media_inventory(max_recent: int) -> dict[str, Any]:
    if not OUTPUT_DIR.exists():
        return {"counts": {"videos": 0, "metadata": 0, "thumbnails": 0, "other": 0}, "recent": [], "bytes": 0}

    video_exts = {".mp4", ".mkv", ".webm", ".m4v"}
    thumb_exts = {".jpg", ".jpeg", ".png", ".webp"}
    counts = {"videos": 0, "metadata": 0, "thumbnails": 0, "other": 0}
    recent: list[dict[str, Any]] = []
    total_bytes = 0

    for path in OUTPUT_DIR.rglob("*"):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        stat = path.stat()
        total_bytes += stat.st_size
        if suffix in video_exts:
            kind = "video"
            counts["videos"] += 1
        elif suffix == ".json":
            kind = "metadata"
            counts["metadata"] += 1
        elif suffix in thumb_exts:
            kind = "thumbnail"
            counts["thumbnails"] += 1
        else:
            kind = "other"
            counts["other"] += 1

        recent.append(
            {
                "path": str(path.relative_to(OUTPUT_DIR)),
                "kind": kind,
                "size": stat.st_size,
                "modifiedAt": iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)),
            }
        )

    recent.sort(key=lambda item: item["modifiedAt"] or "", reverse=True)
    return {"counts": counts, "recent": recent[:max_recent], "bytes": total_bytes}


def active_cookie(config: AppConfig) -> CookieProfile | None:
    if not config.activeCookieId:
        return None

    return next((cookie for cookie in config.cookies if cookie.id == config.activeCookieId), None)


def cookies_status(config: AppConfig) -> dict[str, Any]:
    cookie = active_cookie(config)
    if cookie is None:
        return {
            "activeId": None,
            "name": None,
            "path": None,
            "exists": False,
            "looksNetscape": False,
            "size": 0,
            "modifiedAt": None,
            "profiles": [cookie.model_dump() for cookie in config.cookies],
        }

    path = Path(cookie.path)
    return {
        "activeId": cookie.id,
        "name": cookie.name,
        "path": cookie.path,
        "exists": path.exists(),
        "looksNetscape": looks_netscape(path),
        "size": path.stat().st_size if path.exists() else 0,
        "modifiedAt": iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)) if path.exists() else None,
        "profiles": [profile.model_dump() for profile in config.cookies],
    }


def build_command(config: AppConfig, channel: Channel) -> list[str]:
    format_selector = channel.formatSelector.strip() or config.formatSelector
    playlist_end = channel.playlistEnd or config.playlistEnd
    command = [
        "yt-dlp",
        "--download-archive",
        config.archivePath,
        "--ignore-errors",
        "--no-overwrites",
        "--js-runtimes",
        "node:/usr/local/bin/node",
        "--remote-components",
        "ejs:github",
        "-f",
        format_selector,
        "--merge-output-format",
        config.mergeOutputFormat,
        "-o",
        config.outputTemplate,
    ]

    if config.writeInfoJson:
        command.append("--write-info-json")
    if config.writeThumbnail:
        command.append("--write-thumbnail")
    if config.convertThumbnails:
        command.extend(["--convert-thumbnails", "jpg"])
    if config.embedMetadata:
        command.append("--embed-metadata")
    if config.sleepSeconds > 0:
        command.extend(["--sleep-requests", str(config.sleepSeconds)])
    if playlist_end > 0:
        command.extend(["--playlist-end", str(playlist_end)])
    if config.skipUpcomingPremieres:
        command.extend(["--match-filter", "live_status = not_live"])

    cookie = active_cookie(config)
    if cookie and Path(cookie.path).exists():
        command.extend(["--cookies", cookie.path])

    command.append(channel.url)
    return command


def is_premiere_error(line: str) -> bool:
    normalized = line.lower()
    return (
        "premieres in" in normalized
        or "premiere has not started" in normalized
        or "this live event will begin" in normalized
        or "live event will begin" in normalized
    )


def errors_are_ignorable_premieres(error_lines: list[str]) -> bool:
    if not error_lines:
        return False

    return all(is_premiere_error(line) for line in error_lines)


async def pipe_stream(stream: asyncio.StreamReader, prefix: str, error_lines: list[str] | None = None) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break

        decoded = line.decode(errors="replace").rstrip()
        if decoded.startswith("ERROR:") and error_lines is not None:
            error_lines.append(decoded)

        append_log(f"{prefix}{decoded}")


def update_channel_result(channel_id: str, success: bool, exit_code: int | None) -> None:
    config = load_config()
    for channel in config.channels:
        if channel.id == channel_id:
            channel.lastFinishedAt = now_iso()
            channel.lastSuccess = success
            channel.lastExitCode = exit_code
            break

    save_config(config)


async def run_sync(reason: str, channel_id: str | None = None) -> None:
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
    if channel_id:
        enabled_channels = [channel for channel in config.channels if channel.id == channel_id]
        if not enabled_channels:
            state.running = False
            raise HTTPException(status_code=404, detail="Channel not found")
    else:
        enabled_channels = [channel for channel in config.channels if channel.enabled]

    append_log(f"Sync started: {reason}. Channels: {len(enabled_channels)}")
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

            config = load_config()
            state.current_channel = channel.url
            state.current_channel_id = channel.id
            channel.lastStartedAt = now_iso()
            for configured in config.channels:
                if configured.id == channel.id:
                    configured.lastStartedAt = channel.lastStartedAt
                    break
            save_config(config)

            append_log(f"Refreshing {channel.label or channel.url}")
            command = build_command(config, channel)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            state.process = process

            error_lines: list[str] = []
            stdout_task = asyncio.create_task(pipe_stream(process.stdout, "", error_lines))
            stderr_task = asyncio.create_task(pipe_stream(process.stderr, "", error_lines))
            exit_code = await process.wait()
            await asyncio.gather(stdout_task, stderr_task)

            state.process = None
            premiere_only_failure = (
                exit_code != 0
                and config.ignorePremiereErrors
                and errors_are_ignorable_premieres(error_lines)
            )
            channel_success = exit_code == 0 or premiere_only_failure
            update_channel_result(channel.id, channel_success, exit_code)
            if premiere_only_failure:
                append_log(f"Ignored upcoming premiere errors for channel: {channel.url}")
                append_log(f"Channel finished: {channel.url}")
            elif not channel_success:
                success = False
                append_log(f"Channel finished with exit code {exit_code}: {channel.url}")
            else:
                append_log(f"Channel finished: {channel.url}")

        append_log("Sync finished.")
    except HTTPException:
        raise
    except Exception as exc:
        success = False
        state.last_error = str(exc)
        append_log(f"Sync failed: {exc}")
    finally:
        finished = utc_now()
        config = load_config()
        state.running = False
        state.current_channel = None
        state.current_channel_id = None
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
                asyncio.create_task(run_sync("scheduled"))

        await asyncio.sleep(10)


@app.on_event("startup")
async def startup() -> None:
    ensure_dirs()
    config = load_config()
    if config.autoSync:
        state.next_run_at = utc_now() + timedelta(hours=config.intervalHours)
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
    if config.maxRecentFiles < 1:
        raise HTTPException(status_code=400, detail="maxRecentFiles must be at least 1")

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
    created = Channel(
        url=channel.url.strip(),
        label=channel.label.strip(),
        enabled=channel.enabled,
        playlistEnd=channel.playlistEnd,
        formatSelector=channel.formatSelector.strip(),
    )
    if not created.url:
        raise HTTPException(status_code=400, detail="Channel URL is required")

    config.channels.append(created)
    save_config(config)
    append_log(f"Added channel: {created.url}")
    return created


@app.put("/api/channels/{channel_id}")
async def update_channel(channel_id: str, update: ChannelUpdate) -> Channel:
    config = load_config()
    channel = next((item for item in config.channels if item.id == channel_id), None)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    data = update.model_dump(exclude_unset=True)
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(channel, key, value)

    if not channel.url:
        raise HTTPException(status_code=400, detail="Channel URL is required")

    save_config(config)
    append_log(f"Updated channel: {channel.url}")
    return channel


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
async def start_sync(payload: SyncStartPayload | None = None) -> dict[str, bool]:
    channel_id = payload.channelId if payload else None
    if state.running:
        raise HTTPException(status_code=409, detail="Sync is already running")

    if channel_id and not any(channel.id == channel_id for channel in load_config().channels):
        raise HTTPException(status_code=404, detail="Channel not found")

    asyncio.create_task(run_sync("manual", channel_id=channel_id))
    return {"ok": True}


@app.post("/api/sync/stop")
async def stop_sync() -> dict[str, bool]:
    state.stop_requested = True
    if state.process and state.process.returncode is None:
        with suppress(ProcessLookupError):
            os.killpg(state.process.pid, signal.SIGTERM)

    append_log("Stop requested.")
    return {"ok": True}


@app.post("/api/schedule/skip")
async def skip_next_run() -> dict[str, str | None]:
    config = load_config()
    if not config.autoSync:
        state.next_run_at = None
    else:
        state.next_run_at = utc_now() + timedelta(hours=config.intervalHours)

    append_log("Next scheduled run skipped/reset.")
    return {"nextRunAt": iso(state.next_run_at)}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    config = load_config()
    inventory = media_inventory(config.maxRecentFiles)
    return {
        "running": state.running,
        "currentChannel": state.current_channel,
        "currentChannelId": state.current_channel_id,
        "lastStartedAt": iso(state.last_started_at),
        "lastFinishedAt": iso(state.last_finished_at),
        "lastSuccess": state.last_success,
        "lastError": state.last_error,
        "lastRunSeconds": state.last_run_seconds,
        "nextRunAt": iso(state.next_run_at),
        "autoSync": config.autoSync,
        "intervalHours": config.intervalHours,
        "counts": inventory["counts"],
        "bytes": inventory["bytes"],
        "recent": inventory["recent"],
        "cookies": cookies_status(config),
    }


@app.get("/api/logs")
async def get_logs(lines: int = 400) -> dict[str, str]:
    return {"logs": tail_log(lines)}


@app.delete("/api/logs")
async def clear_logs() -> dict[str, bool]:
    LOG_PATH.write_text("", encoding="utf-8")
    append_log("Logs cleared.")
    return {"ok": True}


@app.delete("/api/archive")
async def clear_archive() -> dict[str, bool]:
    config = load_config()
    path = Path(config.archivePath)
    if path.exists():
        path.unlink()

    append_log(f"Archive cleared: {config.archivePath}")
    return {"ok": True}


@app.get("/api/cookies")
async def list_cookies() -> dict[str, Any]:
    config = load_config()
    return cookies_status(config)


@app.post("/api/cookies")
async def create_cookies(payload: CookiesPayload) -> CookieProfile:
    content = payload.content.strip()
    if not content.startswith("# Netscape HTTP Cookie File"):
        raise HTTPException(status_code=400, detail="Cookies must be Netscape format, starting with '# Netscape HTTP Cookie File'")

    config = load_config()
    profile = CookieProfile(
        name=payload.name.strip() or "YouTube cookies",
        path="",
        active=False,
        createdAt=now_iso(),
        updatedAt=now_iso(),
    )
    path = profile_path(profile.id)
    profile.path = str(path)
    path.write_text(content + "\n", encoding="utf-8")
    refresh_cookie_profile(profile)

    if payload.activate or not config.activeCookieId:
        config.activeCookieId = profile.id

    config.cookies.append(profile)
    save_config(config)
    append_log(f"Cookie profile created: {profile.name}")
    return profile


@app.put("/api/cookies/{cookie_id}")
async def update_cookies(cookie_id: str, payload: CookieUpdate) -> CookieProfile:
    config = load_config()
    profile = next((item for item in config.cookies if item.id == cookie_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="Cookie profile not found")

    if payload.name is not None:
        profile.name = payload.name.strip() or profile.name

    if payload.content is not None:
        content = payload.content.strip()
        if not content.startswith("# Netscape HTTP Cookie File"):
            raise HTTPException(status_code=400, detail="Cookies must be Netscape format, starting with '# Netscape HTTP Cookie File'")

        Path(profile.path).write_text(content + "\n", encoding="utf-8")
        profile.updatedAt = now_iso()

    if payload.activate:
        config.activeCookieId = profile.id

    refresh_cookie_profile(profile)
    save_config(config)
    append_log(f"Cookie profile updated: {profile.name}")
    return profile


@app.post("/api/cookies/{cookie_id}/activate")
async def activate_cookies(cookie_id: str) -> CookieProfile:
    config = load_config()
    profile = next((item for item in config.cookies if item.id == cookie_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="Cookie profile not found")

    config.activeCookieId = profile.id
    save_config(config)
    append_log(f"Cookie profile activated: {profile.name}")
    return profile


@app.delete("/api/cookies/{cookie_id}")
async def delete_cookies(cookie_id: str) -> dict[str, bool]:
    config = load_config()
    profile = next((item for item in config.cookies if item.id == cookie_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="Cookie profile not found")

    with suppress(FileNotFoundError):
        Path(profile.path).unlink()

    config.cookies = [item for item in config.cookies if item.id != cookie_id]
    if config.activeCookieId == cookie_id:
        config.activeCookieId = config.cookies[0].id if config.cookies else None

    save_config(config)
    append_log(f"Cookie profile deleted: {profile.name}")
    return {"ok": True}
