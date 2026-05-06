import sqlite3
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from telegram.helpers import mention_html

import os

TOKEN = os.environ.get("BOT_TOKEN", "8604953355:AAHFptw9DljipSpZlkaC8WH2D0ALX_1SPhM")

#========DB========
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

# ================= USERS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT
)
""")

# ================= GROUPS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    title TEXT
)
""")

# ================= SCAM LIST =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS scam (
    user_id INTEGER PRIMARY KEY,
    reason TEXT
)
""")

# ================= FILTERS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS filters (
    chat_id INTEGER,
    trigger TEXT,
    response TEXT
)
""")

conn.commit()

#======= Owner ========
broadcast_cache = {}
OWNER_ID = 7887025848  # change this

def is_owner(user_id):
    return user_id == OWNER_ID
# ================= HELPERS =================

def add_scam(user_id, reason):
    cursor.execute(
        "INSERT OR REPLACE INTO scam (user_id, reason) VALUES (?, ?)",
        (user_id, reason)
    )
    conn.commit()

def remove_scam(user_id):
    cursor.execute("DELETE FROM scam WHERE user_id=?", (user_id,))
    conn.commit()

def get_scam(user_id):
    cursor.execute("SELECT reason FROM scam WHERE user_id=?", (user_id,))
    return cursor.fetchone()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in ["administrator", "creator"]

def clean_users():
    cursor.execute("SELECT rowid, user_id FROM users")
    data = cursor.fetchall()

    for row in data:
        rowid = row[0]
        user_id = row[1]

        # invalid cases
        if not user_id:
            cursor.execute("DELETE FROM users WHERE rowid=?", (rowid,))

    conn.commit()

clean_users()

def normalize_user(user_id, first, last):
    try:
        user_id = int(user_id)
    except:
        return None

    first = first or ""
    last = last or ""

    name = f"{first} {last}".strip()

    if not name:
        name = "User"

    return user_id, name
    
    from telegram.helpers import mention_html

def safe_mention(user_id, name):
    try:
        return mention_html(user_id, name)
    except:
        return name  # fallback text only
# ================= TARGET FINDER =================

async def get_target(update, context):
    msg = update.message

    # reply (BEST)
    if msg.reply_to_message:
        return msg.reply_to_message.from_user

    # username
    if context.args:
        username = context.args[0].replace("@", "").lower()

        members = await context.bot.get_chat_administrators(update.effective_chat.id)

        for m in members:
            if m.user.username and m.user.username.lower() == username:
                return m.user

    return None
# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    text = f"""
🤖 <b>OrinX Scammer Bot</b>

👋 Welcome {user.first_name}

━━━━━━━━━━━━━━━

👤 <b>Member Commands</b>
/search - Check user
/filters - View filters

━━━━━━━━━━━━━━━

🛡 <b>Admin Commands</b>
/addlist
/rmlist
/mute
/unmute
/ban
/unban
/filter
/broadcast

━━━━━━━━━━━━━━━

👑 <b>Owner Commands</b>
/adminadd
/rmadmin

━━━━━━━━━━━━━━━

⚡ Status: ONLINE
"""

    await update.message.reply_text(text, parse_mode="HTML")
#====== Filter =======
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin / Owner only")

    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /filter Hi Hi ပါဗျ")

    trigger = context.args[0].lower()
    response = " ".join(context.args[1:])

    chat_id = update.effective_chat.id

    cursor.execute(
        "INSERT INTO filters (chat_id, trigger, response) VALUES (?, ?, ?)",
        (chat_id, trigger, response)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Filter added:\n{trigger} → {response}")
    
#======== Filters =========
async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin / Owner only")

    chat_id = update.effective_chat.id

    cursor.execute(
        "SELECT trigger, response FROM filters WHERE chat_id=?",
        (chat_id,)
    )
    data = cursor.fetchall()

    if not data:
        return await update.message.reply_text("❌ No filters found")

    text = "📌 FILTER LIST:\n\n"

    for t, r in data:
        text += f"🔹 {t} → {r}\n"

    await update.message.reply_text(text)
    
async def filter_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text.lower()
    chat_id = update.effective_chat.id

    cursor.execute(
        "SELECT response FROM filters WHERE chat_id=? AND trigger=?",
        (chat_id, text)
    )
    data = cursor.fetchone()

    if data:
        await msg.reply_text(data[0])
        
# 🔹 ADD SCAMMER
async def addlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"

    add_scam(target.id, reason)

    await update.message.reply_text(
        f"""🚨 SCAM ADDED
