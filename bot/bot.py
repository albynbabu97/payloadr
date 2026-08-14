import os
import time
import requests
import logging
import uuid
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

logging.basicConfig(level=logging.INFO)

# --- Config ---
API_ID = os.environ.get("TELEGRAM_API_ID")
API_HASH = os.environ.get("TELEGRAM_API_HASH")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PAYLOADR_URL = os.environ.get("PAYLOADR_URL", "http://payloadr:5000")
PAYLOADR_API_KEY = os.environ.get("PAYLOADR_API_KEY")

ALLOWED_USERS = [int(i.strip()) for i in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if i.strip()]

# Dynamically load the folder list from docker-compose
FOLDER_LIST = [p.strip() for p in os.environ.get("PAYLOADR_PATHS", "/downloads").split(",") if p.strip()]

app = Client("homelab_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Temporary Storage for Interactive Menus ---
PENDING_URLS = {}   # req_id -> {"url": url, "name": name, "sub": sub}
PENDING_FILES = {}  # req_id -> message_id (to retrieve the file later)

# --- Formatters ---
def format_bytes(size):
    if not size: return "0 B"
    power, n = 2**10, 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def format_time(seconds):
    if not seconds or seconds < 0: return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

# --- UI Helpers ---
def build_folder_keyboard(prefix, req_id):
    """Dynamically builds a 2-column keyboard from PAYLOADR_PATHS"""
    buttons = []
    row = []
    for f in FOLDER_LIST:
        row.append(InlineKeyboardButton(f"📁 {f}", callback_data=f"{prefix}|{req_id}|{f}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def get_status_ui():
    try:
        res = requests.get(f"{PAYLOADR_URL}/api/status", headers={"X-API-KEY": PAYLOADR_API_KEY}, timeout=5)
        if res.status_code != 200:
            return "❌ Could not fetch status from server.", None
        
        tasks = res.json()
        if not tasks:
            return "📭 No active or recent downloads.", None

        lines = ["**📊 Download Queue:**\n"]
        buttons = []

        for task_id, info in tasks.items():
            name = info.get("filename", "Unknown")
            status = info.get("status", "")
            prog = info.get("progress", 0)
            short_name = name[:15] + "..." if len(name) > 15 else name

            if status in ["Downloading", "Connecting...", "Starting"]:
                lines.append(f"🔄 **{name}**")
                lines.append(f"├ Status: {status} ({prog}%)")
                lines.append(f"├ DL: {format_bytes(info.get('downloaded'))} / {format_bytes(info.get('total_size'))}")
                lines.append(f"└ Spd: {format_bytes(info.get('speed'))}/s | ETA: {format_time(info.get('eta'))}\n")
                buttons.append([InlineKeyboardButton(f"🛑 Stop: {short_name}", callback_data=f"act|stop|{task_id}")])
                
            elif status == "Completed":
                lines.append(f"✅ **{name}** (Completed)\n")
            else:
                lines.append(f"⏸ **{name}** ({status})\n")
                buttons.append([InlineKeyboardButton(f"🔄 Retry: {short_name}", callback_data=f"act|retry|{task_id}")])

        buttons.append([InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status")])
        return "\n".join(lines), InlineKeyboardMarkup(buttons)
    except Exception as e:
        return f"❌ Error connecting to backend: {e}", None


# --- Command Handlers ---
@app.on_message(filters.user(ALLOWED_USERS) & filters.command("status"))
async def status_command(client, message: Message):
    text, markup = get_status_ui()
    await message.reply_text(text, reply_markup=markup)

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex("^refresh_status$"))
async def refresh_callback(client, callback_query: CallbackQuery):
    text, markup = get_status_ui()
    if callback_query.message.text != text:
        await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer("Status updated!")

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^act\|(stop|retry)\|(.+)$"))
async def action_callback(client, callback_query: CallbackQuery):
    action = callback_query.matches[0].group(1)
    task_id = callback_query.matches[0].group(2)
    try:
        requests.post(f"{PAYLOADR_URL}/api/action/{task_id}/{action}", headers={"X-API-KEY": PAYLOADR_API_KEY}, timeout=5)
        await callback_query.answer(f"Command '{action}' sent!")
        text, markup = get_status_ui()
        await callback_query.message.edit_text(text, reply_markup=markup)
    except Exception as e:
        await callback_query.answer(f"Error: {e}", show_alert=True)


# --- URL Parsing Flow ---
@app.on_message(filters.user(ALLOWED_USERS) & filters.text & ~filters.command("status"))
async def handle_text_input(client, message: Message):
    text = message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        return

    # Parse based on lines: URL -> Name -> Subfolder
    lines = [line.strip() for line in text.split("\n")]
    url = lines[0]
    custom_name = lines[1] if len(lines) > 1 else ""
    subfolder = lines[2] if len(lines) > 2 else ""

    req_id = str(uuid.uuid4())[:8]
    PENDING_URLS[req_id] = {"url": url, "name": custom_name, "sub": subfolder}
    
    markup = build_folder_keyboard("url", req_id)
    
    prompt = f"🔗 **URL Detected**\n"
    if custom_name: prompt += f"📄 Name: `{custom_name}`\n"
    if subfolder: prompt += f"📂 Sub: `{subfolder}`\n"
    prompt += "\nWhere should I save this?"
    
    await message.reply_text(prompt, reply_markup=markup)

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^url\|([^\|]+)\|(.+)$"))
async def handle_url_folder_selection(client, callback_query: CallbackQuery):
    req_id = callback_query.matches[0].group(1)
    folder = callback_query.matches[0].group(2)
    
    data = PENDING_URLS.get(req_id)
    if not data:
        await callback_query.message.edit_text("❌ Request expired.")
        return
        
    del PENDING_URLS[req_id]
    await callback_query.message.edit_text(f"⏳ Queuing to `{folder}`...")
    
    payload = {
        "url": data["url"],
        "folder": folder,
        "subfolder": data["sub"],
        "custom_filename": data["name"]
    }
    try:
        res = requests.post(f"{PAYLOADR_URL}/api/add", json=payload, headers={"X-API-KEY": PAYLOADR_API_KEY}, timeout=5)
        if res.status_code == 200:
            success_text = f"✅ **Queued to {folder}**"
            if data['sub']: success_text += f"\n📂 Sub: `{data['sub']}`"
            if data['name']: success_text += f"\n📄 Name: `{data['name']}`"
            await callback_query.message.edit_text(success_text)
        else:
            await callback_query.message.edit_text(f"❌ Failed: {res.text}")
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Error reaching downloader: {e}")


# --- Telegram File Forwarding Flow ---
@app.on_message(filters.user(ALLOWED_USERS) & (filters.document | filters.video | filters.audio | filters.photo))
async def handle_file_input(client, message: Message):
    # Store the message ID so we can download it later
    req_id = str(uuid.uuid4())[:8]
    PENDING_FILES[req_id] = message.id
    
    file_name = getattr(message.document or message.video or message.audio, 'file_name', 'Unknown File')
    
    markup = build_folder_keyboard("file", req_id)
    await message.reply_text(f"📁 **File Received:** `{file_name}`\nWhere should I save this?", reply_markup=markup)

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^file\|([^\|]+)\|(.+)$"))
async def handle_file_folder_selection(client, callback_query: CallbackQuery):
    req_id = callback_query.matches[0].group(1)
    folder = callback_query.matches[0].group(2)
    
    msg_id = PENDING_FILES.get(req_id)
    if not msg_id:
        await callback_query.message.edit_text("❌ Request expired.")
        return
        
    del PENDING_FILES[req_id]
    
    # Retrieve the original message containing the file
    original_message = await client.get_messages(callback_query.message.chat.id, message_ids=msg_id)
    
    await callback_query.message.edit_text(f"⬇️ Starting file stream directly to `{folder}`...")
    
    last_update_time = time.time()
    async def progress(current, total):
        nonlocal last_update_time
        now = time.time()
        # Update UI every 3 seconds
        if now - last_update_time > 3.0:
            percent = int((current / total) * 100)
            try:
                await callback_query.message.edit_text(
                    f"⬇️ Streaming to `{folder}`: {percent}%\n"
                    f"├ {format_bytes(current)} / {format_bytes(total)}"
                )
                last_update_time = now
            except:
                pass 

    try:
        file_path = await original_message.download(
            file_name=f"{folder}/",
            progress=progress
        )
        filename = os.path.basename(file_path)
        await callback_query.message.edit_text(f"✅ File successfully saved as:\n`{folder}/{filename}`")
    except Exception as e:
        logging.error(f"Failed: {e}")
        await callback_query.message.edit_text(f"❌ Failed to stream file: {e}")

if __name__ == "__main__":
    app.run()