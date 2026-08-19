# 📦 Payloadr

A lightweight, Dockerized HTTP/HTTPS downloader designed specifically for homelabs.

Tired of manually typing out directory paths or using terminal commands just to download a file to your server? Payloadr dynamically scans your mounted storage and provides a clean, mobile-responsive web UI with a drop-down menu to pick exactly where your file lands.

A companion Telegram bot (`payloadr-bot`) can queue HTTP(S) downloads, stream Telegram files straight to disk, and hand magnet links to qBittorrent.

## ✨ Features

- **Real-Time Metrics & Global Stats:** Track download speed, elapsed time, and ETA per file. A dynamic header panel also displays the average speed and remaining time across all active downloads.
- **Segmented Downloads:** Probes the remote URL and, when the server honours HTTP range requests, splits large files across multiple connections (default 8) with automatic fallback to a single stream.
- **Smart Naming & Auto-Subfolders:** Automatically grabs the correct filename from remote headers. You can optionally provide a custom filename, and if no subfolder is specified, Payloadr automatically creates one based on the file's name.
- **Dynamic Folder Selection:** Automatically maps and displays your server directories in a drop-down menu. Choose exactly which folders are visible from the Settings panel.
- **Intuitive UI:** Dark-mode interface with context-aware icons and color-coded statuses (green for success, red for errors), including a mobile-responsive layout.
- **Auto-Renaming:** Safely renames files (e.g., `file_1.iso`) if a file with the same name already exists to prevent accidental overwrites.
- **Safe Deletion:** Delete downloaded files (and empty subfolders) directly from the UI without risking your existing folder data.
- **Secure Authentication:** Built-in session management with bcrypt password hashing, plus optional `PAYLOADR_API_KEY` for the Telegram bot and other API clients.
- **Telegram Bot:** Queue HTTP(S) links, rename files, pick a destination folder, stream Telegram documents/video/audio/photos to disk, and watch live `/status` with stop/retry.
- **qBittorrent Magnets:** Paste a magnet in Telegram; the bot logs into qBittorrent, sets the save path, applies a category from the folder name, and enables AutoTMM.
- **Dashboard API:** Native support for Homepage (`gethomepage.dev`) integration.

---

## 🚀 Quick Start (Docker Compose)

Published images (linux/amd64 and linux/arm64):

- App: `ghcr.io/albynbabu97/payloadr:latest`
- Bot: `ghcr.io/albynbabu97/payloadr-bot:latest`

A ready-to-edit file lives at [`compose.example.yaml`](compose.example.yaml). Copy it next to a `.env` (see [`.env.example`](.env.example)) or paste the sample below.

This stack assumes an existing Docker network named `homelab` that already runs qBittorrent (hostname `qbittorrent`, Web UI on port `8080`). Create the network once if needed:

```bash
docker network create homelab
```

### 1. Create your `compose.yaml`

```yaml
services:
  payloadr:
    image: ghcr.io/albynbabu97/payloadr:latest
    container_name: payloadr
    ports:
      - 5050:5000
    environment:
      PAYLOADR_PATHS: /downloads,/movies,/shows,/anime,/music,/anime-shows
      PAYLOADR_API_KEY: <payloadr-api-key>
    volumes:
      - /srv/downloads:/downloads
      - /srv/media/movies:/movies
      - /srv/media/shows:/shows
      - /srv/media/anime:/anime
      - /srv/media/music:/music
      - /srv/media/anime-shows:/anime-shows
    restart: unless-stopped
    networks:
      - homelab

  telegram-bot:
    image: ghcr.io/albynbabu97/payloadr-bot:latest
    container_name: payloadr-bot
    depends_on:
      - payloadr
    environment:
      PAYLOADR_PATHS: /downloads,/movies,/shows,/anime,/music,/anime-shows
      TELEGRAM_API_ID: <telegram-api-id>
      TELEGRAM_API_HASH: <telegram-api-hash>
      TELEGRAM_BOT_TOKEN: <telegram-bot-token>
      TELEGRAM_ALLOWED_USER_IDS: <telegram-user-id>
      PAYLOADR_URL: http://payloadr:5000
      PAYLOADR_API_KEY: <payloadr-api-key>
      QBITTORRENT_URL: http://qbittorrent:8080
      QBITTORRENT_USER: <qbittorrent-username>
      QBITTORRENT_PASS: <qbittorrent-password>
    volumes:
      - /srv/downloads:/downloads
      - /srv/media/movies:/movies
      - /srv/media/shows:/shows
      - /srv/media/anime:/anime
      - /srv/media/music:/music
      - /srv/media/anime-shows:/anime-shows
    restart: unless-stopped
    networks:
      - homelab

networks:
  homelab:
    external: true
```

