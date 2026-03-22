"""
بوت LeoFame - بوت متكامل لزيادة المشاهدات والإعجابات
@V_ii5 | @Xiil6
"""
import requests
import time
import random
import urllib3
from user_agent import generate_user_agent
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from threading import Thread
from queue import Queue
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import hashlib

# إعداد الألوان للطباعة (للسيرفر)
Y = '\033[1;33m'
B = '\033[1;34m'
R = '\033[1;31m'
C = '\033[1;36m'
G = '\033[1;32m'
Fg = '\033[1;37m'
RESET = '\033[0m'
F = '\033[1;35m'      # 

BOT_TOKEN = "8125932385:AAE1nkYYXbQTmuY6079dixugL_dbXrrLfh4" 
ADMIN_IDS = [5635145118] 
BOT_USERNAME = "@Xiil6"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('leofame_bot.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
     
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP,
                last_use TIMESTAMP,
                total_requests INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        ''')
        
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_type TEXT,
                link TEXT,
                status TEXT,
                request_time TIMESTAMP,
                response TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
       
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_requests INTEGER DEFAULT 0,
                tiktok_views INTEGER DEFAULT 0,
                tiktok_likes INTEGER DEFAULT 0,
                instagram_views INTEGER DEFAULT 0,
                instagram_story_views INTEGER DEFAULT 0,
                instagram_shares INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, last_name):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, join_date, last_use, total_requests) 
            
        ''', (user_id, username, first_name, last_name, datetime.now(), datetime.now(), 0))
        self.conn.commit()
    
    def update_user_activity(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET last_use = ?, total_requests = total_requests + 1 
            WHERE user_id = ?
        ''', (datetime.now(), user_id))
        self.conn.commit()
    
    def add_request(self, user_id, service_type, link, status, response):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO requests (user_id, service_type, link, status, request_time, response) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, service_type, link, status, datetime.now(), response))
        self.conn.commit()
        return cursor.lastrowid
    
    def is_banned(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else False
    
    def ban_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def unban_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_user_stats(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT total_requests, join_date, last_use, is_banned 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        return cursor.fetchone()
    
    def get_daily_stats(self):
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO daily_stats (date) VALUES (?)
        ''', (today,))
        
        cursor.execute('''
            SELECT total_requests, tiktok_views, tiktok_likes, instagram_views, 
                   instagram_story_views, instagram_shares, unique_users 
            FROM daily_stats WHERE date = ?
        ''', (today,))
        
        result = cursor.fetchone()
        if not result:
            return [0, 0, 0, 0, 0, 0, 0]
        return result
    
    def update_daily_stats(self, service_type):
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = self.conn.cursor()
        
        # تحديث العدد الإجمالي للطلبات
        cursor.execute('''
            UPDATE daily_stats SET total_requests = total_requests + 1 
            WHERE date = ?
        ''', (today,))
        
        # تحديث إحصائيات الخدمة المحددة
        cursor.execute(f'''
            UPDATE daily_stats SET {service_type} = {service_type} + 1 
            WHERE date = ?
        ''', (today,))
        
        self.conn.commit()
    
    def update_unique_users(self, date, count):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE daily_stats SET unique_users = ? WHERE date = ?
        ''', (count, date))
        self.conn.commit()

# إنشاء كائن قاعدة البيانات
db = Database()

# قائمة المهام (Queue) للمعالجة غير المتزامنة
request_queue = Queue()

# ==================== دوال الخدمات ====================

class ServiceHandler:
    @staticmethod
    def get_cookies_and_token(url):
        try:
            res = requests.get(url, timeout=10)
            cookies = res.cookies.get_dict()
            return cookies.get('ci_session'), cookies.get('token')
        except Exception as e:
            logger.error(f"Error getting cookies: {e}")
            return None, None
    
    @staticmethod
    def tiktok_views(link):
        try:
            url = 'https://leofame.com/ar/free-tiktok-views'
            ci_session, token = ServiceHandler.get_cookies_and_token(url)
            
            if not ci_session or not token:
                return {'success': False, 'message': 'فشل في الحصول على التوكن'}
            
            cookies = {
                'token': token,
                'ci_session': ci_session,
                'cfzs_google-analytics_v4': '%7B%22mHFS_pageviewCounter%22%3A%7B%22v%22%3A%223%22%7D%7D',
                'cfz_google-analytics_v4': '%7B%22mHFS_engagementDuration%22%3A%7B%22v%22%3A%227966%22%2C%22e%22%3A1802072752085%7D%2C%22mHFS_engagementStart%22%3A%7B%22v%22%3A1770536758122%2C%22e%22%3A1802072759406%7D%2C%22mHFS_counter%22%3A%7B%22v%22%3A%225%22%2C%22e%22%3A1802072744119%7D%2C%22mHFS_ga4sid%22%3A%7B%22v%22%3A%221784819756%22%2C%22e%22%3A1770538544119%7D%2C%22mHFS_session_counter%22%3A%7B%22v%22%3A%221%22%2C%22e%22%3A1802072744119%7D%2C%22mHFS_ga4%22%3A%7B%22v%22%3A%224bb82571-6c56-4c3d-a61d-b8af61619488%22%2C%22e%22%3A1802072744119%7D%2C%22mHFS_let%22%3A%7B%22v%22%3A%221770536744119%22%2C%22e%22%3A1802072744119%7D%7D',
            }

            headers = {
                'authority': 'leofame.com',
                'accept': '*/*',
                'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://leofame.com',
                'referer': url,
                'user-agent': str(generate_user_agent()),
            }

            params = {'api': '1'}
            data = {
                'token': token,
                'timezone_offset': 'Asia/Baghdad',
                'free_link': link,
            }

            response = requests.post(url, params=params, cookies=cookies, 
                                    headers=headers, data=data, verify=False, timeout=15)
            
            response_text = response.text
            
            if "success" in response_text.lower():
                return {'success': True, 'message': '✅ تم إرسال المشاهدات بنجاح!'}
            else:
                return {'success': False, 'message': '❌ فشل في إرسال المشاهدات'}
                
        except Exception as e:
            logger.error(f"TikTok Views Error: {e}")
            return {'success': False, 'message': f'⚠️ حدث خطأ: {str(e)}'}
    
    @staticmethod
    def tiktok_likes(link):
        try:
            url = 'https://leofame.com/ar/free-tiktok-likes'
            ci_session, token = ServiceHandler.get_cookies_and_token(url)
            
            if not ci_session or not token:
                return {'success': False, 'message': 'فشل في الحصول على التوكن'}
            
            cookies = {
                'ci_session': ci_session,
                'token': token,
                'cfzs_google-analytics_v4': '%7B%22mHFS_pageviewCounter%22%3A%7B%22v%22%3A%221%22%7D%7D',
                'cfz_google-analytics_v4': '%7B%22mHFS_engagementDuration%22%3A%7B%22v%22%3A%220%22%2C%22e%22%3A1802093677979%7D%2C%22mHFS_engagementStart%22%3A%7B%22v%22%3A1770557681027%2C%22e%22%3A1802093681585%7D%2C%22mHFS_counter%22%3A%7B%22v%22%3A%2219%22%2C%22e%22%3A1802093677979%7D%2C%22mHFS_session_counter%22%3A%7B%22v%22%3A%222%22%2C%22e%22%3A1802093677979%7D%2C%22mHFS_ga4%22%3A%7B%22v%22%3A%224bb82571-6c56-4c3d-a61d-b8af61619488%22%2C%22e%22%3A1802093677979%7D%2C%22mHFS_let%22%3A%7B%22v%22%3A%221770557677979%22%2C%22e%22%3A1802093677979%7D%2C%22mHFS_ga4sid%22%3A%7B%22v%22%3A%221943590438%22%2C%22e%22%3A1770559477979%7D%7D',
            }

            headers = {
                'authority': 'leofame.com',
                'accept': '*/*',
                'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://leofame.com',
                'referer': url,
                'user-agent': str(generate_user_agent())
            }

            params = {'api': '1'}
            data = {
                'token': token,
                'timezone_offset': 'Asia/Baghdad',
                'free_link': link,
            }

            response = requests.post(url, params=params, cookies=cookies, 
                                    headers=headers, data=data, verify=False, timeout=15)
            
            if "success" in response.text.lower():
                return {'success': True, 'message': '✅ تم إرسال الإعجابات بنجاح!'}
            else:
                return {'success': False, 'message': '❌ فشل في إرسال الإعجابات'}
                
        except Exception as e:
            logger.error(f"TikTok Likes Error: {e}")
            return {'success': False, 'message': f'⚠️ حدث خطأ: {str(e)}'}
    
    @staticmethod
    def instagram_views(link):
        try:
            url = 'https://leofame.com/ar/free-instagram-views'
            ci_session, token = ServiceHandler.get_cookies_and_token(url)
            
            if not ci_session or not token:
                return {'success': False, 'message': 'فشل في الحصول على التوكن'}
            
            cookies = {
                'ci_session': ci_session,
                'token': token,
                'cfzs_google-analytics_v4': '%7B%22mHFS_pageviewCounter%22%3A%7B%22v%22%3A%224%22%7D%7D',
                'cfz_google-analytics_v4': '%7B%22mHFS_engagementDuration%22%3A%7B%22v%22%3A%220%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_engagementStart%22%3A%7B%22v%22%3A%221770558355986%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_counter%22%3A%7B%22v%22%3A%2227%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_session_counter%22%3A%7B%22v%22%3A%222%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_ga4%22%3A%7B%22v%22%3A%224bb82571-6c56-4c3d-a61d-b8af61619488%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_let%22%3A%7B%22v%22%3A%221770558355986%22%2C%22e%22%3A1802094355986%7D%2C%22mHFS_ga4sid%22%3A%7B%22v%22%3A%221943590438%22%2C%22e%22%3A1770560155986%7D%7D',
            }

            headers = {
                'authority': 'leofame.com',
                'accept': '*/*',
                'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://leofame.com',
                'referer': url,
                'user-agent': str(generate_user_agent())
            }

            params = {'api': '1'}
            data = {
                'token': token,
                'timezone_offset': 'Asia/Baghdad',
                'free_link': link,
                'quantity': '200',
                'speed': '5',
            }

            response = requests.post(url, params=params, cookies=cookies, 
                                    headers=headers, data=data, verify=False, timeout=15)
            
            if "success" in response.text.lower():
                return {'success': True, 'message': '✅ تم إرسال المشاهدات بنجاح!'}
            else:
                return {'success': False, 'message': '❌ فشل في إرسال المشاهدات'}
                
        except Exception as e:
            logger.error(f"Instagram Views Error: {e}")
            return {'success': False, 'message': f'⚠️ حدث خطأ: {str(e)}'}
    
    @staticmethod
    def instagram_story_views(link):
        try:
            url = 'https://leofame.com/ar/free-instagram-story-views'
            ci_session, token = ServiceHandler.get_cookies_and_token(url)
            
            if not ci_session or not token:
                return {'success': False, 'message': 'فشل في الحصول على التوكن'}
            
            cookies = {
                'ci_session': ci_session,
                'token': token,
                'cfzs_google-analytics_v4': '%7B%22mHFS_pageviewCounter%22%3A%7B%22v%22%3A%2214%22%7D%7D',
                'cfz_google-analytics_v4': '%7B%22mHFS_engagementDuration%22%3A%7B%22v%22%3A%228199%22%2C%22e%22%3A1802095940729%7D%2C%22mHFS_engagementStart%22%3A%7B%22v%22%3A1770559942844%2C%22e%22%3A1802095943429%7D%2C%22mHFS_counter%22%3A%7B%22v%22%3A%2250%22%2C%22e%22%3A1802095932530%7D%2C%22mHFS_session_counter%22%3A%7B%22v%22%3A%222%22%2C%22e%22%3A1802095932530%7D%2C%22mHFS_ga4%22%3A%7B%22v%22%3A%224bb82571-6c56-4c3d-a61d-b8af61619488%22%2C%22e%22%3A1802095932530%7D%2C%22mHFS_let%22%3A%7B%22v%22%3A%221770559932530%22%2C%22e%22%3A1802095932530%7D%2C%22mHFS_ga4sid%22%3A%7B%22v%22%3A%221943590438%22%2C%22e%22%3A1770561732530%7D%7D',
            }

            headers = {
                'authority': 'leofame.com',
                'accept': '*/*',
                'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://leofame.com',
                'referer': url,
                'user-agent': str(generate_user_agent()),
            }

            params = {'api': '1'}
            data = {
                'token': token,
                'timezone_offset': 'Asia/Baghdad',
                'free_link': link,
            }

            response = requests.post(url, params=params, cookies=cookies,
                                    headers=headers, data=data, verify=False, timeout=15)
            
            if "success" in response.text.lower():
                return {'success': True, 'message': '✅ تم إرسال مشاهدات الستوري بنجاح!'}
            else:
                return {'success': False, 'message': '❌ فشل في إرسال مشاهدات الستوري'}
                
        except Exception as e:
            logger.error(f"Instagram Story Views Error: {e}")
            return {'success': False, 'message': f'⚠️ حدث خطأ: {str(e)}'}
    
    @staticmethod
    def instagram_shares(link):
        try:
            url = 'https://leofame.com/ar/free-instagram-shares'
            ci_session, token = ServiceHandler.get_cookies_and_token(url)
            
            if not ci_session or not token:
                return {'success': False, 'message': 'فشل في الحصول على التوكن'}
            
            cookies = {
                'ci_session': ci_session,
                'token': token,
                'cfzs_google-analytics_v4': '%7B%22mHFS_pageviewCounter%22%3A%7B%22v%22%3A%223%22%7D%7D',
                'cfz_google-analytics_v4': '%7B%22mHFS_engagementDuration%22%3A%7B%22v%22%3A%220%22%2C%22e%22%3A1802096380917%7D%2C%22mHFS_engagementStart%22%3A%7B%22v%22%3A1770560384436%2C%22e%22%3A1802096384930%7D%2C%22mHFS_counter%22%3A%7B%22v%22%3A%2257%22%2C%22e%22%3A1802096380917%7D%2C%22mHFS_session_counter%22%3A%7B%22v%22%3A%222%22%2C%22e%22%3A1802096380917%7D%2C%22mHFS_ga4%22%3A%7B%22v%22%3A%224bb82571-6c56-4c3d-a61d-b8af61619488%22%2C%22e%22%3A1802096380917%7D%2C%22mHFS_let%22%3A%7B%22v%22%3A%221770560380917%22%2C%22e%22%3A1802096380917%7D%2C%22mHFS_ga4sid%22%3A%7B%22v%22%3A%221943590438%22%2C%22e%22%3A1770562180917%7D%7D',
            }

            headers = {
                'authority': 'leofame.com',
                'accept': '*/*',
                'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://leofame.com',
                'referer': url,
                'user-agent': str(generate_user_agent()),
            }

            params = {'api': '1'}
            data = {
                'token': token,
                'timezone_offset': 'Asia/Baghdad',
                'free_link': link,
                'quantity': '98',
                'speed': '5',
            }

            response = requests.post(url, params=params, cookies=cookies, 
                                    headers=headers, data=data, verify=False, timeout=15)
            
            if "success" in response.text.lower():
                return {'success': True, 'message': '✅ تم إرسال المشاركات بنجاح!'}
            else:
                return {'success': False, 'message': '❌ فشل في إرسال المشاركات'}
                
        except Exception as e:
            logger.error(f"Instagram Shares Error: {e}")
            return {'success': False, 'message': f'⚠️ حدث خطأ: {str(e)}'}

# ==================== معالج الطلبات غير المتزامن ====================

def request_worker():
    """معالج الطلبات في الخلفية"""
    while True:
        try:
            if not request_queue.empty():
                task = request_queue.get()
                user_id = task['user_id']
                service = task['service']
                link = task['link']
                message_id = task['message_id']
                
                # تنفيذ الخدمة
                if service == 'tiktok_views':
                    result = ServiceHandler.tiktok_views(link)
                    service_name = 'مشاهدات تيك توك'
                    service_type = 'tiktok_views'
                elif service == 'tiktok_likes':
                    result = ServiceHandler.tiktok_likes(link)
                    service_name = 'إعجابات تيك توك'
                    service_type = 'tiktok_likes'
                elif service == 'instagram_views':
                    result = ServiceHandler.instagram_views(link)
                    service_name = 'مشاهدات انستجرام'
                    service_type = 'instagram_views'
                elif service == 'instagram_story_views':
                    result = ServiceHandler.instagram_story_views(link)
                    service_name = 'مشاهدات ستوري انستجرام'
                    service_type = 'instagram_story_views'
                elif service == 'instagram_shares':
                    result = ServiceHandler.instagram_shares(link)
                    service_name = 'مشاركات انستجرام'
                    service_type = 'instagram_shares'
                
                # حفظ الطلب في قاعدة البيانات
                status = 'success' if result['success'] else 'failed'
                db.add_request(user_id, service_type, link, status, result['message'])
                db.update_daily_stats(service_type)
                
                # إرسال النتيجة للمستخدم
                if result['success']:
                    response_text = f"""✅ <b>تمت العملية بنجاح!</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>الخدمة:</b> {service_name}
┃ <b>الحالة:</b> ✅ ناجحة
┃ <b>الرابط:</b> <code>{link}</code>
┗━━━━━━━━━━━━━━━━━┛

{result['message']}

⚠️ <i>قد يستغرق ظهور النتائج بضع دقائق</i>"""
                else:
                    response_text = f"""❌ <b>فشلت العملية!</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>الخدمة:</b> {service_name}
┃ <b>الحالة:</b> ❌ فشل
┃ <b>الرابط:</b> <code>{link}</code>
┗━━━━━━━━━━━━━━━━━┛

{result['message']}

💡 <i>تأكد من صحة الرابط وحاول مرة أخرى</i>"""
                
                try:
                    bot.edit_message_text(
                        response_text,
                        user_id,
                        message_id,
                        reply_markup=main_menu_keyboard(),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                    bot.send_message(user_id, response_text, reply_markup=main_menu_keyboard(), parse_mode='HTML')
                
                request_queue.task_done()
            
            time.sleep(1)  # تجنب استهلاك المعالج بشكل كبير
            
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            time.sleep(5)

# بدء العامل في الخلفية
Thread(target=request_worker, daemon=True).start()

# ==================== دوال لوحة المفاتيح ====================

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = KeyboardButton("📱 تيك توك")
    btn2 = KeyboardButton("📷 انستجرام")
    btn3 = KeyboardButton("📊 إحصائياتي")
    btn4 = KeyboardButton("ℹ️ معلومات البوت")
    btn5 = KeyboardButton("📞 تواصل مع المطور")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

def tiktok_keyboard():
    """لوحة مفاتيح خدمات تيك توك"""
    markup = InlineKeyboardMarkup(row_width=2)
    btn1 = InlineKeyboardButton("👁 مشاهدات", callback_data="tiktok_views")
    btn2 = InlineKeyboardButton("❤️ إعجابات", callback_data="tiktok_likes")
    btn3 = InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    markup.add(btn1, btn2, btn3)
    return markup

def instagram_keyboard():
    """لوحة مفاتيح خدمات انستجرام"""
    markup = InlineKeyboardMarkup(row_width=2)
    btn1 = InlineKeyboardButton("👁 مشاهدات منشور", callback_data="instagram_views")
    btn2 = InlineKeyboardButton("📱 مشاهدات ستوري", callback_data="instagram_story_views")
    btn3 = InlineKeyboardButton("🔄 مشاركات", callback_data="instagram_shares")
    btn4 = InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    markup.add(btn1, btn2, btn3, btn4)
    return markup

def cancel_keyboard():
    """لوحة مفاتيح الإلغاء"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn = KeyboardButton("❌ إلغاء")
    markup.add(btn)
    return markup

# ==================== أوامر البوت ====================

@bot.message_handler(commands=['start'])
def start_command(message):
    """معالج أمر /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # إضافة المستخدم إلى قاعدة البيانات
    db.add_user(user_id, username, first_name, last_name)
    
    # التحقق من الحظر
    if db.is_banned(user_id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    welcome_text = f"""<b>🎉 أهلاً بك في بوت LeoFame!</b>

{first_name}، مرحباً بك في أفضل بوت لزيادة المشاهدات والإعجابات مجاناً!

<b>✨ الخدمات المتوفرة:</b>
• 👁 مشاهدات تيك توك
• ❤️ إعجابات تيك توك
• 👁 مشاهدات انستجرام
• 📱 مشاهدات ستوري انستجرام
• 🔄 مشاركات منشور انستجرام

<b>📌 كيفية الاستخدام:</b>
1️⃣ اختر الخدمة من القائمة
2️⃣ أرسل رابط الفيديو/المنشور
3️⃣ انتظر النتيجة (قد تستغرق بضع ثوان)

<b>✅ جميع الخدمات مجانية!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>👤 المبرمج:</b> @V_ii5 | @Xiil6
<b>📢 قناة المبرمج:</b> @V_ii5"""

    bot.send_message(user_id, welcome_text, reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.message_handler(commands=['help'])
def help_command(message):
    """معالج أمر /help"""
    help_text = """<b>📚 مساعدة البوت</b>

<b>الأوامر المتوفرة:</b>
• /start - بدء استخدام البوت
• /help - عرض المساعدة
• /stats - إحصائياتك الشخصية
• /info - معلومات البوت

<b>🔹 كيفية استخدام الخدمات:</b>
1. اختر الخدمة من القائمة
2. أرسل الرابط المطلوب
3. انتظر النتيجة

<b>⚠️ ملاحظات مهمة:</b>
• تأكد من صحة الرابط
• الحساب يجب أن يكون عاماً
• قد تستغرق النتائج بضع دقائق للظهور

<b>📞 للدعم الفني:</b>
@V_ii5 | @Xiil6

━━━━━━━━━━━━━━━━━━━━━━
<b>قناة المبرمج:</b> @V_ii5"""
    
    bot.reply_to(message, help_text, parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """معالج أمر /stats"""
    user_id = message.from_user.id
    
    # التحقق من الحظر
    if db.is_banned(user_id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    stats = db.get_user_stats(user_id)
    if stats:
        total_requests, join_date, last_use, is_banned = stats
        
        # حساب عدد الطلبات الناجحة
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM requests 
            WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        successful = cursor.fetchone()[0]
        
        join_date = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
        last_use = datetime.strptime(last_use, '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
        
        stats_text = f"""<b>📊 إحصائياتك الشخصية</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>معرفك:</b> <code>{user_id}</code>
┃ <b>تاريخ الاشتراك:</b> {join_date}
┃ <b>آخر استخدام:</b> {last_use}
┃ <b>إجمالي الطلبات:</b> {total_requests}
┃ <b>الطلبات الناجحة:</b> {successful}
┃ <b>حالة الحظر:</b> {'🚫 محظور' if is_banned else '✅ غير محظور'}
┗━━━━━━━━━━━━━━━━━┛

<i>استمر في استخدام البوت للحصول على المزيد!</i>"""
    else:
        stats_text = "❌ لا توجد إحصائيات متاحة حالياً."
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['info'])
def info_command(message):
    """معالج أمر /info"""
    # إحصائيات عامة
    cursor = db.conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests')
    total_requests = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests WHERE status = "success"')
    successful_requests = cursor.fetchone()[0]
    
    daily_stats = db.get_daily_stats()
    today_requests = daily_stats[0]
    
    info_text = f"""<b>ℹ️ معلومات البوت</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>اسم البوت:</b> LeoFame
┃ <b>الإصدار:</b> 2.0
┃ <b>المبرمج:</b> @V_ii5 | @Xiil6
┃ <b>القناة:</b> @V_ii5
┃ <b>اللغة:</b> العربية
┗━━━━━━━━━━━━━━━━━┛

<b>📈 إحصائيات عامة:</b>
• 👥 إجمالي المستخدمين: {total_users}
• 📊 إجمالي الطلبات: {total_requests}
• ✅ الطلبات الناجحة: {successful_requests}
• 📅 طلبات اليوم: {today_requests}

<b>✨ الخدمات المتوفرة:</b>
• 👁 مشاهدات تيك توك
• ❤️ إعجابات تيك توك
• 👁 مشاهدات انستجرام
• 📱 مشاهدات ستوري انستجرام
• 🔄 مشاركات انستجرام

<i>شكراً لاستخدامك البوت! ❤️</i>"""
    
    bot.reply_to(message, info_text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "📱 تيك توك")
def tiktok_menu(message):
    """قائمة خدمات تيك توك"""
    if db.is_banned(message.from_user.id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    text = """<b>📱 خدمات تيك توك</b>

اختر الخدمة التي تريدها:
• 👁 <b>مشاهدات</b> - زيادة مشاهدات الفيديو
• ❤️ <b>إعجابات</b> - زيادة إعجابات الفيديو

<i>ملاحظة: يجب أن يكون الحساب عاماً</i>"""
    
    bot.send_message(message.from_user.id, text, reply_markup=tiktok_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "📷 انستجرام")
def instagram_menu(message):
    """قائمة خدمات انستجرام"""
    if db.is_banned(message.from_user.id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    text = """<b>📷 خدمات انستجرام</b>

اختر الخدمة التي تريدها:
• 👁 <b>مشاهدات منشور</b> - زيادة مشاهدات الفيديو/الصورة
• 📱 <b>مشاهدات ستوري</b> - زيادة مشاهدات القصص
• 🔄 <b>مشاركات</b> - زيادة مشاركات المنشور

<i>ملاحظة: يجب أن يكون الحساب عاماً</i>"""
    
    bot.send_message(message.from_user.id, text, reply_markup=instagram_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "📊 إحصائياتي")
def my_stats(message):
    """عرض إحصائيات المستخدم"""
    stats_command(message)

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات البوت")
def bot_info(message):
    """عرض معلومات البوت"""
    info_command(message)

@bot.message_handler(func=lambda message: message.text == "📞 تواصل مع المطور")
def contact_dev(message):
    """التواصل مع المطور"""
    contact_text = """<b>📞 تواصل مع المطور</b>

للتواصل مع المطور أو للإبلاغ عن مشكلة:

┏━━━━━━━━━━━━━━━━━┓
┃ <b>المبرمج:</b> @V_ii5 | @Xiil6
┃ <b>قناة المبرمج:</b> @V_ii5
┃ <b>البوت:</b> @LeoFameBot
┗━━━━━━━━━━━━━━━━━┛

<i>يمكنك مراسلة المطور مباشرة للاستفسارات أو المشاكل</i>"""
    
    bot.send_message(message.from_user.id, contact_text, parse_mode='HTML')

@bot.message_handler(func=lambda message: message.text == "❌ إلغاء")
def cancel_action(message):
    """إلغاء العملية الحالية"""
    bot.send_message(
        message.from_user.id, 
        "✅ تم إلغاء العملية",
        reply_markup=main_menu_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """معالج الأزرار المضمنة"""
    user_id = call.from_user.id
    
    # التحقق من الحظر
    if db.is_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 أنت محظور من استخدام هذا البوت.", show_alert=True)
        return
    
    if call.data == "back_to_main":
        bot.edit_message_text(
            "🔹 اختر الخدمة التي تريدها من القائمة الرئيسية",
            user_id,
            call.message.message_id,
            reply_markup=None
        )
        bot.answer_callback_query(call.id)
        
    elif call.data in ["tiktok_views", "tiktok_likes", "instagram_views", "instagram_story_views", "instagram_shares"]:
        service_names = {
            "tiktok_views": "👁 مشاهدات تيك توك",
            "tiktok_likes": "❤️ إعجابات تيك توك",
            "instagram_views": "👁 مشاهدات انستجرام",
            "instagram_story_views": "📱 مشاهدات ستوري انستجرام",
            "instagram_shares": "🔄 مشاركات انستجرام"
        }
        
        service_name = service_names.get(call.data, call.data)
        
        bot.edit_message_text(
            f"""<b>{service_name}</b>

📤 <b>الرجاء إرسال الرابط الآن:</b>

<i>مثال:</i>
<code>https://www.tiktok.com/@username/video/123456789</code>

❌ للإلغاء أرسل /cancel أو اضغط على زر الإلغاء""",
            user_id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=None
        )
        
        # تسجيل الخدمة المطلوبة مؤقتاً
        bot.register_next_step_handler_by_chat_id(
            user_id, 
            process_link, 
            service=call.data,
            service_name=service_name
        )
        
        bot.answer_callback_query(call.id)

def process_link(message, service, service_name):
    """معالجة الرابط المرسل"""
    user_id = message.from_user.id
    link = message.text.strip()
    
    # التحقق من الحظر
    if db.is_banned(user_id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    # التحقق من الإلغاء
    if link.lower() == '/cancel' or link == '❌ إلغاء':
        bot.send_message(user_id, "✅ تم إلغاء العملية", reply_markup=main_menu_keyboard())
        return
    
    # التحقق من صحة الرابط
    if not link.startswith(('http://', 'https://')):
        bot.send_message(
            user_id,
            "❌ <b>رابط غير صالح!</b>\n\nالرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://",
            reply_markup=cancel_keyboard(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler_by_chat_id(user_id, process_link, service=service, service_name=service_name)
        return
    
    # تحديث نشاط المستخدم
    db.update_user_activity(user_id)
    
    # إرسال رسالة انتظار
    wait_msg = bot.send_message(
        user_id,
        f"""⏳ <b>جاري معالجة طلبك...</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>الخدمة:</b> {service_name}
┃ <b>الرابط:</b> <code>{link[:50]}...</code>
┗━━━━━━━━━━━━━━━━━┛

<i>قد تستغرق العملية بضع ثوان...</i>""",
        parse_mode='HTML'
    )
    
    # إضافة المهمة إلى قائمة الانتظار
    request_queue.put({
        'user_id': user_id,
        'service': service,
        'link': link,
        'message_id': wait_msg.message_id
    })

# ==================== أوامر المشرفين ====================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """لوحة تحكم المشرفين"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    # إحصائيات سريعة
    cursor = db.conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests WHERE date(request_time) = date("now")')
    today_requests = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = cursor.fetchone()[0]
    
    admin_text = f"""<b>🔧 لوحة تحكم المشرف</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>إجمالي المستخدمين:</b> {total_users}
┃ <b>طلبات اليوم:</b> {today_requests}
┃ <b>المستخدمين المحظورين:</b> {banned_users}
┗━━━━━━━━━━━━━━━━━┛

<b>📋 الأوامر المتوفرة:</b>
• /ban [user_id] - حظر مستخدم
• /unban [user_id] - إلغاء حظر مستخدم
• /broadcast [رسالة] - إرسال رسالة لجميع المستخدمين
• /stats_detailed - إحصائيات مفصلة
• /users_list - قائمة المستخدمين"""
    
    bot.reply_to(message, admin_text, parse_mode='HTML')

@bot.message_handler(commands=['ban'])
def ban_user(message):
    """حظر مستخدم"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    try:
        target_id = int(message.text.split()[1])
        db.ban_user(target_id)
        bot.reply_to(message, f"✅ تم حظر المستخدم {target_id} بنجاح.")
        
        # محاولة إشعار المستخدم
        try:
            bot.send_message(target_id, "🚫 لقد تم حظرك من استخدام البوت.")
        except:
            pass
            
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ الرجاء استخدام الأمر بشكل صحيح: /ban [user_id]")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    """إلغاء حظر مستخدم"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    try:
        target_id = int(message.text.split()[1])
        db.unban_user(target_id)
        bot.reply_to(message, f"✅ تم إلغاء حظر المستخدم {target_id} بنجاح.")
        
        # محاولة إشعار المستخدم
        try:
            bot.send_message(target_id, "✅ تم إلغاء حظرك، يمكنك استخدام البوت مرة أخرى.")
        except:
            pass
            
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ الرجاء استخدام الأمر بشكل صحيح: /unban [user_id]")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    """إرسال رسالة لجميع المستخدمين"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    try:
        broadcast_text = message.text.split(' ', 1)[1]
        
        # جلب جميع المستخدمين
        cursor = db.conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        
        success_count = 0
        fail_count = 0
        
        progress_msg = bot.reply_to(message, "⏳ جاري إرسال الرسائل...")
        
        for user in users:
            try:
                bot.send_message(user[0], f"<b>📢 إشعار هام</b>\n\n{broadcast_text}", parse_mode='HTML')
                success_count += 1
                time.sleep(0.05)  # تجنب الحظر
            except:
                fail_count += 1
        
        bot.edit_message_text(
            f"""✅ <b>تم إرسال الرسالة</b>

┏━━━━━━━━━━━━━━━━━┓
┃ <b>تم الإرسال لـ:</b> {success_count} مستخدم
┃ <b>فشل الإرسال لـ:</b> {fail_count} مستخدم
┃ <b>إجمالي المستلمين:</b> {success_count + fail_count}
┗━━━━━━━━━━━━━━━━━┛""",
            user_id,
            progress_msg.message_id,
            parse_mode='HTML'
        )
        
    except IndexError:
        bot.reply_to(message, "❌ الرجاء استخدام الأمر بشكل صحيح: /broadcast [الرسالة]")

@bot.message_handler(commands=['stats_detailed'])
def stats_detailed(message):
    """إحصائيات مفصلة للمشرفين"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    cursor = db.conn.cursor()
    
    # إحصائيات عامة
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests')
    total_requests = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests WHERE status = "success"')
    successful = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM requests WHERE status = "failed"')
    failed = cursor.fetchone()[0]
    
    # إحصائيات حسب الخدمة
    services = {
        'tiktok_views': 'مشاهدات تيك توك',
        'tiktok_likes': 'إعجابات تيك توك',
        'instagram_views': 'مشاهدات انستجرام',
        'instagram_story_views': 'مشاهدات ستوري',
        'instagram_shares': 'مشاركات انستجرام'
    }
    
    services_stats = ""
    for service_key, service_name in services.items():
        cursor.execute('SELECT COUNT(*) FROM requests WHERE service_type = ?', (service_key,))
        count = cursor.fetchone()[0]
        services_stats += f"┃ • {service_name}: {count}\n"
    
    # إحصائيات يومية
    today = datetime.now().strftime('%Y-%m-%d')
    daily = db.get_daily_stats()
    
    stats_text = f"""<b>📊 إحصائيات مفصلة</b>

<b>📈 إحصائيات عامة:</b>
┏━━━━━━━━━━━━━━━━━┓
┃ <b>إجمالي المستخدمين:</b> {total_users}
┃ <b>إجمالي الطلبات:</b> {total_requests}
┃ <b>الطلبات الناجحة:</b> {successful}
┃ <b>الطلبات الفاشلة:</b> {failed}
┃ <b>نسبة النجاح:</b> {(successful/total_requests*100) if total_requests > 0 else 0:.1f}%
┗━━━━━━━━━━━━━━━━━┛

<b>📊 إحصائيات الخدمات:</b>
┏━━━━━━━━━━━━━━━━━┓
{services_stats}┗━━━━━━━━━━━━━━━━━┛

<b>📅 إحصائيات اليوم ({today}):</b>
┏━━━━━━━━━━━━━━━━━┓
┃ <b>إجمالي الطلبات:</b> {daily[0]}
┃ <b>مشاهدات تيك توك:</b> {daily[1]}
┃ <b>إعجابات تيك توك:</b> {daily[2]}
┃ <b>مشاهدات انستجرام:</b> {daily[3]}
┃ <b>مشاهدات ستوري:</b> {daily[4]}
┃ <b>مشاركات انستجرام:</b> {daily[5]}
┃ <b>المستخدمين الفريدين:</b> {daily[6]}
┗━━━━━━━━━━━━━━━━━┛"""
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['users_list'])
def users_list(message):
    """قائمة المستخدمين (للمشرفين)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 هذه الصفحة خاصة بالمشرفين فقط.")
        return
    
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT user_id, username, first_name, total_requests, join_date, is_banned 
        FROM users ORDER BY total_requests DESC LIMIT 20
    ''')
    
    users = cursor.fetchall()
    
    users_text = "<b>👥 آخر 20 مستخدم نشط:</b>\n\n"
    
    for user in users:
        user_id_db, username, first_name, total_req, join_date, banned = user
        username_display = f"@{username}" if username else "لا يوجد"
        banned_status = "🚫" if banned else "✅"
        
        join_date_short = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d')
        
        users_text += f"{banned_status} <b>{first_name}</b> ({username_display})\n"
        users_text += f"┣ معرف: <code>{user_id_db}</code>\n"
        users_text += f"┣ طلبات: {total_req}\n"
        users_text += f"┗ تاريخ: {join_date_short}\n\n"
    
    # تقسيم النص إذا كان طويلاً
    if len(users_text) > 4000:
        parts = [users_text[i:i+4000] for i in range(0, len(users_text), 4000)]
        for part in parts:
            bot.send_message(user_id, part, parse_mode='HTML')
    else:
        bot.send_message(user_id, users_text, parse_mode='HTML')

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """معالج جميع الرسائل الأخرى"""
    user_id = message.from_user.id
    
    # التحقق من الحظر
    if db.is_banned(user_id):
        bot.reply_to(message, "🚫 أنت محظور من استخدام هذا البوت.")
        return
    
    # إذا كان المستخدم في حالة انتظار رابط ولكن لم يتم تسجيله في next_step_handler
    bot.reply_to(
        message,
        "❌ أمر غير معروف. الرجاء استخدام الأزرار في القائمة.",
        reply_markup=main_menu_keyboard()
    )

