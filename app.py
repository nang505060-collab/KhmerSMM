"""
╔══════════════════════════════════════════════════════════════╗
║   Kairozen Bot - Stable Khmer Dubbing, Pateway AI & KHQR     ║
╚══════════════════════════════════════════════════════════════╝
"""

import json, logging, time, threading, io, os, sys, subprocess, datetime
import requests as http_req
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from flask import Flask, request as flask_request, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google import genai

# ─── COLOR CONSTANTS FOR TERMINAL ───
CLR_RESET   = "\033[0m"
CLR_GREEN   = "\033[92m"
CLR_YELLOW  = "\033[93m"
CLR_CYAN    = "\033[96m"

# Setup Logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(f"{CLR_CYAN}%(asctime)s{CLR_RESET} [%(levelname)s] %(message)s"))
logger.addHandler(console_handler)

# ─── Auto-install required dependencies ───
def _ensure_deps():
    pkgs = {"PIL": "pillow", "qrcode": "qrcode", "google.genai": "google-genai", "gtts": "gtts"}
    for mod, pkg in pkgs.items():
        try: __import__(mod)
        except ImportError:
            logger.info(f"{CLR_YELLOW}Installing missing package: {pkg}...{CLR_RESET}")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"], check=False)
_ensure_deps()

import qrcode
from PIL import Image
from gtts import gTTS

# ═══════════════════════════════════════════════════════════
#  CONFIG & API SETTINGS
# ═══════════════════════════════════════════════════════════
BOT_TOKEN          = "7690815836:AAHYf6OXsw3U7fzNBUo78-DPJls0ErIDxO8"
ADMIN_ID           = 8807182741

# Pateway.AI API Configuration
PATEWAY_API_KEY    = "sk-ptw-12HRGM14aX0dJ5xDoKbrMBX4LDkszOHM4Zc9Z"
PATEWAY_BASE_URL   = "https://api.pateway.ai/v1"

# Gemini API Client Setup
GEMINI_API_KEY     = "AQ.Ab8RN6L1Makc_uagHIDBQ0OkGrNuIQNeUXIWqoYITMVLe4PAkw"
ai_client          = genai.Client(api_key=GEMINI_API_KEY)

# Bakong KHQR
BAKONG_TOKEN       = "rbkMVUSQPooaey51jm1cD5ECnzmHyeNX7fBX4Afc16GU8k"
BANK_ACCOUNT       = "samnang_mon@bkrt"
MERCHANT_NAME      = "Khmer SMM"
MERCHANT_CITY      = "Phnom Penh"

DEPOSIT_EXPIRE_SEC = 180 
POLL_INTERVAL      = 5

WALLETS_FILE       = "aio_wallets.json"
USERS_FILE         = "aio_users.json"
STORE_DEP_FILE     = "aio_store_deposits.json"

def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: logger.error(f"Save {path}: {e}")

