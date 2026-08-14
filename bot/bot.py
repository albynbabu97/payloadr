import os
import time
import requests
import logging
import uuid
import asyncio
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
FOLDER_LIST = [p.strip() for p in os.environ.get("PAYLOADR_PATHS", "/downloads").split(",") if p.strip()]

app = Client("homelab_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- State Management ---
PENDING_URLS = {}   
PENDING_FILES = {}  
ACTIVE_FILE_TRANSFERS = {}  
USER_STATES = {}  # Tracks if a user is currently renaming a file

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

        lines = ["**📊 URL Download Queue:**\n"]
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
                lines.append(f"└ Spd: {format_bytes(info.get('speed'))}/s | Elap: {format_time(info.get('elapsed'))} | ETA: {format_time(info.get('eta'))}\n")
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


# --- URL Command Handlers ---
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

# --- Text Input (Handles both Rename Flow and URLs) ---
@app.on_message(filters.user(ALLOWED_USERS) & filters.text & ~filters.command("status"))
async def handle_text_input(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # 1. Intercept text if the user is in the middle of renaming a file
    if user_id in USER_STATES and USER_STATES[user_id].get("action") == "waiting_rename":
        req_id = USER_STATES[user_id]["req_id"]
        new_name = text
        del USER_STATES[user_id] # Clear state
        
        if req_id in PENDING_FILES:
            PENDING_FILES[req_id]["custom_name"] = new_name
            status_msg = await message.reply_text("⏳ Preparing download...")
            await start_file_transfer(client, message.chat.id, status_msg, req_id)
        return

    # 2. Standard URL handling
    if not (text.startswith("http://") or text.startswith("https://")):
        return

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
        return await callback_query.message.edit_text("❌ Request expired.")
        
    del PENDING_URLS[req_id]
    await callback_query.message.edit_text(f"⏳ Queuing to `{folder}`...")
    
    payload = {"url": data["url"], "folder": folder, "subfolder": data["sub"], "custom_filename": data["name"]}
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


# --- Telegram File Forwarding Flow (Upgraded with Rename & Subfolders) ---
@app.on_message(filters.user(ALLOWED_USERS) & (filters.document | filters.video | filters.audio | filters.photo))
async def handle_file_input(client, message: Message):
    req_id = str(uuid.uuid4())[:8]
    file_name = getattr(message.document or message.video or message.audio, 'file_name', 'Unknown_File')
    _, ext = os.path.splitext(file_name)
    
    # Store file data
    PENDING_FILES[req_id] = {
        "msg_id": message.id,
        "original_name": file_name,
        "ext": ext,
        "folder": None
    }
    
    markup = build_folder_keyboard("file_dir", req_id)
    await message.reply_text(f"📁 **File Received:** `{file_name}`\nWhere should I save this?", reply_markup=markup)

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^file_dir\|([^\|]+)\|(.+)$"))
async def handle_file_folder_selection(client, callback_query: CallbackQuery):
    req_id = callback_query.matches[0].group(1)
    folder = callback_query.matches[0].group(2)
    
    if req_id not in PENDING_FILES:
        return await callback_query.message.edit_text("❌ Request expired.")
        
    PENDING_FILES[req_id]["folder"] = folder
    
    # Step 2: Ask about renaming
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Yes, rename and create subfolder", callback_data=f"file_ren|yes|{req_id}")],
        [InlineKeyboardButton("✅ No, keep original file name", callback_data=f"file_ren|no|{req_id}")]
    ])
    
    await callback_query.message.edit_text(
        f"📂 Target: `{folder}`\n\nDo you want to rename this file and place it in a subfolder?",
        reply_markup=markup
    )

@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^file_ren\|(yes|no)\|(.+)$"))
async def handle_rename_decision(client, callback_query: CallbackQuery):
    choice = callback_query.matches[0].group(1)
    req_id = callback_query.matches[0].group(2)
    
    if req_id not in PENDING_FILES:
        return await callback_query.message.edit_text("❌ Request expired.")
        
    if choice == "no":
        await callback_query.message.edit_text("⏳ Preparing download...")
        await start_file_transfer(client, callback_query.message.chat.id, callback_query.message, req_id)
    else:
        # Put user into rename mode
        USER_STATES[callback_query.from_user.id] = {"action": "waiting_rename", "req_id": req_id}
        await callback_query.message.edit_text("✏️ Please type the new file name (without extension):")

async def start_file_transfer(client, chat_id, status_message: Message, req_id):
    """Executes the actual Pyrogram download logic"""
    data = PENDING_FILES.get(req_id)
    if not data:
        return await status_message.edit_text("❌ Request expired.")
        
    msg_id = data["msg_id"]
    folder = data["folder"]
    ext = data["ext"]
    
    # Determine the final nested path
    if "custom_name" in data:
        clean_name = data["custom_name"].strip()
        # Creates: /downloads/Batman/Batman.mkv
        final_path = os.path.join(folder, clean_name, f"{clean_name}{ext}")
    else:
        # Creates: /downloads/Batman.mkv
        final_path = os.path.join(folder, data["original_name"])
        
    del PENDING_FILES[req_id]
    
    original_message = await client.get_messages(chat_id, message_ids=msg_id)
    await status_message.edit_text(f"⬇️ Starting file stream to `{final_path}`...")
    
    start_time = time.time()
    last_update_time = start_time

    async def progress(current, total):
        nonlocal last_update_time
        now = time.time()
        
        # Update UI every 3 seconds
        if now - last_update_time > 3.0 or current == total:
            percent = int((current / total) * 100) if total > 0 else 0
            elapsed = now - start_time
            speed = current / elapsed if elapsed > 0 else 0
            eta = (total - current) / speed if speed > 0 else 0
            
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("🛑 Stop Streaming", callback_data=f"stop_file|{req_id}")
            ]])
            
            try:
                await status_message.edit_text(
                    f"⬇️ Streaming to `{final_path}`: {percent}%\n"
                    f"├ {format_bytes(current)} / {format_bytes(total)}\n"
                    f"└ Spd: {format_bytes(speed)}/s | Elap: {format_time(elapsed)} | ETA: {format_time(eta)}",
                    reply_markup=markup
                )
                last_update_time = now
            except:
                pass 

    download_coro = original_message.download(
        file_name=final_path,
        progress=progress
    )
    task = asyncio.create_task(download_coro)
    ACTIVE_FILE_TRANSFERS[req_id] = task

    try:
        await task
        if req_id in ACTIVE_FILE_TRANSFERS:
            del ACTIVE_FILE_TRANSFERS[req_id]
            
        await status_message.edit_text(f"✅ File successfully saved to:\n`{final_path}`")
        
    except asyncio.CancelledError:
        await status_message.edit_text("🛑 File stream was stopped by user.")
    except Exception as e:
        if req_id in ACTIVE_FILE_TRANSFERS:
            del ACTIVE_FILE_TRANSFERS[req_id]
        await status_message.edit_text(f"❌ Failed to stream file: {e}")

# --- Handler for the Stop File Button ---
@app.on_callback_query(filters.user(ALLOWED_USERS) & filters.regex(r"^stop_file\|(.+)$"))
async def stop_file_transfer(client, callback_query: CallbackQuery):
    req_id = callback_query.matches[0].group(1)
    
    task = ACTIVE_FILE_TRANSFERS.get(req_id)
    if task:
        task.cancel()
        del ACTIVE_FILE_TRANSFERS[req_id]
        await callback_query.answer("Stopping transfer...", show_alert=False)
    else:
        await callback_query.answer("Transfer already finished or stopped.", show_alert=True)

if __name__ == "__main__":
    app.run()