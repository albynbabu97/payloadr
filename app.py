import os
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
app.secret_key = "payloadr_secret_secure_session_key"

# Read paths from docker-compose, default to /downloads if none provided
PAYLOADR_PATHS = [p.strip() for p in os.environ.get("PAYLOADR_PATHS", "/downloads").split(",") if p.strip()]

# Store the auth file in the first available path so it persists
AUTH_FILE = os.path.join(PAYLOADR_PATHS[0], ".payloadr_auth.json")

DOWNLOAD_STATUS = {}
STOP_EVENTS = {}

# --- AUTHENTICATION LOGIC ---

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
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <style>
        :root { --bg-base: #1e1e2e; --bg-surface: #313244; --bg-surface-hover: #45475a; --text-main: #cdd6f4; --text-muted: #bac2de; --accent: #89b4fa; --danger: #f38ba8; }
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: var(--bg-base); color: var(--text-main); display: flex; justify-content: center; align-items: center; height: 100vh; padding: 15px; box-sizing: border-box; }
        .login-box { background: var(--bg-surface); padding: 40px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); width: 100%; max-width: 350px; text-align: center; border: 1px solid var(--bg-surface-hover); }
        .brand { font-size: 2rem; font-weight: 800; color: var(--accent); display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; text-align: left; }
        label { display: block; margin-bottom: 6px; font-size: 0.85em; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
        input { width: 100%; padding: 12px; box-sizing: border-box; border-radius: 6px; border: 1px solid var(--bg-surface-hover); background: var(--bg-base); color: var(--text-main); font-size: 1rem; transition: 0.2s; }
        input:focus { outline: none; border-color: var(--accent); }
        .btn { width: 100%; background: var(--accent); color: #11111b; border: none; padding: 12px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 1rem; margin-top: 10px; transition: 0.2s; }
        .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
        .error { color: var(--danger); font-size: 0.9em; margin-bottom: 20px; background: rgba(243, 139, 168, 0.1); padding: 10px; border-radius: 6px; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="brand"><i class='bx bx-box'></i> Payloadr</div>
        {% if error %}
            <div class="error"><i class='bx bx-error-circle'></i> {{ error }}</div>
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
            <button type="submit" class="btn">Secure Login</button>
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
    <title>Payloadr Dashboard</title>
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    <style>
        :root {
            --bg-base: #1e1e2e; --bg-surface: #313244; --bg-surface-hover: #45475a; 
            --text-main: #cdd6f4; --text-muted: #bac2de; --accent: #89b4fa; 
            --success: #a6e3a1; --danger: #f38ba8; --warning: #f9e2af; --border-radius: 10px;
        }
        body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: var(--bg-base); color: var(--text-main); overflow-x: hidden; }
        
        header { background: var(--bg-surface); padding: 15px 40px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .brand { font-size: 1.4rem; font-weight: 800; color: var(--accent); letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px; }
        .header-actions { display: flex; gap: 10px; align-items: center; }
        
        .btn { background: var(--accent); color: #11111b; border: none; padding: 10px 15px; border-radius: 6px; cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 6px; transition: 0.2s; font-size: 0.95rem; white-space: nowrap; }
        .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
        .btn-outline { background: transparent; border: 1px solid var(--bg-surface-hover); color: var(--text-main); }
        .btn-outline:hover { background: var(--bg-surface-hover); }
        .btn-icon { background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 6px; border-radius: 4px; transition: 0.2s; font-size: 1.3rem; display: flex; align-items: center; justify-content: center; }
        .btn-icon:hover { background: var(--bg-surface-hover); color: var(--text-main); }
        .btn-icon.danger:hover { background: rgba(243, 139, 168, 0.1); color: var(--danger); }
        
        .container { max-width: 900px; margin: 40px auto; padding: 0 15px; box-sizing: border-box; }
        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--bg-surface-hover); padding-bottom: 10px; }
        .section-header h3 { margin: 0; font-weight: 600; color: var(--text-main); display: flex; align-items: center; gap: 8px; }
        
        .download-item { background: var(--bg-surface); padding: 20px; border-radius: var(--border-radius); margin-bottom: 15px; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-left: 4px solid var(--bg-surface-hover); transition: all 0.3s ease; }
        .task-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
        .task-title { font-weight: 600; font-size: 1.05rem; display: flex; align-items: center; gap: 10px; color: var(--text-main); word-break: break-all; line-height: 1.4; }
        .task-controls { display: flex; gap: 5px; flex-shrink: 0; }
        
        .progress-wrapper { display: flex; align-items: center; gap: 15px; }
        .progress-bg { flex-grow: 1; background: var(--bg-base); border-radius: 10px; height: 8px; overflow: hidden; position: relative; }
        .progress-bar { height: 100%; width: 0%; transition: width 0.3s ease, background-color 0.3s ease; }
        .progress-text { font-size: 0.85rem; font-family: monospace; color: var(--text-muted); width: 45px; text-align: right; flex-shrink: 0; }
        
        .task-meta { font-size: 0.85rem; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .folder-badge { background: var(--bg-base); padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 0.8rem; display: flex; align-items: center; gap: 4px; word-break: break-all; }
        
        .status-Downloading { border-left-color: var(--accent); } .status-Downloading .progress-bar { background: var(--accent); }
        .status-Completed { border-left-color: var(--success); } .status-Completed .progress-bar { background: var(--success); }
        .status-Paused { border-left-color: var(--warning); } .status-Paused .progress-bar { background: var(--warning); }
        .status-Error { border-left-color: var(--danger); } .status-Error .progress-bar { background: var(--danger); }
        .status-Stopped { border-left-color: var(--text-muted); } .status-Stopped .progress-bar { background: var(--text-muted); }
        
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(5px); padding: 15px; }
        .modal { background: var(--bg-surface); padding: 30px; border-radius: var(--border-radius); width: 100%; max-width: 450px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid var(--bg-surface-hover); box-sizing: border-box; }
        .modal h2 { margin-top: 0; margin-bottom: 25px; display: flex; align-items: center; gap: 8px; font-size: 1.3rem; }
        .form-group { margin-bottom: 18px; }
        label { display: block; margin-bottom: 6px; font-size: 0.85em; font-weight: 600; color: var(--text-muted); letter-spacing: 0.5px; text-transform: uppercase; }
        input, select { width: 100%; padding: 12px; box-sizing: border-box; border-radius: 6px; border: 1px solid var(--bg-surface-hover); background: var(--bg-base); color: var(--text-main); font-size: 1rem; transition: border-color 0.2s; }
        input:focus, select:focus { outline: none; border-color: var(--accent); }
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 30px; flex-wrap: wrap; }
        
        .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); background: var(--bg-surface); border-radius: var(--border-radius); border: 1px dashed var(--bg-surface-hover); display: flex; flex-direction: column; align-items: center; gap: 15px; }
        .empty-state i { font-size: 3rem; color: var(--bg-surface-hover); }

        /* --- MOBILE RESPONSIVE STYLES --- */
        @media (max-width: 650px) {
            header { flex-direction: column; gap: 15px; padding: 15px 20px; }
            .header-actions { width: 100%; justify-content: center; flex-wrap: wrap; gap: 8px; }
            .btn { flex: 1; justify-content: center; font-size: 0.9rem; padding: 10px; }
            .btn span { display: none; } /* Hide text on very small screens if needed, or keep for clarity */
            .container { margin: 20px auto; }
            .task-header { flex-direction: column; align-items: flex-start; }
            .task-controls { width: 100%; justify-content: flex-end; background: var(--bg-base); padding: 5px; border-radius: 6px; margin-top: 8px; }
            .task-meta { flex-direction: column; align-items: flex-start; }
            .modal { padding: 20px; }
            .modal-actions .btn { flex: 1; }
        }
    </style>
