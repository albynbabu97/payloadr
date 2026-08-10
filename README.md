# 📦 Payloadr

A lightweight, Dockerized HTTP/HTTPS downloader designed specifically for homelabs.

Tired of manually typing out directory paths or using terminal commands just to download a file to your server? Payloadr dynamically scans your mounted storage and provides a clean, mobile-responsive web UI with a drop-down menu to pick exactly where your file lands.

## ✨ Features

- **Real-Time Metrics & Global Stats:** Track download speed, elapsed time, and ETA per file. A dynamic header panel also displays the average speed and remaining time across all active downloads!
- **Smart Naming & Auto-Subfolders:** Automatically grabs the correct filename from remote headers. You can optionally provide a custom filename, and if no subfolder is specified, Payloadr automatically creates one based on the file's name.
- **Dynamic Folder Selection:** Automatically maps and displays your server directories in a drop-down menu. Choose exactly which folders are visible from the Settings panel.
- **Intuitive UI:** Beautiful dark-mode interface with context-aware icons and clear color-coded statuses (Green for success, Red for errors).
- **Auto-Renaming:** Safely renames files (e.g., `file_1.iso`) if a file with the same name already exists to prevent accidental overwrites.
- **Safe Deletion:** Delete downloaded files (and empty subfolders) directly from the UI without risking your existing folder data.
- **Secure Authentication:** Built-in session management with bcrypt password hashing.
- **Mobile-Responsive:** Optimized UI that looks great and functions perfectly on both desktop and mobile devices.
- **Dashboard API:** Native support for Homepage (`gethomepage.dev`) integration.

---

## 🚀 Quick Start (Docker Compose)

The easiest way to run Payloadr is via the modern `docker compose` command.

### 1. Create your `compose.yaml`

Create a new directory on your server and add the following `compose.yaml` file:

```yaml
services:
  payloadr:
    image: ghcr.io/albynbabu97/payloadr:latest
    container_name: payloadr
    ports:
      - "5000:5000" # Change the left port if 5000 is already in use
    environment:
      # Comma-separated list of base paths you want to download to
      PAYLOADR_PATHS: /downloads,/movies,/shows
    volumes:
      # Map the container paths (right) to your actual server hard drive paths (left)
      - /srv/downloads:/downloads
      - /srv/media/movies:/movies
      - /srv/media/shows:/shows
    restart: unless-stopped
networks: {}
```

### 2. Deploy the Container

Run the following command in the same directory as your `compose.yaml`:

```bash
docker compose up -d
```

### 3. Access the UI

Navigate to `http://<your-server-ip>:5000` in your web browser.

**Default Login Credentials:**

- **Username:** `admin`
- **Password:** `admin`

> ⚠️ **Important:** As soon as you log in, click the Settings (⚙️) icon in the top navigation row to change your username and password immediately.

---

## 📂 Configuring Storage Paths

Payloadr is designed to handle multiple download destinations safely.

1. Define the internal container paths in the `PAYLOADR_PATHS` environment variable.

2. Bind those internal paths to your actual host machine paths in the `volumes` section.

If you add a new path, just restart the container, and Payloadr will automatically discover it. You can then toggle its visibility in the dropdown menu via the in-app Settings panel!

---

## 📊 Homepage Integration

Payloadr includes a built-in, unauthenticated API endpoint (/api/homepage) designed specifically for [Homepage](https://gethomepage.dev/).

To add the Payloadr widget to your dashboard, add this to your `services.yaml`:

```yaml
- Homelab Tools:
    - Payloadr:
        icon: mdi-download-network
        href: http://<your-server-ip>:5000
        description: Custom HTTP/HTTPS Downloader
        widget:
          type: customapi
          url: http://<your-server-ip>:5000/api/homepage
          refreshInterval: 5000
          mappings:
            - field: active_downloads
              label: Active
            - field: latest_file
              label: Latest
            - field: latest_progress
              label: Progress
```