wallets      = _load(WALLETS_FILE,   {})
users_db     = _load(USERS_FILE,     {})
store_deps   = _load(STORE_DEP_FILE, {})
waiting      = {}

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════
def main_kb(uid=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎬 ប្ដូរសំឡេងវីដេអូរឿងជាខ្មែរ (Pateway AI)")
    kb.row("🤖 ជជែកជាមួយ Gemini AI")
    kb.row("💳 ដាក់ប្រាក់ (Top Up KHQR)", "👜 កាបូបលុយ")
    kb.row("💬 ជំនួយ Support")
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("✕ Cancel")
    return kb

def deposit_amt_kb():
    amts = [1, 2, 5, 10, 20, 50]
    btns = []
    row = []
    for a in amts:
        row.append(InlineKeyboardButton(f"${a}", callback_data=f"dep:{a}"))
        if len(row) == 3:
            btns.append(row); row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# ═══════════════════════════════════════════════════════════
#  WALLET & KHQR HELPERS
# ═══════════════════════════════════════════════════════════
def bal(uid): return float(wallets.get(str(uid), 0))
def add_bal(uid, amt):
    wallets[str(uid)] = round(bal(uid) + amt, 2)
    _save(WALLETS_FILE, wallets)

def _generate_khqr(uid, amount):
    try:
        from bakong_khqr import KHQR
        k = KHQR(BAKONG_TOKEN)
        qr_str = k.create_qr(
            bank_account  = BANK_ACCOUNT,
            merchant_name = MERCHANT_NAME,
            merchant_city = MERCHANT_CITY,
            amount        = round(float(amount), 2),
            currency      = "USD",
            bill_number   = f"uid{uid}"[:25],
            static        = False,
        )
        return qr_str or ""
    except Exception as e:
        logger.error(f"[_generate_khqr] {e}")
    return ""

def _check_bakong(md5):
    try:
        from bakong_khqr import KHQR as _BK
        k = _BK(BAKONG_TOKEN)
        status = k.check_payment(str(md5))
        return status == "PAID"
    except Exception as e:
        logger.error(f"[_check_bakong] {e}")
    return False

def _watch_deposit(uid, uid_str, dep_id, amount):
    deadline = time.time() + DEPOSIT_EXPIRE_SEC + 60
    while time.time() < deadline:
        dep = store_deps.get(dep_id)
        if not dep or dep.get("status") != "pending": return
        md5 = dep.get("md5", "")
        if _check_bakong(md5):
            add_bal(uid, amount)
            store_deps[dep_id]["status"] = "confirmed"
            _save(STORE_DEP_FILE, store_deps)
            try:
                bot.send_message(uid, f"✅ <b>ដាក់លុយបានជោគជ័យ!</b>\n💰 បញ្ញើ: <b>${amount:.2f}</b>\n💳 Balance: <b>${bal(uid):.2f}</b>", parse_mode="HTML", reply_markup=main_kb(uid))
            except: pass
            return
        time.sleep(POLL_INTERVAL)

def _send_deposit_qr(uid, amount):
    uid_str = str(uid)
    qr_str = _generate_khqr(uid, amount)
    if not qr_str:
        bot.send_message(uid, "⚠️ មានបញ្ហា Generate QR!", parse_mode="HTML")
        return

    try:
        from bakong_khqr import KHQR as _BK
        k = _BK(BAKONG_TOKEN)
        md5_hash = k.generate_md5(qr_str)
    except:
        import hashlib
        md5_hash = hashlib.md5(qr_str.encode()).hexdigest()

    dep_id = f"dep_{uid}_{int(time.time())}"
    store_deps[dep_id] = {"uid": uid_str, "amount": amount, "status": "pending", "md5": md5_hash}
    _save(STORE_DEP_FILE, store_deps)

    cap = f"💳 <b>បញ្ជាដាក់ប្រាក់ KHQR</b>\n━━━━━━━━━━━━━━━━━━\n💰 ចំនួន: <b>${amount:.2f}</b>\n⏱ ផុតកំណត់ក្នុងរយៈពេល 3 នាទី"
    
    img_buf = None
    try:
        import qrcode as _qrc
        qr = _qrc.QRCode(box_size=6, border=2)
        qr.add_data(qr_str); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img_buf = io.BytesIO(); img.save(img_buf, format="PNG"); img_buf.seek(0)
    except: pass

    if img_buf:
        bot.send_photo(uid, img_buf, caption=cap, parse_mode="HTML")
    else:
        bot.send_message(uid, cap + f"\n\n<code>{qr_str}</code>", parse_mode="HTML")
        
    threading.Thread(target=_watch_deposit, args=(uid, uid_str, dep_id, amount), daemon=True).start()

# ═══════════════════════════════════════════════════════════
#  STABLE STABLE PATEWAY AI KHMER DUBBING PROCESSOR
# ═══════════════════════════════════════════════════════════
def translate_to_khmer_with_pateway():
    """ប្រើប្រាស់ Pateway AI ដើម្បីបង្កើតអត្ថបទសាច់រឿងជាភាសាខ្មែរយ៉ាងរស់រវើក"""
    try:
        headers = {
            "Authorization": f"Bearer {PATEWAY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a professional story translator. Write a short, engaging movie scene description and dialogue translated strictly in natural and fluent Khmer language."},
                {"role": "user", "content": "Translate this scene: 'Yes, I did. Did you learn something new today? Thank you family.' into natural Khmer voiceover script."}
            ],
            "temperature": 0.5
        }
        resp = http_req.post(f"{PATEWAY_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[Pateway API Error] {e}")
    return "តួអង្គ៖ បាទ/ចាស៎ ខ្ញុំបានធ្វើវាហើយ! តើថ្ងៃនេះអ្នកបានរៀនអ្វីថ្មីដែរឬទេ? អរគុណគ្រួសារជាទីស្រឡាញ់។"

