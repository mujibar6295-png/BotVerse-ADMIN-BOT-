import json
import logging
import os
import sqlite3
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- কনফিগারেশন ----------------- #
BOT_TOKEN = "8968521212:AAE_9OoFOeMMdLIvoy5RQNzZ41J0pnweULg"
ADMIN_ID = 5624448603
PORT = int(os.environ.get("PORT", 8080))
# ---------------------------------------------- #

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Render Keep-Alive Flask Server
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "BotVerse Admin Master Hub is running 24/7!", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ডাটাবেস ইনিশিয়ালাইজেশন
conn = sqlite3.connect("admin_hub.db", check_same_thread=False)
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

ADMIN_STATE = {}

def get_all_bots():
    cursor.execute("SELECT auth_code, bot_name FROM connected_bots")
    return cursor.fetchall()

def get_bot_by_code(auth_code):
    cursor.execute("SELECT bot_name, bot_username, settings_json FROM connected_bots WHERE auth_code = ?", (auth_code,))
    return cursor.fetchone()

def get_bot_by_name(name):
    cursor.execute("SELECT auth_code, bot_username, settings_json FROM connected_bots WHERE bot_name = ?", (name,))
    return cursor.fetchone()

def update_setting(auth_code, setting_key, new_value):
    row = get_bot_by_code(auth_code)
    if row:
        settings = json.loads(row[2])
        if new_value.isdigit():
            settings[setting_key] = int(new_value)
        else:
            try:
                settings[setting_key] = float(new_value)
            except ValueError:
                settings[setting_key] = new_value

        cursor.execute(
            "UPDATE connected_bots SET settings_json = ? WHERE auth_code = ?",
            (json.dumps(settings), auth_code),
        )
        conn.commit()
        return True
    return False

