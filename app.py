import os
import time
import threading
import requests
import uuid
import shutil
import json
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.http import parse_options_header
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Read paths from docker-compose, default to /downloads if none provided
PAYLOADR_PATHS = [
    p.strip()
    for p in os.environ.get("PAYLOADR_PATHS", "/downloads").split(",")
    if p.strip()
]

# Create configured directories before initializing persistent application files
for path in PAYLOADR_PATHS:
    os.makedirs(path, exist_ok=True)

# Store persistent files
AUTH_FILE = os.path.join(PAYLOADR_PATHS[0], ".payloadr_auth.json")
SECRET_FILE = os.path.join(PAYLOADR_PATHS[0], ".payloadr_secret")
SETTINGS_FILE = os.path.join(PAYLOADR_PATHS[0], ".payloadr_settings.json")


def get_secret_key():
    configured_secret = os.environ.get("PAYLOADR_SECRET_KEY")
    if configured_secret:
        return configured_secret

    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r") as f:
            secret = f.read().strip()
        if secret:
            return secret

    secret = os.urandom(32).hex()
    with open(SECRET_FILE, "w") as f:
        f.write(secret)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return secret

app.secret_key = get_secret_key()

DOWNLOAD_STATUS = {}
STOP_EVENTS = {}

# --- SETTINGS & AUTH LOGIC ---

def init_auth():
    if not os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'w') as f:
            json.dump({
                "username": "admin",
                "password_hash": generate_password_hash("admin")
            }, f)
        print("*" * 60, flush=True)
        print("🔒 PAYLOADR SECURITY NOTICE", flush=True)
        print("A new authentication file has been generated.", flush=True)
        print("Default Username: admin", flush=True)
        print("Default Password: admin", flush=True)
        print("Please log in and change these immediately via the Settings panel!", flush=True)
        print("*" * 60, flush=True)
    else:
        print("✅ Payloadr starting up... (Existing auth file found)", flush=True)

def get_auth():
    with open(AUTH_FILE, 'r') as f:
        return json.load(f)

def save_auth(username, password):
    with open(AUTH_FILE, 'w') as f:
        json.dump({
            "username": username,
            "password_hash": generate_password_hash(password)
        }, f)

