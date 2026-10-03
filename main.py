import telebot
import sqlite3
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# ================= ⚙️ কনফিগারেশন =================
BOT_TOKEN = '8919161117:AAEFTcbYlxbgduHDmKdcRKeszSY9-szepQ8'
ADMIN_ID = 2132743108  # এখানে আপনার টেলিগ্রাম আইডি দিন

bot = telebot.TeleBot(BOT_TOKEN)

# ================= 🗄️ ডাটাবেস সেটআপ =================
DB_FILE = 'pro_subscription.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# টেবিল তৈরি
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expire_date TIMESTAMP)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS user_channels (user_id INTEGER, chat_id INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS channel_timers (chat_id INTEGER PRIMARY KEY, expire_date TIMESTAMP)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (setting_key TEXT PRIMARY KEY, setting_value TEXT)''')

# ডিফল্ট সাবস্ক্রিপশন মোড ON রাখা
cursor.execute("INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES ('sub_mode', 'ON')")
conn.commit()

# ================= 🛡️ এডমিন কমান্ডস =================

# 🟢 সাবস্ক্রিপশন মোড ON করা (শুধু পেইড ইউজার)
@bot.message_handler(commands=['sub_on'])
def sub_mode_on(message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("UPDATE settings SET setting_value = 'ON' WHERE setting_key = 'sub_mode'")
    conn.commit()
    bot.reply_to(message, "✅ <b>সাবস্ক্রিপশন মোড ON!</b>\nএখন থেকে শুধু মেয়াদ থাকা ইউজাররাই চ্যানেলে ঢুকতে পারবে।", parse_mode='HTML')

# 🔴 সাবস্ক্রিপশন মোড OFF করা (ফ্রি মোড)
@bot.message_handler(commands=['sub_off'])
def sub_mode_off(message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("UPDATE settings SET setting_value = 'OFF' WHERE setting_key = 'sub_mode'")
    conn.commit()
    bot.reply_to(message, "🔓 <b>সাবস্ক্রিপশন মোড OFF! (ফ্রি মোড)</b>\nএখন থেকে যে কেউ রিকোয়েস্ট দিলে বট স্বয়ংক্রিয়ভাবে তাকে ফ্রিতে এক্সেপ্ট করে নেবে।", parse_mode='HTML')

# 📌 ইউজারের সাবস্ক্রিপশন টাইম সেট করা
@bot.message_handler(commands=['add_user'])
def add_user_time(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        days = int(parts[2])
        expire_date = datetime.now() + timedelta(days=days)
        cursor.execute("INSERT OR REPLACE INTO users (user_id, expire_date) VALUES (?, ?)", (user_id, expire_date))
        conn.commit()
        bot.reply_to(message, f"✅ <b>ইউজার সাবস্ক্রিপশন আপডেট!</b>\n👤 আইডি: <code>{user_id}</code>\n⏳ মেয়াদ: {days} দিন", parse_mode='HTML')
    except:
        bot.reply_to(message, "⚠️ <b>ভুল কমান্ড!</b> নিয়ম: <code>/add_user [User_ID] [দিন]</code>", parse_mode='HTML')

# 📌 নির্দিষ্ট চ্যানেলের টাইমার সেট করা (কিল-সুইচ)
@bot.message_handler(commands=['set_channel_timer'])
def set_channel_timer(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        chat_id = int(parts[1])
        days = int(parts[2])
        expire_date = datetime.now() + timedelta(days=days)
        cursor.execute("INSERT OR REPLACE INTO channel_timers (chat_id, expire_date) VALUES (?, ?)", (chat_id, expire_date))
        conn.commit()
        bot.reply_to(message, f"🚨 <b>চ্যানেল টাইমার সেট!</b>\n📢 চ্যানেল: <code>{chat_id}</code>\n⏳ সময়: {days} দিন পর চ্যানেলটি পুরোপুরি লক হয়ে যাবে।", parse_mode='HTML')
    except:
        bot.reply_to(message, "⚠️ <b>ভুল কমান্ড!</b> নিয়ম: <code>/set_channel_timer [Channel_ID] [দিন]</code>", parse_mode='HTML')

# 📌 ম্যানুয়াল ডাটাবেস ব্যাকআপ
@bot.message_handler(commands=['backup'])
def send_backup(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        with open(DB_FILE, 'rb') as doc:
            bot.send_document(ADMIN_ID, doc, caption=f"📁 ডাটাবেস ব্যাকআপ\nসময়: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ ব্যাকআপ নিতে সমস্যা হয়েছে: {e}")

# ================= 🚪 জয়েন রিকোয়েস্ট হ্যান্ডেলার =================
@bot.chat_join_request_handler()
def handle_join_request(message: telebot.types.ChatJoinRequest):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_name = message.chat.title
    now = datetime.now()
    
    # ১. প্রথমে চেক করবে চ্যানেলটি লক (বন্ধ) হয়ে গেছে কিনা
    cursor.execute("SELECT expire_date FROM channel_timers WHERE chat_id = ?", (chat_id,))
    chan_timer = cursor.fetchone()
    if chan_timer:
        chan_expire_date = datetime.strptime(chan_timer[0], '%Y-%m-%d %H:%M:%S.%f')
        if now >= chan_expire_date:
            bot.decline_chat_join_request(chat_id, user_id)
            bot.send_message(user_id, f"🚫 <b>{chat_name}</b> চ্যানেলটির মেয়াদ শেষ এবং এটি স্থায়ীভাবে বন্ধ করে দেওয়া হয়েছে।", parse_mode='HTML')
            return # চ্যানেল লক থাকলে এখানেই কাজ শেষ, আর কাউকে ঢুকতে দেবে না

    # ২. সাবস্ক্রিপশন মোড চেক করা (ফ্রি নাকি পেইড)
    cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'sub_mode'")
    sub_mode = cursor.fetchone()[0]

    # ফ্রি মোড চালু থাকলে সবাইকে অটো-এক্সেপ্ট করবে
    if sub_mode == 'OFF':
        bot.approve_chat_join_request(chat_id, user_id)
        cursor.execute("INSERT INTO user_channels (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
        conn.commit()
        bot.send_message(user_id, f"🎉 <b>{chat_name}</b> চ্যানেলে আপনাকে ফ্রিতে স্বাগতম!", parse_mode='HTML')
        return

    # পেইড মোড চালু থাকলে সাবস্ক্রিপশন চেক করবে
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result:
        expire_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
        if now < expire_date:
            bot.approve_chat_join_request(chat_id, user_id)
            cursor.execute("INSERT INTO user_channels (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
            conn.commit()
            bot.send_message(user_id, f"✅ <b>{chat_name}</b> চ্যানেলে আপনার জয়েন রিকোয়েস্ট এক্সেপ্ট করা হয়েছে!", parse_mode='HTML')
        else:
            bot.decline_chat_join_request(chat_id, user_id)
            bot.send_message(user_id, "❌ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে।")
    else:
        bot.decline_chat_join_request(chat_id, user_id)
        bot.send_message(user_id, "❌ আপনার কোনো অ্যাক্টিভ সাবস্ক্রিপশন নেই।")

# ================= ⏱️ টাইমার চেকার ও অটো-ব্যান =================
def check_timers():
    now = datetime.now()
    
    # ১. চ্যানেল টাইমার চেক (চ্যানেল লক করার জন্য)
    cursor.execute("SELECT chat_id, expire_date FROM channel_timers")
    channel_timers = cursor.fetchall()
    for ct in channel_timers:
        chat_id = ct[0]
        expire_date = datetime.strptime(ct[1], '%Y-%m-%d %H:%M:%S.%f')
        if now >= expire_date:
            cursor.execute("SELECT user_id FROM user_channels WHERE chat_id = ?", (chat_id,))
            users_in_chat = cursor.fetchall()
            
            # চ্যানেলে থাকা সবাইকে ব্যান করা
            for u in users_in_chat:
                try: bot.ban_chat_member(chat_id, u[0])
                except: pass
            
            # ইউজারদের ডাটা মুছে দেওয়া, কিন্তু চ্যানেল টাইমার ডাটাবেসে রেখে দেওয়া হবে (লক মোডের জন্য)
            cursor.execute("DELETE FROM user_channels WHERE chat_id = ?", (chat_id,))
            conn.commit()
            
            # এডমিনকে শুধু একবার নোটিফিকেশন দেওয়ার জন্য আমরা লক স্ট্যাটাস আপডেট করতে পারি, 
            # তবে আপাতত এটি ব্যাকগ্রাউন্ডে চ্যানেলটি লক রাখবে।

    # ২. ইউজার সাবস্ক্রিপশন চেক
    cursor.execute("SELECT user_id, expire_date FROM users")
    users = cursor.fetchall()
    for u in users:
        user_id = u[0]
        expire_date = datetime.strptime(u[1], '%Y-%m-%d %H:%M:%S.%f')
        if now >= expire_date:
            cursor.execute("SELECT chat_id FROM user_channels WHERE user_id = ?", (user_id,))
            for chat in cursor.fetchall():
                try: bot.ban_chat_member(chat[0], user_id)
                except: pass
            cursor.execute("DELETE FROM user_channels WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            try: bot.send_message(user_id, "⚠️ মেয়াদ শেষ হওয়ায় আপনাকে চ্যানেল থেকে রিমুভ করা হয়েছে।")
            except: pass
            bot.send_message(ADMIN_ID, f"🔔 ইউজার <code>{user_id}</code> এর মেয়াদ শেষ হওয়ায় রিমুভ করা হয়েছে।", parse_mode='HTML')

# ================= 🔄 অটোমেটিক ব্যাকআপ সিস্টেম =================
def auto_backup():
    try:
        with open(DB_FILE, 'rb') as doc:
            bot.send_document(ADMIN_ID, doc, caption=f"🔄 অটো ডেইলি ব্যাকআপ\nসময়: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    except: pass

# শিডিউলার (প্রতি ১ মিনিটে চেক এবং প্রতি ২৪ ঘণ্টায় ব্যাকআপ)
scheduler = BackgroundScheduler()
scheduler.add_job(check_timers, 'interval', minutes=1)
scheduler.add_job(auto_backup, 'interval', hours=24)
scheduler.start()

# ================= 🚀 বট চালু =================
print("✅ প্রো-সাবস্ক্রিপশন বট সফলভাবে চালু হয়েছে...!")
bot.infinity_polling()