# মেইন কিবোর্ড (নিচের মেনু বাটন)
def build_main_keyboard():
    bots = get_all_bots()
    keyboard = []
    
    row = []
    for _, name in bots:
        row.append(KeyboardButton(f"🤖 {name}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([KeyboardButton("🔄 Refresh List"), KeyboardButton("➕ Add Bot Info")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# সেটিংস কিবোর্ড
def build_settings_keyboard(settings_dict):
    keyboard = []
    row = []
    for key in settings_dict.keys():
        clean_title = key.replace("_", " ").title()
        row.append(KeyboardButton(f"⚙️ {clean_title}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([KeyboardButton("🔙 Back to Bots")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# /start কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    ADMIN_STATE.clear()
    reply_markup = build_main_keyboard()
    await update.message.reply_text(
        "👑 **BotVerse Admin Master Panel**\n\n"
        "ম্যানেজ করতে নিচের কিবোর্ড থেকে নির্দিষ্ট বটে ট্যাপ করুন।\n"
        "নতুন বট জুড়তে ব্যবহার করুন: `/add <code>`",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

# /add <code> কমান্ড
async def add_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("⚠️ ব্যবহার করুন: `/add <bot_code>`", parse_mode="Markdown")
        return

    code = context.args[0].strip()
    bot_data = get_bot_by_code(code)

    if bot_data:
        bot_name, username, _ = bot_data
        reply_markup = build_main_keyboard()
        await update.message.reply_text(
            f"✅ **নতুন বট যোগ হয়েছে!**\n\n"
            f"🤖 নাম: **{bot_name}**\n"
            f"🔗 ইউজারনেম: @{username}\n\n"
            f"কিবোর্ডে বাটন যোগ করা হয়েছে।",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ এই কোডের কোনো বট পাওয়া যায়নি!")

# কিবোর্ড ক্লিকের লজিক
async def handle_keyboard_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    text = update.message.text.strip()

    # ১. ভ্যালু এডিট ইনপুট হ্যান্ডলিং
    if user_id in ADMIN_STATE and ADMIN_STATE[user_id].get("action") == "awaiting_value":
        if text in ["🔙 Back to Bots", "/cancel"]:
            ADMIN_STATE.pop(user_id, None)
            await update.message.reply_text("বাতিল করা হয়েছে।", reply_markup=build_main_keyboard())
            return

        code = ADMIN_STATE[user_id]["code"]
        key = ADMIN_STATE[user_id]["key"]
        update_setting(code, key, text)

        bot_data = get_bot_by_code(code)
        settings = json.loads(bot_data[2])
        ADMIN_STATE[user_id] = {"action": "viewing_settings", "code": code}

        clean_title = key.replace("_", " ").title()
        await update.message.reply_text(
            f"✅ `{clean_title}` পরিবর্তন করে `{text}` করা হয়েছে!",
            reply_markup=build_settings_keyboard(settings),
            parse_mode="Markdown",
        )
        return

    # ২. নেভিগেশন বাটন
    if text == "🔙 Back to Bots":
        ADMIN_STATE.pop(user_id, None)
        await update.message.reply_text("📋 মূল তালিকায় ফিরে আসা হলো:", reply_markup=build_main_keyboard())
        return

    elif text == "🔄 Refresh List":
        await update.message.reply_text("🔄 কিবোর্ড রিফ্রেশ করা হয়েছে:", reply_markup=build_main_keyboard())
        return

    elif text == "➕ Add Bot Info":
        await update.message.reply_text(
            "ℹ️ **নতুন বট যোগ করার নিয়ম:**\n\n"
            "১. আপনার মেইন বটে গিয়ে `/api` কমান্ড দিন।\n"
            "২. মেইন বট একটি কোড রিটার্ন করবে।\n"
            "৩. এখানে এসে `/add <সেই কোড>` লিখুন।\n"
            "৪. নিচের কিবোর্ডে বটের নামসহ বাটন চলে আসবে।",
            parse_mode="Markdown",
        )
        return

    # ৩. বটের বাটন ট্যাপ করলে
    if text.startswith("🤖 "):
        bot_name = text.replace("🤖 ", "").strip()
        bot_data = get_bot_by_name(bot_name)

        if bot_data:
            auth_code, username, settings_json = bot_data
            settings = json.loads(settings_json)
            ADMIN_STATE[user_id] = {"action": "viewing_settings", "code": auth_code}

            summary = f"⚙️ **{bot_name}** (@{username})\n\nবর্তমান মান:\n"
            for k, v in settings.items():
                summary += f"• **{k.replace('_', ' ').title()}:** `{v}`\n"
            summary += "\nযেটি এডিট করতে চান নিচের বাটনে ট্যাপ করুন:"

            await update.message.reply_text(
                summary,
                reply_markup=build_settings_keyboard(settings),
                parse_mode="Markdown",
            )
        return

    # ৪. সেটিংস বাটন ট্যাপ করলে
    if text.startswith("⚙️ "):
        if user_id not in ADMIN_STATE or "code" not in ADMIN_STATE[user_id]:
            await update.message.reply_text("প্রথমে একটি বট সিলেক্ট করুন।", reply_markup=build_main_keyboard())
            return

        code = ADMIN_STATE[user_id]["code"]
        raw_title = text.replace("⚙️ ", "").strip()
        bot_data = get_bot_by_code(code)
        settings = json.loads(bot_data[2])

        target_key = None
        for k in settings.keys():
            if k.replace("_", " ").title().lower() == raw_title.lower():
                target_key = k
                break

        if target_key:
            ADMIN_STATE[user_id] = {"action": "awaiting_value", "code": code, "key": target_key}
            cancel_keyboard = ReplyKeyboardMarkup([[KeyboardButton("🔙 Back to Bots")]], resize_keyboard=True)
            await update.message.reply_text(
                f"✏️ **{raw_title}**\n\nবর্তমান মান: `{settings[target_key]}`\n"
                f"নতুন মানটি কিবোর্ডে লিখে পাঠিয়ে দিন:",
                reply_markup=cancel_keyboard,
                parse_mode="Markdown",
            )
        return

def main():
    # ব্যাকগ্রাউন্ড থ্রেডে Flask সার্ভার চালু করা (Render Web Service-এর জন্য)
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_bot_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_clicks))

    print("⚡ BotVerse Admin Panel is running on Render with Flask keep-alive...")
    app.run_polling()

if __name__ == "__main__":
    main()