def get_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings_dict):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings_dict, f)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- TEMPLATES ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Payloadr</title>
    <link rel="icon" type="image/png" sizes="64x64" href="/static/payloadr.png">
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <style>
        :root { 
            --bg-dark: #1b1e3d;
            --bg-dark-gradient: linear-gradient(135deg, #1b1e3d 0%, #2a2d5c 100%);
            --bg-card: #ffffff;
            --text-dark: #1a1a1a;
            --accent: #272c56;
            --input-bg: #f4f5f9;
        }
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: var(--bg-dark-gradient); color: var(--text-dark); display: flex; justify-content: center; align-items: center; height: 100vh; padding: 20px; box-sizing: border-box; }
        .login-box { background: var(--bg-card); padding: 40px 30px; border-radius: 24px; box-shadow: 0 15px 35px rgba(0,0,0,0.3); width: 100%; max-width: 360px; text-align: center; position: relative; z-index: 10; box-sizing: border-box; }
        .brand { font-size: 1.8rem; font-weight: 700; color: var(--accent); display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 30px; }
        .brand img { width: 36px; height: 36px; border-radius: 10px; object-fit: cover; }
        .form-group { margin-bottom: 20px; text-align: left; }
        label { display: block; margin-bottom: 8px; font-size: 0.85rem; font-weight: 600; color: #666; }
        input { width: 100%; padding: 14px; box-sizing: border-box; border-radius: 12px; border: 1px solid transparent; background: var(--input-bg); color: var(--text-dark); font-size: 1rem; transition: 0.2s; }
        input:focus { outline: none; border-color: var(--accent); background: #fff; }
        .btn { width: 100%; background: var(--accent); color: #fff; border: none; padding: 14px; border-radius: 12px; cursor: pointer; font-weight: 600; font-size: 1rem; margin-top: 10px; transition: 0.2s; }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .error { color: #ff3b30; font-size: 0.9em; margin-bottom: 20px; background: rgba(255, 59, 48, 0.1); padding: 10px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="brand"><img src="/static/payloadr.png" alt="Logo"> Payloadr</div>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required autofocus autocomplete="username">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payloadr</title>
    <link rel="icon" type="image/png" sizes="64x64" href="/static/payloadr.png">
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <style>
        :root {
            --bg-dark: #1b1e3d;
            --bg-dark-gradient: linear-gradient(135deg, #1b1e3d 0%, #292d5c 100%);
            --bg-card: #ffffff;
            --text-main: #1a1a1a; 
            --text-muted: #8e8e93; 
            --accent: #272c56; 
            --icon-bg: #f4f5f9;
            --progress-bar: #3b4282;
            --success: #34c759;
            --danger: #ff3b30;
            --border-color: #e5e5ea;
        }
        
        body { 
            font-family: system-ui, -apple-system, sans-serif; 
            margin: 0; 
            background: var(--bg-dark-gradient); 
            color: var(--text-main); 
            -webkit-font-smoothing: antialiased; 
            position: relative;
            overflow-x: hidden;
        }

        body::before {
            content: ''; position: absolute; top: -10vh; right: -5vw; width: 300px; height: 300px;
            background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0) 70%); border-radius: 50%; z-index: 0; pointer-events: none;
        }
        body::after {
            content: ''; position: absolute; top: 15vh; left: -10vw; width: 250px; height: 250px;
            background: radial-gradient(circle, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 70%); border-radius: 50%; z-index: 0; pointer-events: none;
        }
        
        header { padding: 45px 30px 35px 30px; color: white; display: flex; flex-direction: column; max-width: 80%; margin: 0 auto; position: relative; z-index: 10; box-sizing: border-box; }
        .header-top { display: flex; justify-content: space-between; align-items: center; width: 100%; flex-wrap: wrap; gap: 15px; }
        .header-titles h1 { margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px; display: flex; align-items: center; gap: 14px; }
        .header-titles h1 img { width: 42px; height: 42px; border-radius: 12px; object-fit: cover; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        
        .global-stats { 
            display: flex; gap: 20px; font-size: 0.9rem; background: rgba(255,255,255,0.1); 
            padding: 12px 20px; border-radius: 20px; backdrop-filter: blur(8px); 
            border: 1px solid rgba(255,255,255,0.05); align-items: center;
            white-space: nowrap; overflow-x: auto; scrollbar-width: none;
            box-sizing: border-box; max-width: 100%;
        }
        .global-stats::-webkit-scrollbar { display: none; }
        .stat-item { display: flex; align-items: center; gap: 6px; font-weight: 500; }
        .stat-dot { font-size: 0.8rem; }

        .main-card { background: var(--bg-card); border-radius: 35px 35px 0 0; min-height: calc(100vh - 120px); padding: 35px 30px; max-width: 80%; margin: 0 auto; box-shadow: 0 -15px 40px rgba(0,0,0,0.15); box-sizing: border-box; position: relative; z-index: 10; }
        
        .nav-row { display: flex; gap: 15px; margin-bottom: 35px; overflow-x: auto; padding: 5px 2px; scrollbar-width: none; }
        .nav-row::-webkit-scrollbar { display: none; }
        .nav-btn { width: 58px; height: 58px; min-width: 58px; border-radius: 18px; background: var(--icon-bg); color: var(--text-main); display: flex; justify-content: center; align-items: center; font-size: 1.7rem; border: none; cursor: pointer; transition: 0.2s; }
        .nav-btn:hover { background: #eaeaef; transform: translateY(-2px); }

        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .section-title { font-size: 1.2rem; font-weight: 700; margin: 0; display: flex; align-items: center; gap: 10px; color: var(--text-main); }
        .section-title span { font-size: 0.85rem; font-weight: 500; color: var(--text-muted); }
        
        .btn-clear { background: var(--icon-bg); color: var(--text-main); border: none; padding: 8px 14px; border-radius: 10px; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: 0.2s; }
        .btn-clear:hover { background: #eaeaef; color: var(--danger); }
        
        /* Card Structure */
        .download-item { 
            display: flex; align-items: flex-start; gap: 18px; margin-bottom: 20px; 
            width: 100%; box-sizing: border-box; 
            background: #ffffff; border: 1px solid var(--border-color); 
            border-left: 6px solid transparent; border-radius: 16px; 
            padding: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.02);
            transition: box-shadow 0.2s ease-in-out;
        }
        .download-item:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.06); }
        
        .status-Downloading { border-left-color: #40c4ff; }
        .status-Completed { border-left-color: var(--success); }
        .status-Error { border-left-color: var(--danger); }
        .status-Stopped { border-left-color: var(--text-muted); }
        
        .item-icon { width: 50px; height: 50px; min-width: 50px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 1.8rem; color: white; box-shadow: 0 4px 10px rgba(0,0,0,0.1); margin-top: 2px; }
        .status-Downloading .item-icon { background: #40c4ff; }
        .status-Completed .item-icon { background: var(--success); } 
        .status-Error .item-icon { background: var(--danger); }
        .status-Stopped .item-icon { background: var(--text-muted); }

        .item-content { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
        .item-title { font-weight: 600; font-size: 1rem; color: var(--text-main); word-break: break-word; line-height: 1.3; margin-bottom: 2px;}
        
        .item-meta { display: flex; flex-direction: column; gap: 6px; }
        .item-meta-row { display: flex; gap: 15px; font-size: 0.8rem; color: var(--text-muted); font-weight: 500; flex-wrap: wrap; }
        .item-meta-row span { display: flex; align-items: center; gap: 4px; white-space: nowrap; }

        .progress-container { width: 100%; height: 6px; background: #f0f0f5; border-radius: 3px; margin-top: 8px; overflow: hidden; }
        .progress-bar { height: 100%; border-radius: 3px; transition: width 0.3s ease; }
        .status-Downloading .progress-bar { background: #40c4ff; }
        .status-Completed .progress-bar { background: var(--success); }
        .status-Error .progress-bar { background: var(--danger); }
        .status-Stopped .progress-bar { background: var(--text-muted); }

        .item-actions { display: flex; gap: 8px; flex-shrink: 0; margin-top: 2px; flex-wrap: wrap; justify-content: flex-end;}
        .action-btn { background: var(--icon-bg); border: 1px solid transparent; border-radius: 12px; width: 38px; height: 38px; display: flex; justify-content: center; align-items: center; color: var(--text-main); cursor: pointer; font-size: 1.3rem; transition: 0.2s; }
        .action-btn:hover { background: #eaeaef; border-color: #d1d1d6; }
        .action-btn.danger { background: transparent; border: 1px solid var(--border-color); }
        .action-btn.danger:hover { background: rgba(255, 59, 48, 0.1); color: var(--danger); border-color: rgba(255, 59, 48, 0.2); }
        
        /* Modals */
        .modal-overlay { display: none; position: absolute; inset: 0; background: rgba(27, 30, 61, 0.7); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(5px); padding: 20px; box-sizing: border-box; }
        .modal { background: var(--bg-card); padding: 35px; border-radius: 28px; width: 100%; max-width: 480px; margin: auto; box-shadow: 0 25px 50px rgba(0,0,0,0.25); box-sizing: border-box; max-height: 90vh; overflow-y: auto; overflow-x: hidden; }
        .modal.modal-small { max-width: 400px; }
        .modal h2 { margin-top: 0; margin-bottom: 25px; font-size: 1.4rem; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 8px; }
        .form-group { margin-bottom: 20px; width: 100%; box-sizing: border-box; }
        label { display: block; margin-bottom: 8px; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); }
        input[type="text"], input[type="password"], input[type="url"], select, textarea { width: 100%; padding: 14px; box-sizing: border-box; border-radius: 14px; border: 1px solid var(--border-color); background: var(--icon-bg); color: var(--text-main); font-size: 0.95rem; transition: 0.2s; font-family: inherit; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); background: white; box-shadow: 0 0 0 3px rgba(39, 44, 86, 0.1); }
        
        .modal-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 30px; }
        .btn-modal { padding: 12px 22px; border-radius: 12px; font-weight: 600; cursor: pointer; border: none; font-size: 0.95rem; transition: 0.2s; }
        .btn-cancel { background: transparent; color: var(--text-muted); }
        .btn-cancel:hover { background: var(--icon-bg); color: var(--text-main); }
        .btn-submit { background: var(--accent); color: white; }
        .btn-submit:hover { opacity: 0.9; transform: translateY(-1px); }

        .empty-state { text-align: center; padding: 70px 20px; color: var(--text-muted); font-size: 1rem; display: flex; flex-direction: column; align-items: center; gap: 15px; }
        .empty-state i { font-size: 3rem; color: #d1d1d6; }
        
        .settings-auth-row { display: flex; gap: 15px; width: 100%; box-sizing: border-box; }
        .settings-auth-row .form-group { flex: 1; min-width: 0; }
        
        .info-row { margin-bottom: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; }
        .info-row:last-child { border-bottom: none; }
        .info-label { font-size: 0.8rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .info-value { font-size: 0.95rem; color: var(--text-main); word-break: break-all; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

        /* Folder settings styles */
        .folder-list { max-height: 200px; overflow-y: auto; overflow-x: hidden; background: var(--icon-bg); border: 1px solid var(--border-color); border-radius: 14px; padding: 10px; }
        .folder-list::-webkit-scrollbar { width: 6px; }
        .folder-list::-webkit-scrollbar-thumb { background: #d1d1d6; border-radius: 3px; }
        .folder-checkbox-label { display: flex; align-items: center; gap: 12px; padding: 10px; font-size: 0.9rem; color: var(--text-main); cursor: pointer; border-radius: 8px; transition: 0.2s; margin-bottom: 2px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break: break-all; width: 100%; box-sizing: border-box; }
        .folder-checkbox-label:hover { background: rgba(0,0,0,0.05); }
        .folder-checkbox { width: 18px; height: 18px; margin: 0; padding: 0; flex-shrink: 0; accent-color: var(--accent); cursor: pointer; }

        @media (max-width: 768px) {
            .header-top { flex-direction: column; align-items: flex-start; gap: 20px;}
            .global-stats { width: 100%; } 
        }

        @media (max-width: 600px) {
            header { padding: 40px 20px 30px 20px; max-width: 100%; }
            .header-titles h1 img { display: none; } 
            
            .main-card { border-radius: 35px 35px 0 0; padding: 30px 20px; min-height: calc(100vh - 110px); max-width: 100%; }
            .nav-btn { width: 54px; height: 54px; min-width: 54px; border-radius: 16px; font-size: 1.5rem; }
            .item-title { font-size: 0.95rem; }
            .settings-auth-row { flex-direction: column; gap: 0; }
            .modal { padding: 25px 22px; border-radius: 24px; }
            .global-stats { padding: 10px 15px; gap: 15px; justify-content: flex-start; }
            
            .item-icon { display: none; } 
            .download-item { flex-direction: column; align-items: flex-start; text-align: left; gap: 10px; padding: 16px; }
            .item-meta-row { justify-content: flex-start; }
            .item-actions { width: 100%; justify-content: flex-end; margin-top: 5px; }
        }
    </style>
</head>
<body>
    <header>
        <div class="header-top">
            <div class="header-titles">
                <h1><img src="/static/payloadr.png" alt="Logo"> Payloadr</h1>
            </div>
            <div class="global-stats" id="global-stats" style="display: none;">
                <!-- Filled dynamically by JS -->
            </div>
        </div>
    </header>

    <div class="main-card">
        <div class="nav-row">
            <button class="nav-btn" onclick="toggleModal('addModal', true)" title="Add New Download">
                <i class='bx bx-plus'></i>
            </button>
            <button class="nav-btn" onclick="toggleModal('settingsModal', true)" title="Settings">
                <i class='bx bx-cog'></i>
            </button>
            <button class="nav-btn" onclick="window.location.href='/logout'" title="Logout">
                <i class='bx bx-log-out'></i>
            </button>
        </div>

        <div class="section-header">
            <h2 class="section-title">Downloads <span id="queue-count">0 files</span></h2>
            <button class="btn-clear" onclick="actionAll('clear')" title="Clear Completed/Stopped tasks">
                <i class='bx bx-brush'></i> Clear
            </button>
        </div>
        
        <div id="downloads-container">
            <div class="empty-state">
                <i class='bx bx-layer'></i>
                No active downloads
            </div>
        </div>
    </div>

    <!-- Add Task Modal -->
    <div class="modal-overlay" id="addModal">
        <div class="modal">
            <h2><i class='bx bx-plus-circle'></i> New Download</h2>
            <form id="addForm" onsubmit="submitDownload(event)">
                <div class="form-group">
                    <label>URL (HTTP/HTTPS):</label>
                    <input type="url" id="url" required placeholder="https://example.com/file.zip" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Storage folder:</label>
                    <select id="folder">
                        {% for folder in dropdown_folders %}
                        <option value="{{ folder }}">{{ folder }}</option>
                        {% endfor %}
                    </select>
                    <small style="color: var(--text-muted); font-size: 0.75rem; display: block; margin-top: 8px;">
                        Configure which folders appear here from the Settings menu.
                    </small>
                </div>
                <div class="form-group">
                    <label>Subfolder (Optional):</label>
                    <input type="text" id="subfolder" placeholder="e.g., season_1" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Custom Filename (Optional):</label>
                    <input type="text" id="custom_filename" placeholder="e.g., my_video" autocomplete="off">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn-modal btn-cancel" onclick="toggleModal('addModal', false)">Cancel</button>
                    <button type="submit" class="btn-modal btn-submit">Start</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Settings Modal -->
    <div class="modal-overlay" id="settingsModal">
        <div class="modal">
            <h2><i class='bx bx-cog'></i> Settings</h2>
            <form id="settingsForm" onsubmit="updateSettings(event)">
                <div class="settings-auth-row">
                    <div class="form-group">
                        <label>Username (Blank to keep):</label>
                        <input type="text" id="newUsername" placeholder="admin" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label>Password (Blank to keep):</label>
                        <input type="password" id="newPassword" placeholder="••••••••" autocomplete="new-password">
                    </div>
                </div>
                
                <div class="form-group" style="margin-top: 5px;">
                    <label>Visible Dropdown Folders:</label>
                    <div class="folder-list">
                        {% for folder in all_folders %}
                        <label class="folder-checkbox-label">
                            <input type="checkbox" class="folder-checkbox" value="{{ folder }}" 
                                {% if folder in visible_folders %}checked{% endif %}>
                            {{ folder }}
                        </label>
                        {% endfor %}
                        {% if not all_folders %}
                            <div style="padding: 15px; text-align: center; color: var(--text-muted); font-size: 0.9rem;">No subfolders detected yet.</div>
                        {% endif %}
                    </div>
                </div>

                <div class="modal-actions">
                    <button type="button" class="btn-modal btn-cancel" onclick="toggleModal('settingsModal', false)">Cancel</button>
                    <button type="submit" class="btn-modal btn-submit">Save Settings</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Info Modal -->
    <div class="modal-overlay" id="infoModal">
        <div class="modal">
            <h2><i class='bx bx-info-circle'></i> Details</h2>
            <div id="infoModalContent">
                <!-- Injected via JS -->
            </div>
            <div class="modal-actions">
                <button type="button" class="btn-modal btn-submit" onclick="toggleModal('infoModal', false)">Close</button>
            </div>
        </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div class="modal-overlay" id="deleteModal">
        <div class="modal modal-small">
            <h2><i class='bx bx-trash' style="color: var(--danger);"></i> Confirm Delete</h2>
            <p style="color: var(--text-muted); margin-bottom: 25px; font-size: 0.95rem; line-height: 1.5;">
                Are you sure you want to permanently delete this downloaded file from the server? This action cannot be undone.
            </p>
            <div class="modal-actions">
                <button type="button" class="btn-modal btn-cancel" onclick="toggleModal('deleteModal', false)">Cancel</button>
                <button type="button" class="btn-modal" style="background: var(--danger); color: white;" onclick="confirmDelete()">Delete File</button>
            </div>
        </div>
    </div>

    <script>
        let pendingDeleteTaskId = null;
        let latestDownloadsData = {};

        const sanitize = (str) => {
            if (!str) return '';
            const div = document.createElement('div');
            div.innerText = str;
            return div.innerHTML;
        };
        
        function toggleModal(modalId, show) {
            document.getElementById(modalId).style.display = show ? 'flex' : 'none';
            if(show && modalId === 'addModal') document.getElementById('url').focus();
        }

        function showInfo(taskId) {
            const info = latestDownloadsData[taskId];
            if (!info) return;

            let html = `
                <div class="info-row">
                    <div class="info-label">File Name</div>
                    <div class="info-value">${sanitize(info.filename)}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Status</div>
                    <div class="info-value" style="color: ${info.status.includes('Error') ? 'var(--danger)' : 'inherit'}">${sanitize(info.status)}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Source URL</div>
                    <div class="info-value"><a href="${sanitize(info.url)}" target="_blank" style="color: var(--accent); text-decoration: none;">${sanitize(info.url)}</a></div>
                </div>
                <div class="info-row">
                    <div class="info-label">Destination Path</div>
                    <div class="info-value">${sanitize(info.dest_path || 'Pending...')}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Total Size</div>
                    <div class="info-value">${formatBytes(info.total_size)}</div>
                </div>
            `;
            document.getElementById('infoModalContent').innerHTML = html;
            toggleModal('infoModal', true);
        }

        async function submitDownload(e) {
            e.preventDefault();
            const folderSelect = document.getElementById('folder');
            const payload = {
                url: document.getElementById('url').value,
                folder: folderSelect ? folderSelect.value : "",
                subfolder: document.getElementById('subfolder').value,
                custom_filename: document.getElementById('custom_filename').value
            };
            const res = await fetch('/api/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.status === 401) return window.location.reload();
            toggleModal('addModal', false);
            document.getElementById('addForm').reset();
            updateProgress(); 
        }

        async function updateSettings(e) {
            e.preventDefault();
            const checkboxes = document.querySelectorAll('.folder-checkbox:checked');
            const checkedFolders = Array.from(checkboxes).map(cb => cb.value);

            const payload = {
                username: document.getElementById('newUsername').value,
                password: document.getElementById('newPassword').value,
                visible_folders: checkedFolders
            };
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                if (payload.username || payload.password) {
                    window.location.href = '/logout';
                } else {
                    window.location.reload();
                }
            } else {
                alert("Failed to update settings.");
            }
        }

        async function triggerAction(taskId, action) {
            if (action === 'delete') {
                pendingDeleteTaskId = taskId;
                toggleModal('deleteModal', true);
                return;
            }
            const res = await fetch(`/api/action/${taskId}/${action}`, { method: 'POST' });
            if (res.status === 401) return window.location.reload();
            updateProgress();
        }

        async function confirmDelete() {
            if (!pendingDeleteTaskId) return;
            toggleModal('deleteModal', false);
            const res = await fetch(`/api/action/${pendingDeleteTaskId}/delete`, { method: 'POST' });
            if (res.status === 401) return window.location.reload();
            pendingDeleteTaskId = null;
            updateProgress();
        }

        async function actionAll(action) {
            const res = await fetch(`/api/action/all/${action}`, { method: 'POST' });
            if (res.status === 401) return window.location.reload();
            updateProgress();
        }

        function formatBytes(bytes) {
            if (!bytes || bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function formatTime(seconds) {
            if (!seconds || !isFinite(seconds) || seconds < 0) return '0s';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) return `${h}h ${m}m ${s}s`;
            if (m > 0) return `${m}m ${s}s`;
            return `${s}s`;
        }

        function updateProgress() {
            fetch('/api/status')
                .then(res => {
                    if (res.status === 401) window.location.reload();
                    return res.json();
                })
                .then(data => {
                    latestDownloadsData = data;
                    const container = document.getElementById('downloads-container');
                    const countSpan = document.getElementById('queue-count');
                    const statsContainer = document.getElementById('global-stats');
                    
                    const keys = Object.keys(data);
                    countSpan.innerText = `${keys.length} file${keys.length !== 1 ? 's' : ''}`;

                    let activeCount = 0;
                    let totalSpeed = 0;
                    let totalElapsed = 0;
                    let totalEta = 0;

                    if (keys.length === 0) {
                        statsContainer.style.display = 'none';
                        container.innerHTML = `<div class="empty-state"><i class='bx bx-layer'></i>No active downloads</div>`;
                        return;
                    }

                    let html = '';
                    for (const [taskId, info] of Object.entries(data)) {
                        let controls = `<button class="action-btn" title="Details" onclick="showInfo('${taskId}')"><i class='bx bx-info-circle'></i></button>`;
                        let iconClass = 'bx-time';
                        let isActive = false;

                        if (info.status === 'Downloading' || info.status === 'Connecting...') {
                            controls += `<button class="action-btn" title="Stop" onclick="triggerAction('${taskId}', 'stop')"><i class='bx bx-stop'></i></button>`;
                            iconClass = 'bx-cloud-download';
                            isActive = true;
                            
                            activeCount++;
                            totalSpeed += (info.speed || 0);
                            totalElapsed += (info.elapsed || 0);
                            totalEta += (info.eta || 0);
                        } else if (info.status === 'Completed') {
                            controls += `<button class="action-btn" title="Retry" onclick="triggerAction('${taskId}', 'retry')"><i class='bx bx-refresh'></i></button>`;
                            controls += `<button class="action-btn danger" title="Delete" onclick="triggerAction('${taskId}', 'delete')"><i class='bx bx-trash'></i></button>`;
                            iconClass = 'bx-check';
                        } else {
                            controls += `<button class="action-btn" title="Retry" onclick="triggerAction('${taskId}', 'retry')"><i class='bx bx-refresh'></i></button>`;
                            controls += `<button class="action-btn danger" title="Delete" onclick="triggerAction('${taskId}', 'delete')"><i class='bx bx-trash'></i></button>`;
                            iconClass = info.status.includes('Error') ? 'bx-x' : 'bx-stop-circle';
                        }

                        let cssStatus = info.status.split(' ')[0]; 
                        if(info.status.includes('Error')) cssStatus = 'Error';

                        let formattedDownloaded = formatBytes(info.downloaded);
                        let formattedTotal = info.total_size > 0 ? formatBytes(info.total_size) : 'Unknown';

                        html += `
                            <div class="download-item status-${cssStatus}">
                                <div class="item-icon">
                                    <i class='bx ${iconClass}'></i>
                                </div>
                                <div class="item-content">
                                    <div class="item-title" title="${sanitize(info.filename)}">${sanitize(info.filename)}</div>
                                    
                                    <div class="item-meta">
                                        <div class="item-meta-row">
                                            <span><i class='bx bx-data'></i> ${formattedDownloaded} of ${formattedTotal} (${info.progress}%)</span>
                                        </div>
                                        ${isActive ? `
                                        <div class="item-meta-row">
                                            <span><i class='bx bx-tachometer'></i> ${formatBytes(info.speed)}/s</span>
                                            <span><i class='bx bx-time-five'></i> ETA: ${formatTime(info.eta)}</span>
                                            <span><i class='bx bx-stopwatch'></i> Elapsed: ${formatTime(info.elapsed)}</span>
                                        </div>
                                        ` : `
                                        <div class="item-meta-row">
                                            <span><i class='bx bx-stopwatch'></i> Elapsed: ${formatTime(info.elapsed)}</span>
                                            <span style="color: ${cssStatus === 'Error' ? 'var(--danger)' : 'inherit'}">${sanitize(info.status)}</span>
                                        </div>
                                        `}
                                    </div>
                                    
                                    <div class="progress-container">
                                        <div class="progress-bar" style="width: ${info.progress}%;"></div>
                                    </div>
                                </div>
                                <div class="item-actions">${controls}</div>
                            </div>
                        `;
                    }
                    container.innerHTML = html;

                    if (activeCount > 0) {
                        statsContainer.style.display = 'flex';
                        const avgSpeed = totalSpeed; 
                        const avgElapsed = totalElapsed / activeCount;
                        const avgEta = totalEta / activeCount;

                        statsContainer.innerHTML = `
                            <div class="stat-item" title="Combined Speed">
                                <span class="stat-dot" style="color: #40c4ff;">●</span> ${formatBytes(avgSpeed)}/s
                            </div>
                            <div class="stat-item" title="Avg Elapsed Time">
                                <span class="stat-dot" style="color: #ff9500;">●</span> ${formatTime(avgElapsed)}
                            </div>
                            <div class="stat-item" title="Avg Time Left">
                                <span class="stat-dot" style="color: #34c759;">●</span> ${formatTime(avgEta)}
                            </div>
                        `;
                    } else {
                        statsContainer.style.display = 'none';
                    }
                })
                .catch(err => console.error('Error fetching status:', err));
        }

        setInterval(updateProgress, 1000);
        updateProgress();
    </script>
</body>
</html>
"""

# --- UTILITY LOGIC ---

def secure_path_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    base_path = os.path.abspath(base)
    if not (final_path == base_path or final_path.startswith(base_path + os.sep)):
        raise ValueError("Path traversal security violation detected.")
    return final_path

def get_all_folders():
    folders = []
    for base in PAYLOADR_PATHS:
        if os.path.exists(base):
            folders.append(base)
            try:
                for d in os.listdir(base):
                    full_path = os.path.join(base, d)
                    if os.path.isdir(full_path):
                        folders.append(full_path)
            except Exception:
                pass
    return sorted(list(set(folders)))

# --- ENHANCED SURGE-INSPIRED DOWNLOAD ENGINE ---

def download_worker(task_id, url, dest_path, start_byte, end_byte, worker_id, progress_dict, lock):
    """
    Worker function mapping to Surge's 'Large Chunks' optimization.
    It includes its own internal loop for HealthCheck resilience (re-establishing dropped connections).
    """
    headers = {'Range': f'bytes={start_byte}-{end_byte}'}
    current_start = start_byte
    retries = 3

    while retries > 0:
        try:
            if STOP_EVENTS.get(task_id, False):
                return

            with requests.get(url, headers=headers, stream=True, timeout=10) as r:
                r.raise_for_status()
                with open(dest_path, 'rb+') as f:
                    f.seek(current_start)
                    for chunk in r.iter_content(chunk_size=65536):
                        if STOP_EVENTS.get(task_id, False):
                            return
                        if chunk:
                            f.write(chunk)
                            chunk_len = len(chunk)
                            current_start += chunk_len
                            with lock:
                                progress_dict['downloaded'] += chunk_len
            break 
        except Exception as e:
            retries -= 1
            if retries <= 0:
                with lock:
                    progress_dict['error'] = str(e)
                break
            headers = {'Range': f'bytes={current_start}-{end_byte}'}
            time.sleep(1)

def download_task(task_id):
    info = DOWNLOAD_STATUS.get(task_id)
    if not info: return

    url = info['url']
    info['status'] = 'Connecting...'
    info['downloaded'] = 0
    info['start_time'] = time.time()
    info['elapsed'] = 0
    info['speed'] = 0
    info['eta'] = 0
    
    try:
        if not (url.startswith('http://') or url.startswith('https://')):
            raise ValueError("Only HTTP/HTTPS URLs are allowed.")

        # --- Metadata Collection Phase ---
        with requests.get(url, stream=True, timeout=15) as r:
            r.raise_for_status()
            
            dest_path = info.get('dest_path')
            if not dest_path:
                content_disp = r.headers.get('content-disposition')
                original_fname = None
                
                if content_disp:
                    _, options = parse_options_header(content_disp)
                    original_fname = options.get('filename')
                
                if not original_fname:
                    parsed = urlparse(url)
                    original_fname = os.path.basename(parsed.path)
                    if not original_fname:
                        original_fname = "payload.bin"
                
                orig_base, orig_ext = os.path.splitext(original_fname)
                custom_fname = info.get('custom_filename', '').strip()
                if custom_fname:
                    custom_base, custom_ext = os.path.splitext(custom_fname)
                    fname = custom_fname if custom_ext else custom_fname + orig_ext
                else:
                    fname = original_fname
                    
                final_base, final_ext = os.path.splitext(fname)
                
                if not info.get('subfolder'):
                    info['subfolder'] = final_base
                    info['dest_dir'] = secure_path_join(info['base_dir'], final_base)
                
                os.makedirs(info['dest_dir'], exist_ok=True)
                
                counter = 1
                proposed_path = secure_path_join(info['dest_dir'], fname)
                while os.path.exists(proposed_path):
                    fname = f"{final_base}_{counter}{final_ext}"
                    proposed_path = secure_path_join(info['dest_dir'], fname)
                    counter += 1
                
                dest_path = proposed_path
                info['dest_path'] = dest_path
                info['filename'] = fname

            content_length = r.headers.get('content-length')
            accept_ranges = r.headers.get('accept-ranges') == 'bytes'
            
            if content_length:
                total_size = int(content_length)
                info['total_size'] = total_size
            else:
                total_size = info.get('total_size', 0)

        # --- Execution Phase (Multi-threaded Surge Engine) ---
        info['status'] = 'Downloading'
        num_workers = 8 

        if total_size > 0 and accept_ranges:
            with open(dest_path, "wb") as f:
                f.truncate(total_size) 
                
            chunk_size = total_size // num_workers
            threads = []
            lock = threading.Lock()
            progress_dict = {'downloaded': 0, 'error': None}
            
            for i in range(num_workers):
                start_byte = i * chunk_size
                end_byte = (start_byte + chunk_size - 1) if i < (num_workers - 1) else total_size - 1
                
                t = threading.Thread(
                    target=download_worker,
                    args=(task_id, url, dest_path, start_byte, end_byte, i, progress_dict, lock)
                )
                t.daemon = True
                threads.append(t)
                t.start()

            while any(t.is_alive() for t in threads):
                if STOP_EVENTS.get(task_id, False):
                    break
                    
                time.sleep(1)
                
                with lock:
                    dl_bytes = progress_dict['downloaded']
                    err = progress_dict['error']
                    
                if err:
                    raise Exception(err)

                now = time.time()
                elapsed = now - info['start_time']
                speed = dl_bytes / elapsed if elapsed > 0 else 0
                
                info['downloaded'] = dl_bytes
                info['elapsed'] = elapsed
                info['speed'] = speed
                info['progress'] = int((dl_bytes / total_size) * 100)
                info['eta'] = (total_size - dl_bytes) / speed if speed > 0 else 0
                
        else:
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                downloaded_bytes = 0
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if STOP_EVENTS.get(task_id, False):
                            return 
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            
                            now = time.time()
                            elapsed = now - info['start_time']
                            speed = downloaded_bytes / elapsed if elapsed > 0 else 0
                            
                            info['downloaded'] = downloaded_bytes
                            info['elapsed'] = elapsed
                            info['speed'] = speed
                            if total_size > 0:
                                info['progress'] = int((downloaded_bytes / total_size) * 100)
                                info['eta'] = (total_size - downloaded_bytes) / speed if speed > 0 else 0
                            else:
                                info['progress'] = 100 

        if not STOP_EVENTS.get(task_id, False):
            info['progress'] = 100
            info['speed'] = 0
            info['eta'] = 0
            info['status'] = 'Completed'
        
    except Exception as e:
        info['status'] = f"Error: {str(e)}"
        info['speed'] = 0
        info['eta'] = 0
    finally:
        if task_id in STOP_EVENTS:
            del STOP_EVENTS[task_id]

def start_thread(task_id):
    STOP_EVENTS[task_id] = False
    thread = threading.Thread(target=download_task, args=(task_id,))
    thread.daemon = True
    thread.start()

# --- ROUTES ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        auth_data = get_auth()
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == auth_data["username"] and check_password_hash(auth_data["password_hash"], password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid username or password.")
            
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/")
@login_required
def index():
    all_folders = get_all_folders()
    settings = get_settings()
    visible_folders = settings.get("visible_folders")

    if visible_folders is None:
        visible_folders = all_folders

    dropdown_folders = [f for f in all_folders if f in visible_folders]
    
    return render_template_string(HTML_TEMPLATE, all_folders=all_folders, visible_folders=visible_folders, dropdown_folders=dropdown_folders)

@app.route("/api/settings", methods=["POST"])
@login_required
def update_settings():
    data = request.json
    
    new_username = data.get("username")
    new_password = data.get("password")
    
    if new_username or new_password:
        auth_data = get_auth()
        final_user = new_username if new_username else auth_data["username"]
        if new_password:
            save_auth(final_user, new_password)
        elif new_username:
            with open(AUTH_FILE, 'w') as f:
                json.dump({
                    "username": final_user,
                    "password_hash": auth_data["password_hash"]
                }, f)
                
    if "visible_folders" in data:
        settings = get_settings()
        settings["visible_folders"] = data.get("visible_folders", [])
        save_settings(settings)
        
    return jsonify({"status": "success"})

@app.route("/api/add", methods=["POST"])
@login_required
def add_download():
    data = request.json
    url = data.get("url")
    folder = data.get("folder")
    subfolder = data.get("subfolder")
    custom_filename = data.get("custom_filename")

    try:
        is_allowed = False
        requested_path = os.path.abspath(folder)

        for allowed_path in PAYLOADR_PATHS:
            allowed_path = os.path.abspath(allowed_path)
            if requested_path == allowed_path or requested_path.startswith(allowed_path + os.sep):
                is_allowed = True
                break
        
        if not is_allowed:
            raise ValueError("Unauthorized base path requested.")

        if subfolder:
            dest_dir = secure_path_join(folder, subfolder)
        else:
            dest_dir = folder

    except ValueError:
        return jsonify({"error": "Security violation: Invalid path structure"}), 403

    task_id = str(uuid.uuid4())
    DOWNLOAD_STATUS[task_id] = {
        "filename": "Resolving metadata...",
        "url": url,
        "base_dir": folder,
        "dest_dir": dest_dir,
        "dest_path": None,
        "subfolder": subfolder if subfolder else "",
        "custom_filename": custom_filename if custom_filename else "",
        "progress": 0,
        "status": "Starting",
        "downloaded": 0,
        "total_size": 0,
        "speed": 0,
        "elapsed": 0,
        "eta": 0
    }
    
    start_thread(task_id)
    return jsonify({"status": "success", "task_id": task_id})

@app.route("/api/action/<task_id>/<action>", methods=["POST"])
@login_required
def task_action(task_id, action):
    if task_id == "all":
        if action == "clear":
            to_remove = [tid for tid, info in DOWNLOAD_STATUS.items() if info['status'] in ['Completed', 'Stopped'] or 'Error' in info['status']]
            for tid in to_remove:
                del DOWNLOAD_STATUS[tid]
        return jsonify({"status": "success"})

    info = DOWNLOAD_STATUS.get(task_id)
    if not info:
        return jsonify({"error": "Task not found"}), 404

    if action == "stop":
        if info['status'] in ['Downloading', 'Connecting...']:
            STOP_EVENTS[task_id] = True
            info['status'] = 'Stopped'
            info['speed'] = 0
            
    elif action == "retry":
        info['progress'] = 0
        info['downloaded'] = 0
        info['speed'] = 0
        info['elapsed'] = 0
        info['eta'] = 0
        info['status'] = 'Starting'
        start_thread(task_id)
        
    elif action == "clear":
        if info['status'] in ['Completed', 'Stopped'] or 'Error' in info['status']:
            del DOWNLOAD_STATUS[task_id]
            if task_id in STOP_EVENTS:
                del STOP_EVENTS[task_id]

    elif action == "delete":
        if info['status'] in ['Downloading', 'Connecting...']:
            STOP_EVENTS[task_id] = True
        
        dest_path = info.get('dest_path')
        dest_dir = info.get('dest_dir')
        
        try:
            if dest_path and os.path.exists(dest_path):
                secure_path_join(info['base_dir'], os.path.relpath(dest_path, info['base_dir']))
                os.remove(dest_path) 
            
            if info.get('subfolder') and dest_dir and os.path.exists(dest_dir):
                if not os.listdir(dest_dir): 
                    os.rmdir(dest_dir)
                    
        except Exception as e:
            return jsonify({"error": f"Failed to delete: {str(e)}"}), 500

        del DOWNLOAD_STATUS[task_id]
        if task_id in STOP_EVENTS:
            del STOP_EVENTS[task_id]

    return jsonify({"status": "success"})

@app.route("/api/status")
@login_required
def status():
    return jsonify(DOWNLOAD_STATUS)

@app.route("/api/homepage")
def homepage_api():
    active_count = sum(1 for info in DOWNLOAD_STATUS.values() if info.get("status") in ["Downloading", "Starting", "Connecting..."])
    completed_count = sum(1 for info in DOWNLOAD_STATUS.values() if info.get("status") == "Completed")
    
    latest_file = "Idle"
    latest_progress = "-"
    
    if DOWNLOAD_STATUS:
        latest_task = list(DOWNLOAD_STATUS.values())[-1]
        latest_file = latest_task['filename']
        latest_progress = f"{latest_task['progress']}%"
        if len(latest_file) > 15:
            latest_file = latest_file[:12] + "..."

    return jsonify({
        "active_downloads": active_count,
        "completed_downloads": completed_count,
        "latest_file": latest_file,
        "latest_progress": latest_progress
    })

init_auth()

if __name__ == "__main__":
    print("🚀 Payloadr is now running on http://0.0.0.0:5000", flush=True)
    app.run(host="0.0.0.0", port=5000, threaded=True)