FROM node:22-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    YOUTUBE_DASHBOARD_CONFIG=/config/config.json \
    YOUTUBE_DASHBOARD_LOG=/config/sync.log \
    YOUTUBE_OUTPUT_DIR=/youtube

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg ca-certificates \
  && pip3 install --break-system-packages --no-cache-dir fastapi uvicorn yt-dlp \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app ./app
COPY static ./static

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
