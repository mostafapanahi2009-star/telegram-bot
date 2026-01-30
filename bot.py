#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import random
import sqlite3
import json
import re
import time
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode

# ==================== تنظیمات ====================
TOKEN = "8554258985:AAE8-8MDP_eYA6Btj2nEPPnpM-6V7B_M75A"
ADMIN_ID = 8223560115
DATABASE_NAME = "bot_database.db"
CONFIG_FILE = "bot_config.json"

# تنظیم لاگ انگلیسی
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== کلاس تنظیمات ====================
class BotConfig:
    def __init__(self):
        self.config = self.load_config()
    
    def load_config(self):
        default_config = {
            "language": "fa",
            "bot_mode": "rude",
            "welcome_message": "👋 به گروه خوش آمدید {name}!",
            "goodbye_message": "👋 {name} گروه رو ترک کرد!",
            "mute_message": "⚠️ شما تا {time} در سکوت هستید.",
            "unmute_message": "✅ سکوت شما برداشته شد.",
            "admin_promoted": "👑 {name} به ادمین ارتقا یافت!",
            "admin_demoted": "📉 ادمینی {name} به پایان رسید.",
            "spam_warning": "⚠️ اخطار اسپم!",
            "learn_enabled": True,
            "auto_response": True,
            "contest_enabled": True,
            "contest_prize_days": 3,
            "max_warnings": 3,
            "mute_duration": 60
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
        
        self.config = default_config
        self.save_config()
        return default_config
    
    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        self.save_config()
        return True

# ==================== دیتابیس ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                language TEXT DEFAULT 'fa',
                bio TEXT,
                country TEXT,
                message_count INTEGER DEFAULT 0,
                total_time INTEGER DEFAULT 0,
                join_date TEXT,
                last_seen TEXT,
                tokens INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                admin_until TEXT,
                is_muted INTEGER DEFAULT 0,
                mute_until TEXT,
                warnings INTEGER DEFAULT 0
            )
        ''')
        
        # جدول پیام‌های گروه
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                text TEXT,
                date TEXT
            )
        ''')
        
        # جدول پاسخ‌های یادگرفته
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT,
                response TEXT,
                added_by INTEGER,
                added_date TEXT
            )
        ''')
        
        # جدول مسابقات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT,
                end_date TEXT,
                winner_id INTEGER,
                prize TEXT
            )
        ''')
        
        # جدول تنظیمات گروه
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_enabled INTEGER DEFAULT 1,
                goodbye_enabled INTEGER DEFAULT 1,
                antispam_enabled INTEGER DEFAULT 1,
                learning_enabled INTEGER DEFAULT 1
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, last_name=""):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, join_date, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, 
                  datetime.now().isoformat(), datetime.now().isoformat()))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def update_user(self, user_id, **kwargs):
        cursor = self.conn.cursor()
        try:
            for key, value in kwargs.items():
                cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False
    
    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
    
    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]
    
    def add_message(self, user_id, chat_id, text):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO messages (user_id, chat_id, text, date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, chat_id, text, datetime.now().isoformat()))
            
            cursor.execute('''
                UPDATE users SET message_count = message_count + 1, last_seen = ?
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), user_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            return False
    
    def get_top_users(self, chat_id=None, limit=10):
        cursor = self.conn.cursor()
        if chat_id:
            cursor.execute('''
                SELECT u.user_id, u.first_name, u.username, COUNT(m.id) as count
                FROM users u
                JOIN messages m ON u.user_id = m.user_id
                WHERE m.chat_id = ?
                GROUP BY u.user_id
                ORDER BY count DESC
                LIMIT ?
            ''', (chat_id, limit))
        else:
            cursor.execute('''
                SELECT user_id, first_name, username, message_count
                FROM users
                ORDER BY message_count DESC
                LIMIT ?
            ''', (limit,))
        return cursor.fetchall()
    
    def add_response(self, word, response, added_by):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO responses (word, response, added_by, added_date)
                VALUES (?, ?, ?, ?)
            ''', (word.lower(), response, added_by, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding response: {e}")
            return False
    
    def get_responses(self, word):
        cursor = self.conn.cursor()
        cursor.execute('SELECT response FROM responses WHERE word = ?', (word.lower(),))
        return [row[0] for row in cursor.fetchall()]
    
    def delete_response(self, word, response):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM responses WHERE word = ? AND response = ?', 
                      (word.lower(), response))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_all_responses(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT word FROM responses')
        return [row[0] for row in cursor.fetchall()]
    
    def mute_user(self, user_id, minutes):
        cursor = self.conn.cursor()
        mute_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        cursor.execute('''
            UPDATE users 
            SET is_muted = 1, mute_until = ?, warnings = warnings + 1
            WHERE user_id = ?
        ''', (mute_until, user_id))
        self.conn.commit()
        return mute_until
    
    def unmute_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET is_muted = 0, mute_until = NULL
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    def check_expired_mutes(self):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('SELECT user_id FROM users WHERE is_muted = 1 AND mute_until < ?', (now,))
        users = [row[0] for row in cursor.fetchall()]
        for user_id in users:
            self.unmute_user(user_id)
        return users
    
    def add_admin(self, user_id, days):
        cursor = self.conn.cursor()
        admin_until = (datetime.now() + timedelta(days=days)).isoformat()
        cursor.execute('''
            UPDATE users 
            SET is_admin = 1, admin_until = ?
            WHERE user_id = ?
        ''', (admin_until, user_id))
        self.conn.commit()
        return admin_until
    
    def check_expired_admins(self):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('SELECT user_id FROM users WHERE is_admin = 1 AND admin_until < ?', (now,))
        users = [row[0] for row in cursor.fetchall()]
        for user_id in users:
            cursor.execute('UPDATE users SET is_admin = 0, admin_until = NULL WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return users
    
    def add_token(self, user_id, count=1):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET tokens = tokens + ? WHERE user_id = ?', (count, user_id))
        self.conn.commit()
    
    def get_user_count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]
    
    def get_message_count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM messages')
        return cursor.fetchone()[0]

# ==================== مدیریت ربات ====================
class BotManager:
    def __init__(self):
        self.db = Database()
        self.config = BotConfig()
        self.user_languages = {}
        self.active_chats = set()
        self.start_time = datetime.now()
        
        # شروع چکرهای دوره‌ای
        self.start_checkers()
    
    def start_checkers(self):
        def check_mutes():
            while True:
                try:
                    expired = self.db.check_expired_mutes()
                    if expired:
                        logger.info(f"Auto-unmuted users: {expired}")
                except Exception as e:
                    logger.error(f"Error checking mutes: {e}")
                time.sleep(60)
        
        def check_admins():
            while True:
                try:
                    expired = self.db.check_expired_admins()
                    if expired:
                        logger.info(f"Auto-demoted admins: {expired}")
                except Exception as e:
                    logger.error(f"Error checking admins: {e}")
                time.sleep(3600)  # هر ساعت
        
        threading.Thread(target=check_mutes, daemon=True).start()
        threading.Thread(target=check_admins, daemon=True).start()
    
    def format_user_info(self, user_data, lang="fa"):
        if not user_data:
            return "کاربر یافت نشد"
        
        user_id = user_data[0]
        username = user_data[1] or "ندارد"
        first_name = user_data[2] or "بدون نام"
        last_name = user_data[3] or ""
        message_count = user_data[8]
        tokens = user_data[12]
        is_admin = user_data[13]
        is_muted = user_data[15]
        warnings = user_data[17]
        
        if lang == "en":
            info = f"""
👤 User: {first_name} {last_name}
🆔 ID: {user_id}
📝 Username: @{username}
📊 Messages: {message_count}
🎫 Tokens: {tokens}
👑 Admin: {'Yes' if is_admin else 'No'}
🤫 Muted: {'Yes' if is_muted else 'No'}
⚠️ Warnings: {warnings}
📅 Joined: {user_data[10][:10]}
            """
        else:
            info = f"""
👤 کاربر: {first_name} {last_name}
🆔 آی‌دی: {user_id}
📝 نام کاربری: @{username}
📊 پیام‌ها: {message_count}
🎫 توکن: {tokens}
👑 ادمین: {'✅' if is_admin else '❌'}
🤫 سکوت: {'✅' if is_muted else '❌'}
⚠️ اخطارها: {warnings}
📅 عضویت: {user_data[10][:10]}
            """
        
        return info
    
    def get_response(self, word):
        responses = self.db.get_responses(word)
        if responses:
            return random.choice(responses)
        return None
    
    def learn_word(self, word, response, teacher_id):
        return self.db.add_response(word, response, teacher_id)
    
    def process_message(self, user_id, chat_id, text):
        # ذخیره پیام
        self.db.add_message(user_id, chat_id, text)
        
        # چک کردن اسپم
        if self.config.get("antispam_enabled"):
            # منطق ساده تشخیص اسپم
            if len(text) > 500:  # پیام خیلی طولانی
                return {"action": "warn", "reason": "long_message"}
        
        return {"action": "ok"}

# ==================== ایجاد نمونه ربات ====================
bot = BotManager()

# ==================== Handlers ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat
        
        logger.info(f"Start from {user.id} in chat {chat.id}")
        
        # ذخیره کاربر
        bot.db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        # اگر چت خصوصی
        if chat.type == "private":
            keyboard = [
                [InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa")],
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🌍 لطفا زبان خود را انتخاب کنید / Please choose your language:",
                reply_markup=reply_markup
            )
        else:
            # در گروه
            lang = bot.user_languages.get(user.id, "fa")
            if user.id == ADMIN_ID:
                await update.message.reply_text(
                    "👑 سلام ادمین عزیز! ربات فعال است.\n"
                    "برای مدیریت از /admin استفاده کنید."
                )
            else:
                await update.message.reply_text(
                    "🤖 سلام! من ربات مدیریت گروه هستم.\n"
                    "دستورات: /help"
                )
    
    except Exception as e:
        logger.error(f"Error in start: {e}")

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "lang_fa":
        bot.user_languages[user_id] = "fa"
        await query.edit_message_text(
            "✅ زبان فارسی انتخاب شد!\n\n"
            "🤖 به ربات مدیریت گروه خوش آمدید!\n\n"
            "📋 دستورات:\n"
            "/help - راهنما\n"
            "/info - اطلاعات کاربر\n"
            "/learn - آموزش کلمه\n"
            "/stats - آمار\n"
            "/admin - پنل مدیریت (فقط ادمین)"
        )
    elif data == "lang_en":
        bot.user_languages[user_id] = "en"
        await query.edit_message_text(
            "✅ English language selected!\n\n"
            "🤖 Welcome to Group Manager Bot!\n\n"
            "📋 Commands:\n"
            "/help - Help\n"
            "/info - User info\n"
            "/learn - Learn word\n"
            "/stats - Statistics\n"
            "/admin - Admin panel (admin only)"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = bot.user_languages.get(user_id, "fa")
    
    if lang == "en":
        help_text = """
🤖 **Group Manager Bot - Commands**

👤 **User Commands:**
/start - Start bot
/help - Show this help
/info - Your info
/stats - Group statistics
/mytokens - Your tokens
/learn - Teach me a word
/responses - Show learned words
/contest - Weekly contest

👑 **Admin Commands:**
/admin - Admin panel
/mute - Mute user (reply)
/unmute - Unmute user (reply)
/promote - Make admin (reply)
/demote - Remove admin (reply)
/broadcast - Send to all
/settings - Bot settings
/clean - Clean messages

⚠️ **Group Management:**
Reply to message with:
!mute 60 - Mute for 60min
!unmute - Remove mute
!warn - Give warning
!kick - Kick user
!ban - Ban user
"""
    else:
        help_text = """
🤖 **ربات مدیریت گروه - دستورات**

👤 **دستورات کاربران:**
/start - شروع ربات
/help - راهنما
/info - اطلاعات شما
/stats - آمار گروه
/mytokens - توکن‌های شما
/learn - آموزش کلمه
/responses - کلمات یادگرفته
/contest - مسابقه هفتگی

👑 **دستورات ادمین:**
/admin - پنل مدیریت
/mute - سکوت کاربر (ریپلای)
/unmute - برداشتن سکوت (ریپلای)
/promote - ادمین کردن (ریپلای)
/demote - حذف ادمین (ریپلای)
/broadcast - ارسال به همه
/settings - تنظیمات ربات
/clean - پاک کردن پیام‌ها

⚠️ **مدیریت گروه:**
روی پیام ریپلای کنید با:
!mute 60 - سکوت ۶۰ دقیقه
!unmute - برداشتن سکوت
!warn - اخطار دادن
!kick - اخراج کاربر
!ban - بن کردن
"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_data = bot.db.get_user(user.id)
        lang = bot.user_languages.get(user.id, "fa")
        
        info_text = bot.format_user_info(user_data, lang)
        await update.message.reply_text(info_text)
        
    except Exception as e:
        logger.error(f"Error in info: {e}")
        await update.message.reply_text("خطا در دریافت اطلاعات")

async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        lang = bot.user_languages.get(user.id, "fa")
        
        if not context.args:
            if lang == "en":
                await update.message.reply_text(
                    "📚 **Learn a new word:**\n"
                    "Format: /learn word = response\n\n"
                    "**Examples:**\n"
                    "/learn hello = hi there!\n"
                    "/learn سلام = علیک\n"
                    "/learn چطوری = خوبم تو چطور؟\n\n"
                    "You can add multiple responses to same word!"
                )
            else:
                await update.message.reply_text(
                    "📚 **آموزش کلمه جدید:**\n"
                    "فرمت: /learn کلمه = پاسخ\n\n"
                    "**مثال‌ها:**\n"
                    "/learn hello = hi there!\n"
                    "/learn سلام = علیک\n"
                    "/learn چطوری = خوبم تو چطور؟\n\n"
                    "می‌توانید چند پاسخ برای یک کلمه اضافه کنید!"
                )
            return
        
        text = " ".join(context.args)
        if "=" not in text:
            if lang == "en":
                await update.message.reply_text("❌ Use = to separate word and response!")
            else:
                await update.message.reply_text("❌ از = برای جدا کردن کلمه و پاسخ استفاده کنید!")
            return
        
        word, response = text.split("=", 1)
        word = word.strip()
        response = response.strip()
        
        if not word or not response:
            if lang == "en":
                await update.message.reply_text("❌ Word and response cannot be empty!")
            else:
                await update.message.reply_text("❌ کلمه و پاسخ نمی‌توانند خالی باشند!")
            return
        
        if bot.learn_word(word, response, user.id):
            if lang == "en":
                await update.message.reply_text(f"✅ Learned: **{word}** → **{response}**")
            else:
                await update.message.reply_text(f"✅ یادگرفتم: **{word}** → **{response}**")
        else:
            if lang == "en":
                await update.message.reply_text("❌ Error saving response!")
            else:
                await update.message.reply_text("❌ خطا در ذخیره پاسخ!")
    
    except Exception as e:
        logger.error(f"Error in learn: {e}")
        await update.message.reply_text("❌ خطا در پردازش دستور")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.effective_chat
        user = update.effective_user
        lang = bot.user_languages.get(user.id, "fa")
        
        total_users = bot.db.get_user_count()
        total_messages = bot.db.get_message_count()
        top_users = bot.db.get_top_users(chat.id if chat.id < 0 else None, 5)
        
        if lang == "en":
            stats_text = f"""
📊 **Bot Statistics:**
👥 Total Users: {total_users}
📨 Total Messages: {total_messages}
⏰ Uptime: {(datetime.now() - bot.start_time).days} days

🏆 **Top Users:**
"""
            for i, (uid, name, username, count) in enumerate(top_users, 1):
                stats_text += f"{i}. {name} (@{username or 'no'}) - {count} msgs\n"
        
        else:
            stats_text = f"""
📊 **آمار ربات:**
👥 کاربران کل: {total_users}
📨 پیام‌های کل: {total_messages}
⏰ مدت فعالیت: {(datetime.now() - bot.start_time).days} روز

🏆 **کاربران برتر:**
"""
            for i, (uid, name, username, count) in enumerate(top_users, 1):
                stats_text += f"{i}. {name} (@{username or 'ندارد'}) - {count} پیام\n"
        
        await update.message.reply_text(stats_text)
    
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await update.message.reply_text("❌ خطا در دریافت آمار")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ فقط ادمین اصلی دسترسی دارد!")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("⚙ تنظیمات ربات", callback_data="admin_settings")],
            [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🗣 مدیریت پاسخ‌ها", callback_data="admin_responses")],
            [InlineKeyboardButton("🎯 مسابقات", callback_data="admin_contests")],
            [InlineKeyboardButton("🔧 پیام‌های خودکار", callback_data="admin_messages")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👑 **پنل مدیریت ادمین اصلی**\n\n"
            "لطفا بخش مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
    
    except Exception as e:
        logger.error(f"Error in admin panel: {e}")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("❌ دسترسی ممنوع!")
        return
    
    data = query.data
    
    if data == "admin_stats":
        total_users = bot.db.get_user_count()
        total_messages = bot.db.get_message_count()
        learned_words = len(bot.db.get_all_responses())
        
        stats_text = f"""
📊 **آمار کامل ربات:**
👥 کاربران: {total_users}
📨 پیام‌ها: {total_messages}
🗣 کلمات یادگرفته: {learned_words}
⏰ مدت فعالیت: {(datetime.now() - bot.start_time).days} روز
🎯 حالت فعلی: {bot.config.get('bot_mode')}
🌐 زبان پیشفرض: {bot.config.get('language')}
        """
        
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    elif data == "admin_broadcast":
        await query.edit_message_text(
            "📢 **ارسال پیام همگانی:**\n\n"
            "پیام خود را به صورت زیر ارسال کنید:\n"
            "/broadcast متن پیام\n\n"
            "یا برای ارسال با دکمه:\n"
            "/broadcastbutton متن پیام | متن دکمه | لینک"
        )
    
    elif data == "admin_responses":
        responses = bot.db.get_all_responses()
        
        if not responses:
            text = "هنوز کلمه‌ای یادگرفته نشده است."
        else:
            text = "📚 **کلمات یادگرفته شده:**\n\n"
            for i, word in enumerate(responses[:20], 1):
                resps = bot.db.get_responses(word)
                text += f"{i}. **{word}** → {len(resps)} پاسخ\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ اضافه کردن", callback_data="add_response")],
            [InlineKeyboardButton("🗑 حذف کردن", callback_data="delete_response")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_messages":
        keyboard = [
            [InlineKeyboardButton("✍️ ویرایش پیام خوش‌آمد", callback_data="edit_welcome")],
            [InlineKeyboardButton("👋 ویرایش پیام خداحافظ", callback_data="edit_goodbye")],
            [InlineKeyboardButton("🤫 ویرایش پیام سکوت", callback_data="edit_mute")],
            [InlineKeyboardButton("✅ ویرایش پیام رفع سکوت", callback_data="edit_unmute")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        current_msgs = f"""
✍️ **پیام‌های فعلی:**

👋 خوش‌آمد: {bot.config.get('welcome_message')}
👋 خداحافظ: {bot.config.get('goodbye_message')}
🤫 سکوت: {bot.config.get('mute_message')}
✅ رفع سکوت: {bot.config.get('unmute_message')}
👑 ترفیع: {bot.config.get('admin_promoted')}
📉 عزل: {bot.config.get('admin_demoted')}

برای ویرایش هر کدام کلیک کنید.
متغیرهای قابل استفاده:
{{name}} - نام کاربر
{{time}} - زمان
{{group}} - نام گروه
        """
        
        await query.edit_message_text(current_msgs, reply_markup=reply_markup)
    
    elif data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("⚙ تنظیمات ربات", callback_data="admin_settings")],
            [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🗣 مدیریت پاسخ‌ها", callback_data="admin_responses")],
            [InlineKeyboardButton("🎯 مسابقات", callback_data="admin_contests")],
            [InlineKeyboardButton("🔧 پیام‌های خودکار", callback_data="admin_messages")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👑 **پنل مدیریت ادمین اصلی**",
            reply_markup=reply_markup
        )
    
    elif data.startswith("edit_"):
        msg_type = data[5:]  # welcome, goodbye, etc
        msg_types = {
            "welcome": "پیام خوش‌آمد",
            "goodbye": "پیام خداحافظ",
            "mute": "پیام سکوت",
            "unmute": "پیام رفع سکوت"
        }
        
        await query.edit_message_text(
            f"✍️ **ویرایش {msg_types.get(msg_type, msg_type)}:**\n\n"
            f"پیام فعلی: {bot.config.get(msg_type + '_message')}\n\n"
            f"پیام جدید را ارسال کنید:\n"
            f"/setmsg {msg_type} متن جدید\n\n"
            "متغیرهای قابل استفاده:\n"
            "{name} - نام کاربر\n"
            "{time} - زمان\n"
            "{group} - نام گروه"
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if user.id != ADMIN_ID:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📢 فرمت:\n"
                "/broadcast متن پیام\n\n"
                "یا برای دکمه:\n"
                "/broadcast متن | متن دکمه | لینک"
            )
            return
        
        text = " ".join(context.args)
        
        # چک کردن حالت دکمه
        if "|" in text:
            parts = text.split("|")
            if len(parts) >= 3:
                message_text = parts[0].strip()
                button_text = parts[1].strip()
                button_url = parts[2].strip()
                
                keyboard = [[InlineKeyboardButton(button_text, url=button_url)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                message_text = text
                reply_markup = None
        else:
            message_text = text
            reply_markup = None
        
        # دریافت تمام کاربران
        user_ids = bot.db.get_all_users()
        
        success = 0
        failed = 0
        
        await update.message.reply_text(f"⏳ ارسال پیام به {len(user_ids)} کاربر...")
        
        for uid in user_ids:
            try:
                if reply_markup:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=message_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                success += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to {uid}: {e}")
            
            # تاخیر کوچک برای جلوگیری از محدودیت
            await asyncio.sleep(0.1)
        
        await update.message.reply_text(
            f"✅ ارسال پیام همگانی تکمیل شد!\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {failed}"
        )
    
    except Exception as e:
        logger.error(f"Error in broadcast: {e}")
        await update.message.reply_text("❌ خطا در ارسال پیام همگانی")

async def set_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if user.id != ADMIN_ID:
            return
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "✍️ فرمت:\n"
                "/setmsg نوع متن\n\n"
                "انواع:\n"
                "welcome - پیام خوش‌آمد\n"
                "goodbye - پیام خداحافظ\n"
                "mute - پیام سکوت\n"
                "unmute - پیام رفع سکوت\n"
                "promoted - پیام ترفیع\n"
                "demoted - پیام عزل"
            )
            return
        
        msg_type = context.args[0]
        message_text = " ".join(context.args[1:])
        
        valid_types = {
            "welcome": "welcome_message",
            "goodbye": "goodbye_message",
            "mute": "mute_message",
            "unmute": "unmute_message",
            "promoted": "admin_promoted",
            "demoted": "admin_demoted"
        }
        
        if msg_type not in valid_types:
            await update.message.reply_text("❌ نوع پیام نامعتبر است!")
            return
        
        config_key = valid_types[msg_type]
        bot.config.set(config_key, message_text)
        
        await update.message.reply_text(f"✅ پیام {msg_type} با موفقیت به روز شد!")
    
    except Exception as e:
        logger.error(f"Error in setmsg: {e}")
        await update.message.reply_text("❌ خطا در ذخیره پیام")

async def responses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        responses = bot.db.get_all_responses()
        
        if not responses:
            await update.message.reply_text("📭 هنوز کلمه‌ای یادگرفته نشده است!")
            return
        
        text = "📚 **کلمات یادگرفته شده:**\n\n"
        for i, word in enumerate(responses[:15], 1):
            resps = bot.db.get_responses(word)
            sample = resps[0][:30] + "..." if len(resps[0]) > 30 else resps[0]
            text += f"{i}. **{word}** → {sample} ({len(resps)} پاسخ)\n"
        
        if len(responses) > 15:
            text += f"\n... و {len(responses) - 15} کلمه دیگر"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        logger.error(f"Error in responses: {e}")

async def mytokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_data = bot.db.get_user(user.id)
        
        if user_data:
            tokens = user_data[12]
            lang = bot.user_languages.get(user.id, "fa")
            
            if lang == "en":
                text = f"🎫 **Your Tokens:** {tokens}\n\n"
                text += "Each token = 1 day of admin\n"
                text += "Use /contest to win more tokens!"
            else:
                text = f"🎫 **توکن‌های شما:** {tokens}\n\n"
                text += "هر توکن = ۱ روز ادمینی\n"
                text += "برای کسب توکن بیشتر در /contest شرکت کنید!"
            
            await update.message.reply_text(text)
    
    except Exception as e:
        logger.error(f"Error in mytokens: {e}")

async def contest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.effective_chat
        user = update.effective_user
        lang = bot.user_languages.get(user.id, "fa")
        
        top_users = bot.db.get_top_users(chat.id if chat.id < 0 else None, 3)
        
        if lang == "en":
            text = "🏆 **Weekly Contest**\n\n"
            text += "**Current Top Users:**\n"
            
            for i, (uid, name, username, count) in enumerate(top_users, 1):
                text += f"{i}. {name} - {count} messages\n"
            
            text += "\n**Prize for winner:**\n"
            text += "🎫 1 Token (1 day admin)\n"
            text += "👑 Special badge\n\n"
            text += "Contest resets every Sunday!"
        
        else:
            text = "🏆 **مسابقه هفتگی**\n\n"
            text += "**کاربران برتر فعلی:**\n"
            
            for i, (uid, name, username, count) in enumerate(top_users, 1):
                text += f"{i}. {name} - {count} پیام\n"
            
            text += "\n**جایزه برنده:**\n"
            text += "🎫 ۱ توکن (۱ روز ادمینی)\n"
            text += "👑 نشان ویژه\n\n"
            text += "مسابقه هر یکشنبه ریست می‌شود!"
        
        await update.message.reply_text(text)
    
    except Exception as e:
        logger.error(f"Error in contest: {e}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type not in ["group", "supergroup"]:
            return
        
        # چک کردن ادمین بودن
        user_data = bot.db.get_user(user.id)
        if not user_data or not user_data[13]:
            await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند سکوت کنند!")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ لطفا روی پیام کاربر ریپلای کنید!")
            return
        
        target_user = update.message.reply_to_message.from_user
        minutes = int(context.args[0]) if context.args and context.args[0].isdigit() else 60
        
        # سکوت کاربر
        mute_until = bot.db.mute_user(target_user.id, minutes)
        
        # ارسال پیام
        mute_msg = bot.config.get('mute_message').format(
            name=target_user.first_name,
            time=datetime.fromisoformat(mute_until).strftime("%H:%M"),
            group=chat.title
        )
        
        await update.message.reply_text(f"✅ {mute_msg}")
        
        # اطلاع به کاربر
        try:
            await context.bot.send_message(
                chat_id=target_user.id,
                text=mute_msg
            )
        except:
            pass
    
    except Exception as e:
        logger.error(f"Error in mute: {e}")
        await update.message.reply_text("❌ خطا در سکوت کاربر")

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat
        
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ فقط ادمین اصلی می‌تواند ترفیع دهد!")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ لطفا روی پیام کاربر ریپلای کنید!")
            return
        
        target_user = update.message.reply_to_message.from_user
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 3
        
        # ترفیع کاربر
        admin_until = bot.db.add_admin(target_user.id, days)
        
        # ارسال پیام
        promote_msg = bot.config.get('admin_promoted').format(
            name=target_user.first_name,
            time=datetime.fromisoformat(admin_until).strftime("%Y-%m-%d"),
            group=chat.title
        )
        
        await update.message.reply_text(f"✅ {promote_msg}")
        
        # اطلاع به کاربر
        try:
            await context.bot.send_message(
                chat_id=target_user.id,
                text=f"👑 شما در گروه {chat.title} به ادمین ارتقا یافتید!\n"
                     f"مدت: {days} روز\n"
                     f"تا: {datetime.fromisoformat(admin_until).strftime('%Y-%m-%d %H:%M')}"
            )
        except:
            pass
    
    except Exception as e:
        logger.error(f"Error in promote: {e}")
        await update.message.reply_text("❌ خطا در ترفیع کاربر")

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        
        if not message.text:
            return
        
        # پردازش پیام
        result = bot.process_message(user.id, chat.id, message.text)
        
        # چک کردن اسپم
        if result.get("action") == "warn":
            await message.reply_text(bot.config.get("spam_warning"))
            return
        
        # پاسخ به کلمات یادگرفته
        if bot.config.get("auto_response"):
            response = bot.get_response(message.text)
            if response:
                # حالت بی‌ادبی
                if bot.config.get("bot_mode") == "rude":
                    rude_addons = [" 🖕", " 😒", " برو بابا!", " ول کن!"]
                    response += random.choice(rude_addons)
                
                await message.reply_text(response)
        
        # دستورات سریع با !
        if message.text.startswith("!"):
            await handle_quick_command(update, context)
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def handle_quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        
        if chat.type not in ["group", "supergroup"]:
            return
        
        if not message.reply_to_message:
            return
        
        # چک کردن ادمین بودن
        user_data = bot.db.get_user(user.id)
        if not user_data or not user_data[13]:
            return
        
        target_user = update.message.reply_to_message.from_user
        command = message.text.lower().split()[0]
        
        if command == "!mute":
            minutes = int(message.text.split()[1]) if len(message.text.split()) > 1 else 60
            mute_until = bot.db.mute_user(target_user.id, minutes)
            
            mute_msg = bot.config.get('mute_message').format(
                name=target_user.first_name,
                time=datetime.fromisoformat(mute_until).strftime("%H:%M"),
                group=chat.title
            )
            
            await message.reply_text(f"✅ {mute_msg}")
        
        elif command == "!unmute":
            bot.db.unmute_user(target_user.id)
            await message.reply_text(f"✅ سکوت {target_user.first_name} برداشته شد.")
        
        elif command == "!warn":
            warnings = bot.db.get_user(target_user.id)[17] + 1
            bot.db.update_user(target_user.id, warnings=warnings)
            
            await message.reply_text(
                f"⚠️ اخطار به {target_user.first_name}\n"
                f"تعداد اخطارها: {warnings}/3"
            )
            
            if warnings >= 3:
                bot.db.mute_user(target_user.id, 120)
                await message.reply_text(f"🚫 کاربر به دلیل ۳ اخطار برای ۲ ساعت سکوت شد.")
        
        elif command == "!kick":
            try:
                await chat.ban_member(target_user.id, until_date=datetime.now() + timedelta(seconds=30))
                await message.reply_text(f"👢 کاربر {target_user.first_name} اخراج شد.")
            except:
                await message.reply_text("❌ خطا در اخراج کاربر")
    
    except Exception as e:
        logger.error(f"Error in quick command: {e}")

async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.effective_chat
        new_members = update.message.new_chat_members
        
        for member in new_members:
            # ذخیره کاربر جدید
            bot.db.add_user(member.id, member.username, member.first_name, member.last_name)
            
            # ارسال پیام خوش‌آمد
            welcome_msg = bot.config.get('welcome_message').format(
                name=member.first_name,
                time=datetime.now().strftime("%H:%M"),
                group=chat.title
            )
            
            await update.message.reply_text(welcome_msg)
    
    except Exception as e:
        logger.error(f"Error welcoming new member: {e}")

async def left_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.effective_chat
        left_member = update.message.left_chat_member
        
        # ارسال پیام خداحافظ
        goodbye_msg = bot.config.get('goodbye_message').format(
            name=left_member.first_name,
            time=datetime.now().strftime("%H:%M"),
            group=chat.title
        )
        
        await update.message.reply_text(goodbye_msg)
    
    except Exception as e:
        logger.error(f"Error saying goodbye: {e}")

async def clean_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        if user.id != ADMIN_ID:
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ روی پیام ریپلای کنید!")
            return
        
        chat = update.effective_chat
        message_id = update.message.reply_to_message.message_id
        
        # حذف پیام‌ها
        deleted = 0
        for i in range(10):  # 10 پیام قبلی
            try:
                await context.bot.delete_message(chat.id, message_id - i)
                deleted += 1
            except:
                break
        
        await update.message.reply_text(f"✅ {deleted} پیام پاک شد.")
    
    except Exception as e:
        logger.error(f"Error in clean: {e}")

# ==================== تابع اصلی ====================
def main():
    """تابع اصلی اجرای ربات"""
    try:
        # ایجاد اپلیکیشن
        application = Application.builder().token(TOKEN).build()
        
        # اضافه کردن هندلرها
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("learn", learn_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("admin", admin_panel))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("setmsg", set_message_command))
        application.add_handler(CommandHandler("responses", responses_command))
        application.add_handler(CommandHandler("mytokens", mytokens_command))
        application.add_handler(CommandHandler("contest", contest_command))
        application.add_handler(CommandHandler("mute", mute_command))
        application.add_handler(CommandHandler("promote", promote_command))
        application.add_handler(CommandHandler("clean", clean_command))
        
        # هندلرهای ویژه
        application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
        application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(admin_callback, pattern="^edit_"))
        application.add_handler(CallbackQueryHandler(admin_callback, pattern="^add_"))
        application.add_handler(CallbackQueryHandler(admin_callback, pattern="^delete_"))
        
        # هندلرهای پیام
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_message))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
        application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member))
        
        # شروع ربات
        print("=" * 50)
        print("🤖 Group Manager Bot - Advanced Version")
        print(f"👑 Admin ID: {ADMIN_ID}")
        print(f"📅 Started: {bot.start_time}")
        print("=" * 50)
        print("✅ Bot is running...")
        print("📝 All logs are in English")
        print("⚠️ Press Ctrl+C to stop")
        print("=" * 50)
        
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")

if __name__ == '__main__':
    main()
