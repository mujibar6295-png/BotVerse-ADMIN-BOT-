import json
import logging
import os
import sqlite3
import threading
from flask import Flask, request, jsonify
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- Configuration ----------------- #
BOT_TOKEN = "8968521212:AAE_9OoFOeMMdLIvoy5RQNzZ41J0pnweULg"
ADMIN_ID = 5624448603
PORT = int(os.environ.get("PORT", 8080))
DB_FILE = "admin_hub.db"
# ------------------------------------------------- #

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- SQLite Central Database --- #
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS connected_bots (
    auth_code TEXT PRIMARY KEY,
    bot_name TEXT,
    bot_username TEXT,
    settings_json TEXT
)
""")
conn.commit()

# --- Flask Remote Engine --- #
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "BotVerse Central Admin API Engine Active", 200

@flask_app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    code = data.get("auth_code")
    name = data.get("bot_name")
    username = data.get("bot_username")
    settings = json.dumps(data.get("settings", {}))

    if not code or not name:
        return jsonify({"status": "error", "msg": "Invalid data"}), 400

    cursor.execute("""
    INSERT OR REPLACE INTO connected_bots (auth_code, bot_name, bot_username, settings_json)
    VALUES (?, ?, ?, ?)
    """, (code, name, username, settings))
    conn.commit()
    return jsonify({"status": "success", "msg": "Bot registered"}), 200

@flask_app.route("/api/get_settings/<username>", methods=["GET"])
def api_get_settings(username):
    cursor.execute("SELECT settings_json FROM connected_bots WHERE bot_username = ?", (username,))
    row = cursor.fetchone()
    if row:
        return jsonify({"status": "success", "settings": json.loads(row[0])}), 200
    return jsonify({"status": "error", "msg": "Bot not found"}), 404

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# --- Telegram Admin Interface --- #
ADMIN_STATE = {}

def get_all_bots():
    cursor.execute("SELECT auth_code, bot_name FROM connected_bots")
    return cursor.fetchall()

def get_bot_by_code(code):
    cursor.execute("SELECT bot_name, bot_username, settings_json FROM connected_bots WHERE auth_code = ?", (code,))
    return cursor.fetchone()

def get_bot_by_name(name):
    cursor.execute("SELECT auth_code, bot_username, settings_json FROM connected_bots WHERE bot_name = ?", (name,))
    return cursor.fetchone()

def update_setting(code, key, val):
    row = get_bot_by_code(code)
    if row:
        settings = json.loads(row[2])
        if str(val).isdigit():
            settings[key] = int(val)
        else:
            try:
                settings[key] = float(val)
            except ValueError:
                settings[key] = str(val)

        cursor.execute("UPDATE connected_bots SET settings_json = ? WHERE auth_code = ?", (json.dumps(settings), code))
        conn.commit()
        return True
    return False

def build_main_keyboard():
    bots = get_all_bots()
    kb = []
    row = []
    for _, name in bots:
        row.append(KeyboardButton(f"🤖 {name}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([KeyboardButton("🔄 Refresh List")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def build_settings_keyboard(settings):
    kb = []
    row = []
    for k in settings.keys():
        row.append(KeyboardButton(f"⚙️ {k.replace('_', ' ').title()}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([KeyboardButton("🔙 Back to Bots")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    ADMIN_STATE.clear()
    await update.message.reply_text(
        "👑 **BotVerse Admin Master Panel**\n\n"
        "Manage your connected bots from the keyboard below:\n"
        "To connect a new bot, run: `/add <code>`",
        reply_markup=build_main_keyboard(),
        parse_mode="Markdown"
    )

async def add_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/add <auth_code>`", parse_mode="Markdown")
        return
    code = context.args[0].strip()
    data = get_bot_by_code(code)
    if data:
        await update.message.reply_text(
            f"✅ **Bot Connected Successfully!**\n\n"
            f"🤖 Name: **{data[0]}**\n"
            f"🔗 Username: @{data[1]}",
            reply_markup=build_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Auth code not found. Make sure you generated the code via `/api` in your child bot.")

async def keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    text = update.message.text.strip()

    # Value update handler
    if user_id in ADMIN_STATE and ADMIN_STATE[user_id].get("action") == "awaiting_value":
        if text in ["🔙 Back to Bots", "/cancel"]:
            ADMIN_STATE.pop(user_id, None)
            await update.message.reply_text("Cancelled.", reply_markup=build_main_keyboard())
            return

        code = ADMIN_STATE[user_id]["code"]
        key = ADMIN_STATE[user_id]["key"]
        update_setting(code, key, text)

        data = get_bot_by_code(code)
        settings = json.loads(data[2])
        ADMIN_STATE[user_id] = {"action": "viewing_settings", "code": code}

        clean_title = key.replace("_", " ").title()
        await update.message.reply_text(
            f"✅ `{clean_title}` updated to: `{text}`",
            reply_markup=build_settings_keyboard(settings),
            parse_mode="Markdown"
        )
        return

    # Navigation buttons
    if text == "🔙 Back to Bots" or text == "🔄 Refresh List":
        ADMIN_STATE.pop(user_id, None)
        await update.message.reply_text("📋 Connected Bots:", reply_markup=build_main_keyboard())
        return

    # Bot selection
    if text.startswith("🤖 "):
        name = text.replace("🤖 ", "").strip()
        data = get_bot_by_name(name)
        if data:
            code, username, settings_str = data
            settings = json.loads(settings_str)
            ADMIN_STATE[user_id] = {"action": "viewing_settings", "code": code}
            summary = f"⚙️ **{name}** (@{username})\n\nCurrent Configuration:\n"
            for k, v in settings.items():
                summary += f"• **{k.replace('_', ' ').title()}:** `{v}`\n"
            summary += "\nTap any setting below to update its value:"
            await update.message.reply_text(summary, reply_markup=build_settings_keyboard(settings), parse_mode="Markdown")
        return

    # Setting selection
    if text.startswith("⚙️ "):
        if user_id not in ADMIN_STATE or "code" not in ADMIN_STATE[user_id]:
            await update.message.reply_text("Please select a bot first.", reply_markup=build_main_keyboard())
            return
        code = ADMIN_STATE[user_id]["code"]
        raw_key = text.replace("⚙️ ", "").strip()
        data = get_bot_by_code(code)
        settings = json.loads(data[2])

        target_key = next((k for k in settings if k.replace('_', ' ').title().lower() == raw_key.lower()), None)
        if target_key:
            ADMIN_STATE[user_id] = {"action": "awaiting_value", "code": code, "key": target_key}
            cancel_kb = ReplyKeyboardMarkup([[KeyboardButton("🔙 Back to Bots")]], resize_keyboard=True)
            await update.message.reply_text(
                f"✏️️ **{raw_key}**\n\nCurrent value: `{settings[target_key]}`\n"
                f"Type and send the new value below:",
                reply_markup=cancel_kb,
                parse_mode="Markdown"
            )
        return

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_bot_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keyboard_handler))
    print("⚡ Admin Master Engine is live...")
    app.run_polling()

if __name__ == "__main__":
    main()
