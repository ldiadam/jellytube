# JellyTube

JellyTube now has two parts:

- `dashboard/`: the useful Docker sidecar. It manages YouTube channels/playlists, cookies, schedule, manual sync, and logs.
- `Jellyfin.Plugin.YouTubeChannelCache/`: the earlier Jellyfin plugin scaffold. It can stay installed, but it is not required for the practical ZimaOS workflow.

## ZimaOS Dashboard

Build the dashboard image directly from GitHub on ZimaOS:

```bash
docker build -t jellytube-dashboard:local https://github.com/ldiadam/jellytube.git#main:dashboard
```

Stop the old one-command sync container if it exists:

```bash
docker rm -f youtube-cache-sync
```

Start the dashboard:

```bash
mkdir -p /media/sdb1/YouTube-dashboard

docker run -d \
  --name jellytube-dashboard \
  --restart unless-stopped \
  -p 8088:8080 \
  -v /media/sdb1/YouTube:/youtube \
  -v /media/sdb1/YouTube-dashboard:/config \
  jellytube-dashboard:local
```

Open:

```text
http://ZIMAOS_IP:8088
```

The dashboard stores its config and logs in:

```text
/media/sdb1/YouTube-dashboard
```

Downloaded videos, metadata, thumbnails, cookies, and archive data live in:

```text
/media/sdb1/YouTube
```

### Dashboard Features

- add/remove YouTube channel or playlist URLs
- edit source labels, URLs, enabled state, per-source playlist limits, and format overrides
- enable/disable individual sources
- run all sources or a single source immediately
- stop a running sync
- skip/reset the next scheduled run
- set schedule interval, default 6 hours
- create, update, activate, and delete Netscape-format YouTube cookie profiles
- configure yt-dlp format selector, merge format, archive path, output template, metadata/thumbnail behavior, and request sleep
- view sync logs
- clear logs and clear the yt-dlp download archive
- track downloaded video, metadata, thumbnail, storage size, and recent output files

### Jellyfin Library

Your ZimaOS mount already maps:

```text
/media/sdb1/YouTube -> /cache/youtube-channels
```

In Jellyfin, add this as a normal media library:

```text
Dashboard -> Libraries -> Add Media Library
Folder: /cache/youtube-channels
Content type: Other Videos
```

If the old Jellyfin plugin is still installed, set:

```text
Cache Directory: /cache/youtube-channels
Enable scheduled refresh: off
```

The dashboard is now the downloader and scheduler.

### Dashboard Maintenance

View logs:

```bash
docker logs -f jellytube-dashboard
```

Restart:

```bash
docker restart jellytube-dashboard
```

Upgrade after pushing changes to GitHub:

```bash
docker build -t jellytube-dashboard:local https://github.com/ldiadam/jellytube.git#main:dashboard
docker rm -f jellytube-dashboard
docker run -d \
  --name jellytube-dashboard \
  --restart unless-stopped \
  -p 8088:8080 \
  -v /media/sdb1/YouTube:/youtube \
  -v /media/sdb1/YouTube-dashboard:/config \
  jellytube-dashboard:local
```

## Jellyfin Plugin Scaffold

This is a Jellyfin metadata/general plugin scaffold that reads and refreshes YouTube channel metadata through a local cache. It is intended for setups where TubeSync, TubeArchivist, `yt-dlp`, or another worker writes channel data and media to local paths Jellyfin can see.

The plugin currently includes:

- plugin configuration storage and web configuration page
- cache read/write service for `channel.json`
- scheduled task that can refresh configured channels with `yt-dlp`
- minimal `Series` metadata provider keyed by a custom `YouTube` provider id

## Build

```bash
cd Jellyfin.Plugin.YouTubeChannelCache
dotnet restore
dotnet build -c Release
```

Copy the release output into Jellyfin's plugin directory and restart Jellyfin.

If your local machine does not have the .NET SDK, the included scripts can build with Docker.

## Package

```bash
scripts/package-plugin.sh
```

This creates:

```text
dist/Jellyfin.Plugin.YouTubeChannelCache.zip
```

## Deploy to a Remote Jellyfin Server

The deploy script builds the plugin, uploads `Jellyfin.Plugin.YouTubeChannelCache.dll` and `meta.json` over SSH, then restarts Jellyfin.

Native Linux Jellyfin install:

```bash
scripts/deploy-plugin.sh --host root@your-server
```