👤 {target.first_name}
🆔 {target.id}
📝 {reason}"""
    )

#=======Broadcast=======
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_owner(user.id):
        return await update.message.reply_text("❌ Owner only")

    msg = update.message

    if len(context.args) < 1:
        return await msg.reply_text("Usage: /broadcast [mode] [target?] text")

    raw = context.args

    mode = raw[0].lower()
    target = None
    text = ""

    # =========================
    # PARSE INPUT
    # =========================

    if mode in ["user", "group"]:
        if len(raw) >= 3 and raw[1].startswith("@"):
            target = raw[1].replace("@", "")
            text = " ".join(raw[2:])
            mode = f"{mode}_name"
        elif len(raw) >= 3:
            target = raw[1]
            text = " ".join(raw[2:])
            mode = f"{mode}_id"
        else:
            text = " ".join(raw[1:])
    else:
        text = " ".join(raw)

    # =========================
    # MEDIA SUPPORT (reply)
    # =========================

    reply = msg.reply_to_message
    media = None
    media_type = None

    if reply:
        if reply.photo:
            media = reply.photo[-1].file_id
            media_type = "photo"
        elif reply.video:
            media = reply.video.file_id
            media_type = "video"
        elif reply.voice:
            media = reply.voice.file_id
            media_type = "voice"
        elif reply.sticker:
            media = reply.sticker.file_id
            media_type = "sticker"

    # =========================
    # STORE TEMP
    # =========================

    broadcast_cache[user.id] = {
        "mode": mode,
        "target": target,
        "text": text,
        "media": media,
        "media_type": media_type
    }

    # =========================
    # CONFIRM BUTTON
    # =========================

    keyboard = [
        [
            InlineKeyboardButton("✅ SEND", callback_data="bc_yes"),
            InlineKeyboardButton("❌ CANCEL", callback_data="bc_no")
        ]
    ]

    await msg.reply_text(
        f"📣 CONFIRM BROADCAST\n\nMode: {mode}\nTarget: {target}\nText: {text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    #====== Broadcast Callback =======
async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if not is_owner(user_id):
        return await query.edit_message_text("❌ Not allowed")

    data = broadcast_cache.get(user_id)

    if not data:
        return await query.edit_message_text("❌ No pending broadcast")

    # ❌ CANCEL
    if query.data == "bc_no":
        broadcast_cache.pop(user_id, None)
        return await query.edit_message_text("❌ Cancelled")

    mode = data["mode"]
    target = data["target"]
    text = data["text"]
    media = data["media"]
    media_type = data["media_type"]

    sent = 0

    users = []
    groups = []

    # =========================
    # LOAD DB
    # =========================

    cursor.execute("SELECT user_id FROM users")
    all_users = cursor.fetchall()

    cursor.execute("SELECT chat_id FROM groups")
    all_groups = cursor.fetchall()

    # =========================
    # ROUTING
    # =========================

    if mode == "user":
        users = all_users

    elif mode == "group":
        groups = all_groups

    elif mode == "user_id":
        users = [(int(target),)]

    elif mode == "group_id":
        groups = [(int(target),)]

    # =========================
    # SEND FUNCTION
    # =========================

    async def send(uid):
        nonlocal sent
        try:
            if media:
                if media_type == "photo":
                    await context.bot.send_photo(uid, media, caption=text)
                elif media_type == "video":
                    await context.bot.send_video(uid, media, caption=text)
                elif media_type == "voice":
                    await context.bot.send_voice(uid, media)
                elif media_type == "sticker":
                    await context.bot.send_sticker(uid, media)
            else:
                await context.bot.send_message(uid, text)

            sent += 1
        except:
            pass

    # =========================
    # EXECUTE
    # =========================

    for u in users:
        await send(u[0])

    for g in groups:
        await send(g[0])

    broadcast_cache.pop(user_id, None)

    await query.edit_message_text(f"📣 Sent to {sent} targets")
    
# 🔹 REMOVE SCAMMER
async def rmlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    remove_scam(target.id)

    await update.message.reply_text(f"✅ Removed: {target.first_name}")
# 🔹 PROMOTE GROUP ADMIN
async def adminadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            target.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True,
            can_promote_members=False
        )
        await update.message.reply_text(f"👑 Promoted: {target.first_name}")
    except:
        await update.message.reply_text("❌ Bot needs admin rights")

#======= user list =========
from telegram.helpers import mention_html

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id, first_name, last_name FROM users")
    data = cursor.fetchall()

    text = "👤 USERS LIST\n\n"

    for u in data:
        user_id = u[0]

        name = f"{u[1] or ''} {u[2] or ''}".strip()
        if not name:
            name = "User"

        # clickable name
        mention = mention_html(user_id, name)

        # show BOTH id + clickable name
        text += f"🆔 {user_id}\n👤 {mention}\n\n"

    await update.message.reply_text(text, parse_mode="HTML")

#======= group list =======
async def groups_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT chat_id, title FROM groups")
    data = cursor.fetchall()

    text = "🏢 GROUPS LIST\n\n"

    for g in data:
        text += f"ID: {g[0]} | {g[1]}\n"

    await update.message.reply_text(text)
# 🔹 DEMOTE ADMIN
async def rmadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            target.id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_promote_members=False
        )
        await update.message.reply_text(f"🗑 Demoted: {target.first_name}")
    except:
        await update.message.reply_text("❌ Failed")

# 🔍 SEARCH (PRETTY UI)
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    data = get_scam(target.id)

    if data:
        reason = data[0]

        await update.message.reply_text(
            f"""🚨 𝗦𝗖𝗔𝗠𝗠𝗘𝗥 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗

