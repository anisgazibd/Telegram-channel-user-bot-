import telebot
import sqlite3
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# ================= কনফিগারেশন =================
BOT_TOKEN = 'এখানে_আপনার_বটের_টোকেন_দিন'
ADMIN_ID = 123456789  # এখানে আপনার নিজের টেলিগ্রাম আইডি দিন (বট কন্ট্রোল করার জন্য)
CHANNEL_ID = -1000000000000  # এখানে আপনার প্রাইভেট চ্যানেলের আইডি দিন (-100 দিয়ে শুরু হয়)

bot = telebot.TeleBot(BOT_TOKEN)

# ================= ডাটাবেস সেটআপ =================
conn = sqlite3.connect('subscription.db', check_same_thread=False)
cursor = conn.cursor()

# ইউজারদের টেবিল (সাবস্ক্রিপশন)
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, expire_date TIMESTAMP)''')
# চ্যানেলের গ্লোবাল টাইমার টেবিল
cursor.execute('''CREATE TABLE IF NOT EXISTS channel_settings
                  (id INTEGER PRIMARY KEY, global_expire_date TIMESTAMP)''')
conn.commit()

# ================= এডমিন কমান্ডস =================

# ১. চ্যানেলের গ্লোবাল টাইমার সেট করা (Global Kill-Switch)
@bot.message_handler(commands=['set_channel_timer'])
def set_global_timer(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        days = int(message.text.split()[1])
        expire_date = datetime.now() + timedelta(days=days)
        
        cursor.execute("INSERT OR REPLACE INTO channel_settings (id, global_expire_date) VALUES (1, ?)", (expire_date,))
        conn.commit()
        bot.reply_to(message, f"✅ পুরো চ্যানেলের টাইমার সেট করা হয়েছে! {days} দিন পর চ্যানেল লক হয়ে যাবে এবং সবাইকে ব্যান করা হবে।")
    except:
        bot.reply_to(message, "⚠️ ভুল কমান্ড! সঠিক নিয়ম: /set_channel_timer [দিন]\nউদাহরণ: /set_channel_timer 30")

# ২. ইউজারের সাবস্ক্রিপশন টাইম সেট করা
@bot.message_handler(commands=['add_user'])
def add_user_time(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        days = int(parts[2])
        
        expire_date = datetime.now() + timedelta(days=days)
        cursor.execute("INSERT OR REPLACE INTO users (user_id, expire_date) VALUES (?, ?)", (user_id, expire_date))
        conn.commit()
        
        bot.reply_to(message, f"✅ ইউজার {user_id} এর সাবস্ক্রিপশন {days} দিনের জন্য আপডেট করা হয়েছে।")
    except:
        bot.reply_to(message, "⚠️ ভুল কমান্ড! সঠিক নিয়ম: /add_user [User_ID] [দিন]\nউদাহরণ: /add_user 12345678 30")

# ================= জয়েন রিকোয়েস্ট হ্যান্ডেলার =================
@bot.chat_join_request_handler()
def handle_join_request(message: telebot.types.ChatJoinRequest):
    user_id = message.from_user.id
    
    # চেক করবে ইউজারের সাবস্ক্রিপশন আছে কিনা
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result:
        expire_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
        if datetime.now() < expire_date:
            bot.approve_chat_join_request(CHANNEL_ID, user_id)
            bot.send_message(user_id, "✅ চ্যানেলে আপনার জয়েন রিকোয়েস্ট এক্সেপ্ট করা হয়েছে!")
        else:
            bot.decline_chat_join_request(CHANNEL_ID, user_id)
            bot.send_message(user_id, "❌ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে। দয়া করে এডমিনের সাথে যোগাযোগ করুন।")
    else:
        bot.decline_chat_join_request(CHANNEL_ID, user_id)
        bot.send_message(user_id, "❌ আপনার কোনো সাবস্ক্রিপশন কেনা নেই। দয়া করে এডমিনের সাথে যোগাযোগ করুন।")

# ================= অটো-ব্যান সিস্টেম (টাইমার চেকার) =================
def check_timers():
    now = datetime.now()
    
    # ১. প্রথমে গ্লোবাল চ্যানেল টাইমার চেক করা
    cursor.execute("SELECT global_expire_date FROM channel_settings WHERE id = 1")
    global_result = cursor.fetchone()
    
    global_expired = False
    if global_result:
        global_expire_date = datetime.strptime(global_result[0], '%Y-%m-%d %H:%M:%S.%f')
        if now >= global_expire_date:
            global_expired = True
            
    # যদি গ্লোবাল টাইম শেষ হয়, সবাইকে ব্যান করবে
    if global_expired:
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()
        for u in all_users:
            user_id = u[0]
            try:
                bot.ban_chat_member(CHANNEL_ID, user_id)
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            except Exception as e:
                pass
        conn.commit()
        # গ্লোবাল টাইমার মুছে ফেলা যেন বারবার একই কাজ না করে
        cursor.execute("DELETE FROM channel_settings WHERE id = 1")
        conn.commit()
        bot.send_message(ADMIN_ID, "🚨 গ্লোবাল টাইমার শেষ! চ্যানেলের সকল মেম্বারকে ব্যান করে বের করে দেওয়া হয়েছে।")
        return # গ্লোবাল কাজ শেষ হলে আর ইন্ডিভিজুয়াল চেক করার দরকার নেই

    # ২. ইন্ডিভিজুয়াল ইউজারের সাবস্ক্রিপশন চেক করা
    cursor.execute("SELECT user_id, expire_date FROM users")
    users = cursor.fetchall()
    
    for u in users:
        user_id = u[0]
        expire_date = datetime.strptime(u[1], '%Y-%m-%d %H:%M:%S.%f')
        
        if now >= expire_date:
            try:
                bot.ban_chat_member(CHANNEL_ID, user_id)
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                conn.commit()
                bot.send_message(user_id, "⚠️ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হওয়ায় আপনাকে চ্যানেল থেকে রিমুভ করা হয়েছে।")
                bot.send_message(ADMIN_ID, f"🔔 ইউজার {user_id} এর মেয়াদ শেষ হওয়ায় রিমুভ করা হয়েছে।")
            except:
                pass

# প্রতি ১ মিনিট পর পর চেকারটি রান করবে
scheduler = BackgroundScheduler()
scheduler.add_job(check_timers, 'interval', minutes=1)
scheduler.start()

# ================= বট চালু করা =================
print("বট সফলভাবে চালু হয়েছে...!")
bot.infinity_polling()