Remote Docker install where Jellyfin config is mounted at `/srv/jellyfin/config`:

```bash
scripts/deploy-plugin.sh \
  --host adam@your-server \
  --path /srv/jellyfin/config/plugins/YouTubeChannelCache \
  --restart docker \
  --container jellyfin
```

Docker Compose example:

```bash
scripts/deploy-plugin.sh \
  --host adam@your-server \
  --path /srv/jellyfin/config/plugins/YouTubeChannelCache \
  --restart-cmd 'docker compose -f /opt/jellyfin/docker-compose.yml restart jellyfin'
```

Upload without restart:

```bash
scripts/deploy-plugin.sh --host adam@your-server --restart none
```

## Install Through a Jellyfin Plugin Repository

Jellyfin can install third-party plugins from a repository URL. The repository is just a hosted JSON manifest that points to hosted plugin zip files.

This repo includes a `docs/` folder that GitHub Pages can publish directly.

### GitHub Pages Setup Without Actions

Create a GitHub repository, push this project to it, then enable GitHub Pages from the `docs/` folder:

```text
GitHub repo -> Settings -> Pages -> Build and deployment
Source: Deploy from a branch
Branch: main
Folder: /docs
```

GitHub Pages will publish:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/manifest.json
```

For this repo name, the expected URL is:

```text
https://ldiadam.github.io/jellytube/manifest.json
```

If your GitHub username or repo name is different, adjust the URL accordingly.

If GitHub Pages redirects to a custom domain you did not mean to use, either remove that custom domain in GitHub Pages settings or use the raw manifest URL instead:

```text
https://raw.githubusercontent.com/ldiadam/jellytube/main/docs/manifest.json
```

Then add this repository in Jellyfin:

```text
Dashboard -> Plugins -> Repositories -> Add
```

Repository URL:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/manifest.json
```

After saving, go to:

```text
Dashboard -> Plugins -> Catalog
```

Install `YouTube Channel Cache`, then restart Jellyfin.

### Rebuild Plugin Repository Locally

The `docs/` folder currently contains the installable zip and manifest. To regenerate the plugin repository output locally:

```bash
scripts/build-plugin-repository.sh https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME
```

It creates:

```text
plugin-repository/manifest.json
plugin-repository/Jellyfin.Plugin.YouTubeChannelCache_0.1.0.0.zip
```

## Cache Layout

```text
/cache/youtube-channels/{channelId}/channel.json
```

Example `channel.json`:

```json
{
  "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
  "title": "Google for Developers",
  "description": "...",
  "url": "https://www.youtube.com/@GoogleDevelopers/videos",
  "lastUpdatedUtc": "2026-04-19T10:00:00Z",
  "videos": [
    {
      "videoId": "abc123",
      "title": "New API update",
      "description": "...",
      "publishedUtc": "2026-04-10T12:00:00Z",
      "durationSeconds": 742,
      "filePath": "/media/youtube/Google for Developers/2026/New API update [abc123].mp4"
    }
  ]
}
```

## Docker Notes

If Jellyfin runs in Docker, mount the cache and media directories into the container:

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    volumes:
      - ./config:/config
      - ./cache/youtube:/cache/youtube-channels
      - ./media/youtube:/media/youtube
```

If scheduled refresh is enabled, `yt-dlp` must also exist inside the Jellyfin container.

## ZimaOS / Docker Cache Sync

On ZimaOS App Store Jellyfin, the Jellyfin container usually does not include `yt-dlp`. In that setup, disable the plugin's scheduled refresh and run the cache sync outside Jellyfin.

In the plugin config:

```text
Enable scheduled refresh: off
Cache Directory: /cache/youtube-channels
```

Then run a sidecar or host job that writes the same host folder mounted into Jellyfin.

Example one-off sync from a machine with Python and `yt-dlp`:

```bash
python3 scripts/sync-youtube-cache.py \
  --cache-dir /PATH/TO/HOST/youtube-cache \
  --channel-url 'https://www.youtube.com/@museidwonderland'
```

Example with a channel list:

```bash
python3 scripts/sync-youtube-cache.py \
  --cache-dir /PATH/TO/HOST/youtube-cache \
  --channels-file channels.txt
```

The Jellyfin container must mount that host folder to the plugin's cache directory. For example:

```text
/PATH/TO/HOST/youtube-cache -> /cache/youtube-channels
```