</head>
<body>
    <header>
        <div class="brand"><i class='bx bx-box'></i> Payloadr</div>
        <div class="header-actions">
            <button class="btn btn-outline" onclick="toggleModal('settingsModal', true)">
                <i class='bx bx-cog'></i>
            </button>
            <button class="btn btn-outline" onclick="actionAll('clear')">
                <i class='bx bx-brush'></i> Clear
            </button>
            <button class="btn" onclick="toggleModal('addModal', true)">
                <i class='bx bx-plus'></i> New
            </button>
            <button class="btn-icon" onclick="window.location.href='/logout'" title="Logout">
                <i class='bx bx-log-out'></i>
            </button>
        </div>
    </header>

    <div class="container">
        <div class="section-header">
            <h3><i class='bx bx-list-ul'></i> Active Queue</h3>
        </div>
        <div id="downloads-container">
            <div class="empty-state">
                <i class='bx bx-ghost'></i>
                <span>Queue is empty. Click <b>New</b> to start.</span>
            </div>
        </div>
    </div>

    <!-- Add Task Modal -->
    <div class="modal-overlay" id="addModal">
        <div class="modal">
            <h2><i class='bx bx-cloud-download'></i> Add New Payload</h2>
            <form id="addForm" onsubmit="submitDownload(event)">
                <div class="form-group">
                    <label>URL (HTTP/HTTPS):</label>
                    <input type="url" id="url" required placeholder="https://example.com/payload.iso" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Destination Location:</label>
                    <select id="folder">
                        {% for folder in folders %}
                        <option value="{{ folder }}">{{ folder }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Subfolder Name (Optional):</label>
                    <input type="text" id="subfolder" placeholder="e.g., ubuntu_iso" autocomplete="off">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-outline" onclick="toggleModal('addModal', false)">Cancel</button>
                    <button type="submit" class="btn"><i class='bx bx-play'></i> Start Download</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Settings Modal -->
    <div class="modal-overlay" id="settingsModal">
        <div class="modal">
            <h2><i class='bx bx-cog'></i> Account Settings</h2>
            <form id="settingsForm" onsubmit="updateCredentials(event)">
                <div class="form-group">
                    <label>New Username:</label>
                    <input type="text" id="newUsername" required placeholder="admin" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>New Password:</label>
                    <input type="password" id="newPassword" required placeholder="••••••••" autocomplete="new-password">
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn btn-outline" onclick="toggleModal('settingsModal', false)">Cancel</button>
                    <button type="submit" class="btn"><i class='bx bx-save'></i> Save</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const sanitize = (str) => {
            const div = document.createElement('div');
            div.innerText = str;
            return div.innerHTML;
        };

        function toggleModal(modalId, show) {
            document.getElementById(modalId).style.display = show ? 'flex' : 'none';
            if(show && modalId === 'addModal') document.getElementById('url').focus();
        }

        async function submitDownload(e) {
            e.preventDefault();
            const payload = {
                url: document.getElementById('url').value,
                folder: document.getElementById('folder').value,
                subfolder: document.getElementById('subfolder').value
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

        async function updateCredentials(e) {
            e.preventDefault();
            const payload = {
                username: document.getElementById('newUsername').value,
                password: document.getElementById('newPassword').value
            };
            const res = await fetch('/api/settings/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                alert("Credentials updated successfully. Please log in again.");
                window.location.href = '/logout';
            } else {
                alert("Failed to update credentials.");
            }
        }

        async function triggerAction(taskId, action) {
            if (action === 'delete') {
                if (!confirm("Are you sure you want to permanently delete this downloaded file from the server?")) return;
            }
            const res = await fetch(`/api/action/${taskId}/${action}`, { method: 'POST' });
            if (res.status === 401) return window.location.reload();
            updateProgress();
        }

        async function actionAll(action) {
            const res = await fetch(`/api/action/all/${action}`, { method: 'POST' });
            if (res.status === 401) return window.location.reload();
            updateProgress();
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function updateProgress() {
            fetch('/api/status')
                .then(res => {
                    if (res.status === 401) window.location.reload();
                    return res.json();
                })
                .then(data => {
                    const container = document.getElementById('downloads-container');
                    
                    if (Object.keys(data).length === 0) {
                        container.innerHTML = `
                            <div class="empty-state">
                                <i class='bx bx-ghost'></i>
                                <span>Queue is empty. Click <b>New</b> to start.</span>
                            </div>`;
                        return;
                    }

                    let html = '';
                    for (const [taskId, info] of Object.entries(data)) {
                        let controls = '';
                        if (info.status === 'Downloading' || info.status === 'Connecting...') {
                            controls += `<button class="btn-icon" title="Pause" onclick="triggerAction('${taskId}', 'pause')"><i class='bx bx-pause'></i></button>`;
                            controls += `<button class="btn-icon" title="Stop" onclick="triggerAction('${taskId}', 'stop')"><i class='bx bx-stop'></i></button>`;
                        } else if (info.status === 'Paused') {
                            controls += `<button class="btn-icon" title="Resume" onclick="triggerAction('${taskId}', 'resume')"><i class='bx bx-play'></i></button>`;
                            controls += `<button class="btn-icon" title="Stop" onclick="triggerAction('${taskId}', 'stop')"><i class='bx bx-stop'></i></button>`;
                        } else if (info.status === 'Completed' || info.status === 'Stopped' || info.status.includes('Error')) {
                            controls += `<button class="btn-icon" title="Retry Download" onclick="triggerAction('${taskId}', 'retry')"><i class='bx bx-refresh'></i></button>`;
                            controls += `<button class="btn-icon" title="Clear from List" onclick="triggerAction('${taskId}', 'clear')"><i class='bx bx-x'></i></button>`;
                            controls += `<button class="btn-icon danger" title="Delete File from Server" onclick="triggerAction('${taskId}', 'delete')"><i class='bx bxs-trash'></i></button>`;
                        }

                        let cssStatus = info.status.split(' ')[0]; 
                        if(info.status.includes('Error')) cssStatus = 'Error';

                        let folderDisplay = info.subfolder ? `${info.base_dir}/${info.subfolder}` : info.base_dir;

                        html += `
                            <div class="download-item status-${cssStatus}">
                                <div class="task-header">
                                    <div class="task-title"><i class='bx bx-file'></i> ${sanitize(info.filename)}</div>
                                    <div class="task-controls">${controls}</div>
                                </div>
                                <div class="progress-wrapper">
                                    <div class="progress-bg">
                                        <div class="progress-bar" style="width: ${info.progress}%;"></div>
                                    </div>
                                    <div class="progress-text">${info.progress}%</div>
                                </div>
                                <div class="task-meta">
                                    <span>${sanitize(info.status)}</span>
                                    <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
                                        <span class="folder-badge"><i class='bx bx-folder'></i> ${sanitize(folderDisplay)}</span>
                                        <span>${formatBytes(info.downloaded)} / ${info.total_size > 0 ? formatBytes(info.total_size) : 'Unknown'}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }
                    container.innerHTML = html;
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

def get_folders():
    folders = []
    # Only iterate top level to prevent hanging the UI on massive media directories
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

# --- DOWNLOAD ENGINE ---

def download_task(task_id):
    info = DOWNLOAD_STATUS.get(task_id)
    if not info: return

    url = info['url']
    headers = {}
    file_mode = 'wb'
    downloaded_bytes = 0
    dest_path = info.get('dest_path')
    
    if dest_path and os.path.exists(dest_path) and info['status'] == 'Paused':
        downloaded_bytes = os.path.getsize(dest_path)
        headers['Range'] = f'bytes={downloaded_bytes}-'
        file_mode = 'ab'

    info['status'] = 'Connecting...'
    info['downloaded'] = downloaded_bytes
    
    try:
        if not (url.startswith('http://') or url.startswith('https://')):
            raise ValueError("Only HTTP/HTTPS URLs are allowed.")

        with requests.get(url, headers=headers, stream=True, timeout=15) as r:
            r.raise_for_status()
            
            if not dest_path:
                content_disp = r.headers.get('content-disposition')
                fname = None
                
                if content_disp:
                    _, options = parse_options_header(content_disp)
                    fname = options.get('filename')
                
                if not fname:
                    parsed = urlparse(url)
                    fname = os.path.basename(parsed.path)
                    if not fname:
                        fname = "payload.bin"
                
                base_name, ext = os.path.splitext(fname)
                counter = 1
                proposed_path = secure_path_join(info['dest_dir'], fname)
                
                while os.path.exists(proposed_path):
                    fname = f"{base_name}_{counter}{ext}"
                    proposed_path = secure_path_join(info['dest_dir'], fname)
                    counter += 1
                
                dest_path = proposed_path
                info['dest_path'] = dest_path
                info['filename'] = fname
            
            if r.status_code == 200 and downloaded_bytes > 0:
                downloaded_bytes = 0
                file_mode = 'wb'
                info['downloaded'] = 0

            content_length = r.headers.get('content-length')
            if content_length:
                total_size = downloaded_bytes + int(content_length)
                info['total_size'] = total_size
            else:
                total_size = info.get('total_size', 0)

            info['status'] = 'Downloading'
            
            with open(dest_path, file_mode) as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if STOP_EVENTS.get(task_id, False):
                        return 
                        
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        info['downloaded'] = downloaded_bytes
                        if total_size > 0:
                            info['progress'] = int((downloaded_bytes / total_size) * 100)
                        else:
                            info['progress'] = 100 

        info['progress'] = 100
        info['status'] = 'Completed'
        
    except Exception as e:
        info['status'] = f"Error: {str(e)}"
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
    return render_template_string(HTML_TEMPLATE, folders=get_folders())

@app.route("/api/settings/auth", methods=["POST"])
@login_required
def update_auth():
    data = request.json
    new_username = data.get("username")
    new_password = data.get("password")
    
    if new_username and new_password:
        save_auth(new_username, new_password)
        return jsonify({"status": "success"})
    return jsonify({"error": "Invalid input"}), 400

@app.route("/api/add", methods=["POST"])
@login_required
def add_download():
    data = request.json
    url = data.get("url")
    folder = data.get("folder")
    subfolder = data.get("subfolder")

    try:
        # Security: Ensure the requested base folder is one of our explicitly allowed paths
        is_allowed = False
        for allowed_path in PAYLOADR_PATHS:
            if os.path.abspath(folder).startswith(os.path.abspath(allowed_path)):
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

    os.makedirs(dest_dir, exist_ok=True)

    task_id = str(uuid.uuid4())
    DOWNLOAD_STATUS[task_id] = {
        "filename": "Resolving metadata...",
        "url": url,
        "base_dir": folder,
        "dest_dir": dest_dir,
        "dest_path": None,
        "subfolder": subfolder if subfolder else "",
        "progress": 0,
        "status": "Starting",
        "downloaded": 0,
        "total_size": 0
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

    if action == "pause":
        if info['status'] in ['Downloading', 'Connecting...']:
            STOP_EVENTS[task_id] = True
            info['status'] = 'Paused'
            
    elif action == "stop":
        if info['status'] in ['Downloading', 'Paused', 'Connecting...']:
            STOP_EVENTS[task_id] = True
            info['status'] = 'Stopped'
            
    elif action == "resume":
        if info['status'] == 'Paused':
            info['status'] = 'Resuming...'
            start_thread(task_id)
            
    elif action == "retry":
        info['progress'] = 0
        info['downloaded'] = 0
        info['status'] = 'Starting'
        start_thread(task_id)
        
    elif action == "clear":
        if info['status'] in ['Completed', 'Stopped'] or 'Error' in info['status']:
            del DOWNLOAD_STATUS[task_id]
            if task_id in STOP_EVENTS:
                del STOP_EVENTS[task_id]

    elif action == "delete":
        if info['status'] in ['Downloading', 'Paused', 'Connecting...']:
            STOP_EVENTS[task_id] = True
        
        dest_path = info.get('dest_path')
        dest_dir = info.get('dest_dir')
        
        try:
            if dest_path and os.path.exists(dest_path):
                # Using the base_dir to ensure we only delete within allowed bounds
                secure_path_join(info['base_dir'], os.path.relpath(dest_path, info['base_dir']))
                os.remove(dest_path) 
            
            # Only attempt to delete the folder if it was a custom subfolder, never the base mount
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

if __name__ == "__main__":
    for path in PAYLOADR_PATHS:
        os.makedirs(path, exist_ok=True)
    init_auth()
    print("🚀 Payloadr is now running on http://0.0.0.0:5000", flush=True)
    app.run(host="0.0.0.0", port=5000, threaded=True)