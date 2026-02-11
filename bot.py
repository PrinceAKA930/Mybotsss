import os
import json
import asyncio
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telethon import TelegramClient, errors

# ================================
# ENV VARIABLES
# ================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise Exception("❌ Please set BOT_TOKEN, API_ID, and API_HASH in your environment variables")

try:
    API_ID = int(API_ID)
except:
    raise Exception("❌ API_ID must be an integer")

ADMIN_IDS = [int(x) for x in ADMIN_IDS.split(",") if x.strip().isdigit()]

# ================================
# FILES AND DIRECTORIES
# ================================
DATA_FILE = "data.json"
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ================================
# DATABASE
# ================================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    return json.load(open(DATA_FILE))

def save_data(d):
    json.dump(d, open(DATA_FILE, "w"), indent=2)

db = load_data()

# ================================
# KEYBOARD
# ================================
def keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📱 Login", "🚪 Logout"],
            ["➕ Add Chat", "➖ Remove Chat"],
            ["📋 List Chats"],
            ["📝 Set Message"],
            ["▶ Start Ads", "⏹ Stop Ads"],
            ["⏱ Interval", "📊 Status"],
        ],
        resize_keyboard=True,
    )

# ================================
# HELPERS
# ================================
def get_user(uid):
    uid = str(uid)
    if uid not in db:
        db[uid] = {
            "chats": [],
            "interval": 60,
            "message": "🔥 Default Ad Message 🔥",
            "running": False,
            "state": None,
            "phone": None,
            "phone_code_hash": None
        }
    return db[uid]

async def get_client(uid):
    return TelegramClient(f"{SESSIONS_DIR}/{uid}", API_ID, API_HASH)

# ================================
# ADS LOOP
# ================================
async def ads_loop(uid):
    user = get_user(uid)
    client = await get_client(uid)
    await client.connect()

    while user["running"]:
        try:
            for chat in user["chats"]:
                await client.send_message(chat, user["message"])
            await asyncio.sleep(user["interval"])
        except Exception as e:
            print("❌ Error in ads_loop:", e)
            await asyncio.sleep(5)

    await client.disconnect()

# ================================
# START COMMAND
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 AdBot Ready",
        reply_markup=keyboard(),
    )

# ================================
# MAIN TEXT HANDLER
# ================================
async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    uid = update.message.from_user.id
    user = get_user(uid)

    # =========================
    # LOGIN FLOW
    # =========================
    if msg == "📱 Login":
        user["state"] = "phone"
        save_data(db)
        await update.message.reply_text("Send phone number (+91xxxx)")
        return

    if user["state"] == "phone":
        user["phone"] = msg
        client = await get_client(uid)
        try:
            sent = await client.send_code_request(msg)
            user["phone_code_hash"] = sent.phone_code_hash
            user["state"] = "otp"
            save_data(db)
            await update.message.reply_text("Send OTP like:\ncode12345")
        except errors.PhoneNumberInvalidError:
            await update.message.reply_text("❌ Invalid phone number")
            user["state"] = None
        return

    if user["state"] == "otp":
        if not msg.startswith("code"):
            await update.message.reply_text("Format must be: code12345")
            return
        code = msg[4:]
        client = await get_client(uid)
        try:
            await client.sign_in(
                phone=user["phone"],
                code=code,
                phone_code_hash=user["phone_code_hash"]
            )
            user["state"] = None
            user["phone_code_hash"] = None
            save_data(db)
            await update.message.reply_text("✅ Login successful")
        except errors.SessionPasswordNeededError:
            await update.message.reply_text("❌ Two-step verification enabled, please provide password")
        except Exception as e:
            await update.message.reply_text(f"❌ Login failed: {e}")
        return

    # =========================
    # LOGOUT
    # =========================
    if msg == "🚪 Logout":
        session = f"{SESSIONS_DIR}/{uid}.session"
        if os.path.exists(session):
            os.remove(session)
        await update.message.reply_text("Logged out")
        return

    # =========================
    # SET MESSAGE
    # =========================
    if msg == "📝 Set Message":
        user["state"] = "set_message"
        await update.message.reply_text("Send your ad message text")
        return

    if user["state"] == "set_message":
        user["message"] = msg
        user["state"] = None
        save_data(db)
        await update.message.reply_text("✅ Message updated")
        return

    # =========================
    # CHAT MANAGEMENT
    # =========================
    if msg == "➕ Add Chat":
        user["state"] = "add_chat"
        await update.message.reply_text("Send chat id or username")
        return

    if msg == "➖ Remove Chat":
        user["state"] = "remove_chat"
        await update.message.reply_text("Send chat id to remove")
        return

    if msg == "📋 List Chats":
        await update.message.reply_text(str(user["chats"]))
        return

    if user["state"] == "add_chat":
        user["chats"].append(msg)
        user["state"] = None
        save_data(db)
        await update.message.reply_text("Chat added")
        return

    if user["state"] == "remove_chat":
        if msg in user["chats"]:
            user["chats"].remove(msg)
        user["state"] = None
        save_data(db)
        await update.message.reply_text("Chat removed")
        return

    # =========================
    # INTERVAL
    # =========================
    if msg == "⏱ Interval":
        user["state"] = "interval"
        await update.message.reply_text("Send seconds")
        return

    if user["state"] == "interval":
        try:
            user["interval"] = int(msg)
        except:
            await update.message.reply_text("❌ Enter a valid number")
            return
        user["state"] = None
        save_data(db)
        await update.message.reply_text("Interval updated")
        return

    # =========================
    # ADS
    # =========================
    if msg == "▶ Start Ads":
        if not user["chats"]:
            await update.message.reply_text("Add chats first")
            return
        user["running"] = True
        save_data(db)
        context.application.create_task(ads_loop(uid))
        await update.message.reply_text("Ads started")
        return

    if msg == "⏹ Stop Ads":
        user["running"] = False
        save_data(db)
        await update.message.reply_text("Ads stopped")
        return

    # =========================
    # STATUS
    # =========================
    if msg == "📊 Status":
        await update.message.reply_text(
            f"Chats: {len(user['chats'])}\n"
            f"Interval: {user['interval']}s\n"
            f"Running: {user['running']}\n"
            f"Message:\n{user['message']}"
        )

# ================================
# MAIN
# ================================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, text))
    print("🚀 AdBot running")
    app.run_polling()

if __name__ == "__main__":
    main()