Adjust host paths and `PAYLOADR_PATHS` to match your disks. Keep the **left** and **right** sides of each volume bind identical between `payloadr` and `telegram-bot` so Telegram file streams write to the same folders the web UI manages.

### 2. Fill in secrets

| Variable | Where to get it |
| --- | --- |
| `PAYLOADR_API_KEY` | Any random string (`openssl rand -hex 32`). **Must be the same** on both services. |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USER_IDS` | Your numeric user ID from [@userinfobot](https://t.me/userinfobot). Comma-separated for multiple users. |
| `QBITTORRENT_URL` | Web UI base URL as seen from the bot container (example: `http://qbittorrent:8080`). Put qBittorrent on the `homelab` network. |
| `QBITTORRENT_USER` / `QBITTORRENT_PASS` | qBittorrent Web UI login (defaults inside the bot are `admin` / `adminadmin` if unset). |

Generate a shared API key:

```bash
openssl rand -hex 32
```

### 3. Deploy

```bash
docker compose up -d
```

### 4. Access the UI

Navigate to `http://<your-server-ip>:5050` (or the host port you mapped).

**Default Login Credentials:**

- **Username:** `admin`
- **Password:** `admin`

> ⚠️ **Important:** As soon as you log in, click the Settings (⚙️) icon in the top navigation row to change your username and password immediately.

---

## 🤖 Telegram bot

Allowlisted users can:

1. Paste an `http://` or `https://` URL → pick a folder → optionally rename (creates a matching subfolder).
2. Forward a document, video, audio, or photo → pick a folder → optionally rename. The bot streams the file to disk over MTProto (it does **not** go through the Payloadr HTTP engine).
3. Paste a `magnet:?` link → pick a folder → the bot adds it to qBittorrent with `savepath` set to that folder, category = last path segment (e.g. `/movies` → `movies`), and AutoTMM enabled.
4. Send `/status` (or `/help`) for live progress, stop, and retry. Status auto-refreshes while downloads are active.

Magnet progress is tracked in qBittorrent, not in the Payloadr UI.

qBittorrent login accepts HTTP **200** and **204** (newer Web API versions).

---

## 📂 Configuring Storage Paths

1. Define the internal container paths in the `PAYLOADR_PATHS` environment variable (comma-separated).
2. Bind those internal paths to your actual host machine paths in the `volumes` section of **both** services.

If you add a new path, restart the containers and Payloadr will discover it. Toggle visibility in the in-app Settings panel.

Auth, session secret, and settings files are stored under the **first** path in `PAYLOADR_PATHS`.

---

## 🔧 Optional environment variables (app)

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAYLOADR_SECRET_KEY` | auto-generated file on first path | Flask session secret |
| `PAYLOADR_USER_AGENT` | Chrome-like UA | Outbound download User-Agent |
| `PAYLOADR_READ_TIMEOUT` | `60` | HTTP read timeout (seconds) |
| `PAYLOADR_MAX_RETRIES` | `10` | Retry attempts |
| `PAYLOADR_CONNECTIONS` | `8` | Parallel range connections for segmented downloads |

---

## 📊 Homepage Integration

Payloadr includes a built-in, unauthenticated API endpoint (`/api/homepage`) designed specifically for [Homepage](https://gethomepage.dev/).

To add the Payloadr widget to your dashboard, add this to your `services.yaml`:

```yaml
- Homelab Tools:
    - Payloadr:
        icon: mdi-download-network
        href: http://<your-server-ip>:5050
        description: Custom HTTP/HTTPS Downloader
        widget:
          type: customapi
          url: http://<your-server-ip>:5050/api/homepage
          refreshInterval: 5000
          mappings:
            - field: active_downloads
              label: Active
            - field: latest_file
              label: Latest
            - field: latest_progress
              label: Progress
```
