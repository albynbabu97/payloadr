# 📦 Payloadr

A lightweight, Dockerized HTTP/HTTPS downloader designed specifically for homelabs. 

Tired of manually typing out directory paths or using terminal commands just to download a file to your server? Payloadr dynamically scans your mounted storage and provides a clean, mobile-responsive web UI with a drop-down menu to pick exactly where your file lands.

## ✨ Features

* **Dynamic Folder Selection:** Automatically maps and displays your server directories in a drop-down menu.
* **Smart Filename Extraction:** Automatically grabs the correct filename from the remote server's headers.
* **Auto-Renaming:** Safely renames files (e.g., `file_1.iso`) if a file with the same name already exists.
* **Safe Deletion:** Delete downloaded files directly from the UI without risking your existing folder data.
* **Resume Support:** Pause and resume downloads (supports HTTP `Range` headers).
* **Secure Authentication:** Built-in session management with bcrypt password hashing.
* **Mobile-Responsive:** Beautiful dark-mode UI that looks great on desktops and phones.
* **Dashboard API:** Native support for Homepage (`gethomepage.dev`) integration.

---

## 🚀 Quick Start (Docker Compose)

The easiest way to run Payloadr is via Docker Compose. 

### 1. Create your `docker-compose.yml`

Create a new directory on your server and add the following `docker-compose.yml` file:

```yaml
services:
  payloadr:
    # If using a pre-built image from a registry, replace 'build: .' with 'image: yourusername/payloadr:latest'
    build: .
    container_name: payloadr
    ports:
      - "5000:5000" # Change the left port if 5000 is already in use
    environment:
      # Comma-separated list of base paths you want to download to
      - PAYLOADR_PATHS=/downloads,/movies,/shows
    volumes:
      # Map the container paths (right) to your actual server hard drive paths (left)
      - /path/to/your/host/downloads:/downloads
      - /srv/media/movies:/movies
      - /srv/media/shows:/shows
    restart: unless-stopped
```

### 2. Deploy the Container

Run the following command in the same directory as your `docker-compose.yml`:

```bash
docker-compose up --build -d
```

### 3. Access the UI

Navigate to `http://<your-server-ip>:5000` in your web browser.

**Default Login Credentials:**
* **Username:** `admin`
* **Password:** `admin`

> ⚠️ **Important:** As soon as you log in, click the **Settings** (⚙️) icon in the top right corner to change your username and password.

---

## 📂 Configuring Storage Paths

Payloadr is designed to handle multiple download destinations safely. 

1. Define the internal container paths in the `PAYLOADR_PATHS` environment variable.
2. Bind those internal paths to your actual host machine paths in the `volumes` section.

If you add a new path, just restart the container, and Payloadr will automatically discover it and add it to the UI drop-down menu!

---

## 📊 Homepage Integration

Payloadr includes a built-in, unauthenticated API endpoint (`/api/homepage`) designed specifically for [Homepage](https://gethomepage.dev/). 

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