# ==================== تشغيل البوت ====================

def print_bot_info():
    """طباعة معلومات البوت عند التشغيل"""
    print(f"{G}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{G}║{Y}                   بوت LeoFame - الإصدار 2.0              {G}║{RESET}")
    print(f"{G}╠══════════════════════════════════════════════════════════╣{RESET}")
    print(f"{G}║{C}  📱 تم تطوير الأداة إلى بوت تليجرام متكامل              {G}║{RESET}")
    print(f"{G}║{C}  ✨ جميع الخدمات متوفرة مع مميزات إضافية                {G}║{RESET}")
    print(f"{G}╠══════════════════════════════════════════════════════════╣{RESET}")
    print(f"{G}║{F}  يوزر المبرمج: {B}@Xiil6                                  {G}║{RESET}")
    print(f"{G}║{F}  قناة المبرمج: {B}@V_ii5                                  {G}║{RESET}")
    print(f"{G}║{F}  البوت: {B}@{BOT_USERNAME}                                   {G}║{RESET}")
    print(f"{G}╚══════════════════════════════════════════════════════════╝{RESET}")
    print(f"\n{Y}[✓] تم تشغيل البوت بنجاح!{RESET}")
    print(f"{C}[~] جاري الاستماع للرسائل...{RESET}\n")

if __name__ == "__main__":
    try:
        print_bot_info()
        
        # التأكد من وجود توكن البوت
        if BOT_TOKEN == "8125932385:AAE1nkYYXbQTmuY6079dixugL_dbXrrLfh4":
            print(f"{R}[-] خطأ: الرجاء وضع توكن البوت في المتغير BOT_TOKEN{RESET}")
            print(f"{Y}[!] يمكنك الحصول على توكن من @BotFather على تليجرام{RESET}")
            sys.exit(1)
        
        # تشغيل البوت
        logger.info("Starting bot...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        print(f"\n{R}تم إيقاف البوت بواسطة المستخدم{RESET}")
        logger.info("Bot stopped by user")
    except Exception as e:
        print(f"{R}حدث خطأ في تشغيل البوت: {e}{RESET}")
        logger.error(f"Bot error: {e}")
    finally:
        print(f"{Y}تم إيقاف البوت{RESET}")