👤 Name: {target.first_name}
🆔 ID: {target.id}

📝 Reason:
{reason}

━━━━━━━━━━━━
⚠️ Status: BLACKLISTED"""
        )
    else:
        await update.message.reply_text(
            f"""🟢 𝗖𝗟𝗘𝗔𝗡 𝗨𝗦𝗘𝗥

👤 Name: {target.first_name}
🆔 ID: {target.id}

━━━━━━━━━━━━
✅ Status: SAFE"""
        )
#======= mute ========
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target.id,
        permissions={
            "can_send_messages": False
        }
    )

    await update.message.reply_text(f"🔇 Muted: {target.first_name}")
#======= unmute =======
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target.id,
        permissions={
            "can_send_messages": True
        }
    )

    await update.message.reply_text(f"🔊 Unmuted: {target.first_name}")
#====== ban ========
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    await context.bot.ban_chat_member(
        update.effective_chat.id,
        target.id
    )

    await update.message.reply_text(f"🚫 Banned: {target.first_name}")
#======= unban =======
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Admin only")

    target = await get_target(update, context)
    if not target:
        return await update.message.reply_text("❌ User not found")

    await context.bot.unban_chat_member(
        update.effective_chat.id,
        target.id
    )

    await update.message.reply_text(f"✅ Unbanned: {target.first_name}")
# ================= ALERT SYSTEM =================
async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    user = msg.from_user
    chat = msg.chat

    data = get_scam(user.id)

    if data:

        reason = data[0]

        admins = await context.bot.get_chat_administrators(chat.id)
        owner = next((a.user for a in admins if a.status == "creator"), None)

        if chat.username:
            link = f"https://t.me/{chat.username}/{msg.message_id}"
        else:
            cid = str(chat.id).replace("-100", "")
            link = f"https://t.me/c/{cid}/{msg.message_id}"

        text = f"""🚨 SCAM ALERT

User: {user.first_name}
ID: {user.id}

Reason: {reason}

🔗 {link}
"""

        # group alert
        await msg.reply_text(
            f"🚨 <a href='tg://user?id={owner.id}'>OWNER</a>\n{text}",
            parse_mode="HTML"
        )

        # DM owner
        try:
            await context.bot.send_message(owner.id, text)
        except:
            pass
       
async def collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    user_id, name = normalize_user(
        user.id,
        user.first_name,
        user.last_name
    )

    if not user_id:
        return

    cursor.execute("""
        INSERT OR REPLACE INTO users 
        (user_id, first_name, last_name)
        VALUES (?, ?, ?)
    """,
    (user_id, user.first_name, user.last_name))

    conn.commit()
# ================= RUN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addlist", addlist))
app.add_handler(CommandHandler("rmlist", rmlist))
app.add_handler(CommandHandler("adminadd", adminadd))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("rmadmin", rmadmin))
app.add_handler(CommandHandler("search", search))
app.add_handler(CommandHandler("filter", add_filter))
app.add_handler(CommandHandler("filters", list_filters))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("unmute", unmute))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("users", users_list))
app.add_handler(CommandHandler("groups", groups_list))

app.add_handler(MessageHandler(filters.ALL, collector))


app.add_handler(CallbackQueryHandler(broadcast_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_watch))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, watch))

print("OrinX Scammer Alert Bot Running⚡")
app.run_polling()