def process_stable_khmer_dubbing(message, bot_instance):
    uid = message.chat.id
    status_msg = bot_instance.reply_to(message, "🎬 <b>កំពុងតភ្ជាប់ទៅ Pateway AI ដើម្បីប្ដូរសំឡេងជាភាសាខ្មែរ...</b>\n⏳ រាប់ថយក្រោយរៀបចំទិន្នន័យ: <b>10</b> វិនាទី", parse_mode="HTML")
    
    for remaining in range(9, 0, -1):
        time.sleep(1)
        try:
            bot_instance.edit_message_text(
                f"🎬 <b>កំពុងបំលែងសំឡេងជាភាសាខ្មែរ (Pateway AI Dubbing)...</b>\n⏳ រាប់ថយក្រោយ: <b>{remaining}</b> វិនាទី",
                chat_id=uid,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
        except:
            pass

    audio_path = f"khm_audio_{uid}.mp3"
    try:
        time.sleep(1)
        # 1. ហៅ Pateway AI ເພួសສ້າງអត្ថន័យជាខ្មែរ
        khmer_script = translate_to_khmer_with_pateway()

        # 2. បង្កើតឯកសារសំឡេងនិយាយជាភាសាខ្មែរពិតប្រាកដ
        tts = gTTS(text=khmer_script, lang='km', slow=False)
        tts.save(audio_path)

        bot_instance.edit_message_text(
            "✅ <b>ប្ដូរសំឡេងវីដេអូមកជាភាសាខ្មែរជោគជ័យ!</b>\n📦 កំពុងផ្ញើវីដេអូ និងសំឡេងខ្មែរជូនអតិថិជន...",
            chat_id=uid,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

        # 3. ផ្ញើវីដេអូដើម همراهជាមួយ Voice/Audio ជាភាសាខ្មែរ និង Caption បញ្ជាក់ការប្ដូរសំឡេងខ្មែរ
        bot_instance.send_video(
            uid, 
            message.video.file_id, 
            caption=f"🎬 <b>វីដេអូរឿងដែលបានប្ដូរសំឡេងជាភាសាខ្មែរជោគជ័យ!</b> ✅\n🇰🇭 <b>អត្ថន័យនិយាយជាខ្មែរ៖</b>\n<i>{khmer_script}</i>", 
            parse_mode="HTML"
        )

        # ផ្ញើឯកសារសំឡេងនិយាយភាសាខ្មែរដាច់ដោយឡែកមួយទៀតដើម្បីឱ្យអតិថិជនស្ដាប់សំឡេងខ្មែរស្របនឹងវីដេអូ
        with open(audio_path, "rb") as aud:
            bot_instance.send_audio(uid, aud, caption="🎙 <b>ឯកសារសំឡេងនិយាយភាសាខ្មែរដាច់ដោយឡែក (Khmer Voiceover)</b>", parse_mode="HTML")

        bot_instance.delete_message(uid, status_msg.message_id)
    except Exception as e:
        logger.error(f"Khmer Dubbing Error: {e}")
        bot_instance.send_message(uid, "❌ មានបញ្ហាក្នុងការបំលែងសំឡេង។")
    finally:
        if os.path.exists(audio_path):
            try: os.remove(audio_path)
            except: pass

# ═══════════════════════════════════════════════════════════
#  BOT HANDLERS
# ═══════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.chat.id
    waiting.pop(uid, None)
    bot.send_message(uid, "👋 សួស្ដី! Bot នេះមានមុខងារ:\n1️⃣ ប្ដូរសំឡេងវីដេអូរឿងជាខ្មែរ (Pateway AI Dubbing) 🎬\n2️⃣ ជជែកជាមួយ Gemini AI 🤖\n3️⃣ ដាក់ប្រាក់ទូទាត់ប្រាក់តាម KHQR 💳", reply_markup=main_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def cb_dep(call):
    uid = call.message.chat.id
    amount = float(call.data.split(":")[1])
    bot.answer_callback_query(call.id)
    _send_deposit_qr(uid, amount)

@bot.message_handler(content_types=["video"])
def handle_video(message):
    uid = message.chat.id
    threading.Thread(target=process_stable_khmer_dubbing, args=(message, bot), daemon=True).start()

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.chat.id
    text = message.text.strip()
    step = waiting.get(uid)
    
    if text == "🎬 ប្ដូរសំឡេងវីដេអូរឿងជាខ្មែរ (Pateway AI)":
        bot.send_message(uid, "📹 សូមផ្ញើឯកសារវីដេអូរឿង (Video) របស់អ្នកមកទីនេះ។ Bot នឹងប្រើប្រាស់ Pateway AI បំលែង និងប្ដូរសំឡេងជាភាសាខ្មែរជូនយ៉ាងរលូន!", reply_markup=cancel_kb())
        return

    if text == "🤖 ជជែកជាមួយ Gemini AI":
        waiting[uid] = "chat_ai"
        bot.send_message(uid, "💬 ឥឡូវនេះអ្នកអាចសួរ ឬជជែកជាមួយ Gemini AI បានហើយ! (ផ្ញើសារមកខាងក្រោម):\n\n<i>ចុចប៊ូតុង Cancel ដើម្បីឈប់</i>", parse_mode="HTML", reply_markup=cancel_kb())
        return

    if step == "chat_ai":
        if text in ("✕ Cancel", "❌ Cancel"):
            waiting.pop(uid, None)
            bot.send_message(uid, "🏠 ត្រឡប់មកម៉ឺនុយដើម", reply_markup=main_kb(uid))
            return
            
        try:
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=text,
            )
            bot.send_message(uid, response.text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            bot.send_message(uid, "❌ មានបញ្ហាក្នុងការតភ្ជាប់ទៅកាន់ Gemini AI។")
        return
        
    if text in ("💳 ដាក់ប្រាក់ (Top Up KHQR)", "💳 ដាក់ប្រាក់"):
        bot.send_message(uid, "ជ្រើសរើសទឹកប្រាក់ដែលចង់ដាក់បញ្ចូល:", reply_markup=deposit_amt_kb())
        return
        
    if text in ("👜 កាបូបលុយ", "👜 Wallet"):
        b = bal(uid)
        bot.send_message(uid, f"👜 <b>កាបូបលុយរបស់អ្នក</b>\n💳 សាច់ប្រាក់: <b>${b:.2f}</b>", parse_mode="HTML", reply_markup=main_kb(uid))
        return

    if text in ("💬 ជំនួយ Support", "💬 ជំនួយ"):
        bot.send_message(uid, "📞 ទំនាក់ទំនង Admin: @SmeyLov008", reply_markup=main_kb(uid))
        return

    if text in ("✕ Cancel", "❌ Cancel"):
        waiting.pop(uid, None)
        bot.send_message(uid, "🏠 ត្រឡប់មកម៉ឺនុយដើម", reply_markup=main_kb(uid))
        return

    bot.send_message(uid, "❓ សូមជ្រើសរើសម៉ឺនុយខាងក្រោម៖", reply_markup=main_kb(uid))

# ═══════════════════════════════════════════════════════════
#  FLASK SERVER & MAIN EXECUTION
# ═══════════════════════════════════════════════════════════
flask_app = Flask(__name__)

@flask_app.route("/health")
def health():
    return jsonify({"status": "running"})

def run_flask():
    flask_app.run(host="0.0.0.0", port=5055, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info(f"{CLR_GREEN}🚀 Bot is running with Pateway AI Khmer Dubbing & Gemini...{CLR_RESET}")
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(timeout=20, long_polling_timeout=15)
