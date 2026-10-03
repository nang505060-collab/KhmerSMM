import os
import requests
from flask import Flask, request
from openai import OpenAI

TELEGRAM_BOT_TOKEN = "7690815836:AAE3IdIrevWkjbjWiJVRSV_0vU6LUTOf2to"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)

def send_telegram_message_with_buttons(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "📥 ដាក់វីដេអូចូល", "callback_data": "upload_video"}],
            [{"text": "▶️ ដំណើរការវីដេអូ", "callback_data": "process_video"}],
            [{"text": "⏹️ បញ្ចប់វីដេអូ", "callback_data": "finish_video"}]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard
    }
    requests.post(url, json=payload)

@app.route("/")
def home():
    return "Telegram Bot Webhook is running!"

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        
        # 1. ករណីអ្នកប្រើប្រាស់ចុចលើប៊ូតុងអន្តរកម្ម (Inline Buttons)
        if "callback_query" in data:
            query = data["callback_query"]
            chat_id = query["message"]["chat"]["id"]
            callback_data = query["data"]
            
            if callback_data == "upload_video":
                send_telegram_message_with_buttons(chat_id, "📥 សូមផ្ញើឯកសារវីដេអូរបស់អ្នកចូលមកទីនេះដើម្បីចាប់ផ្តើម។")
            elif callback_data == "process_video":
                send_telegram_message_with_buttons(chat_id, "▶️ កំពុងដំណើរការបកប្រែវីដេអូ... សូមរង់ចាំបន្តិច!")
            elif callback_data == "finish_video":
                send_telegram_message_with_buttons(chat_id, "⏹️ ការដំណើរការត្រូវបានបញ្ចប់ដោយជោគជ័យ!")
            return "OK", 200

        # 2. ករណីអ្នកប្រើប្រាស់ផ្ញើសារ ឬពាក្យបញ្ជា /start
        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"]["text"]
            if text == "/start":
                send_telegram_message_with_buttons(chat_id, "👋 សួស្តី! សូមស្វាគមន៍មកកាន់ Bot បកប្រែវីដេអូ។ សូមជ្រើសរើសប៊ូតុងខាងក្រោម ឬផ្ញើវីដេអូរបស់អ្នកចូលមកដើម្បីចាប់ផ្តើម៖")
            return "OK", 200

        # 3. ករណីผู้ใช้งานផ្ញើវីដេអូចូលមកផ្ទាល់
        if "message" in data and "video" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            file_id = data["message"]["video"]["file_id"]
            
            send_telegram_message_with_buttons(chat_id, "⏳ បានទទួលវីដេអូរបស់អ្នកហើយ! កំពុងដំណើរការទាញយក និងបកប្រែ...")
            
            file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
            file_info_res = requests.get(file_info_url).json()
            
            if file_info_res.get("ok"):
                file_path = file_info_res["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                
                video_bytes = requests.get(download_url).content
                input_video_path = "input_video.mp4"
                audio_path = "audio.mp3"
                
                with open(input_video_path, "wb") as f:
                    f.write(video_bytes)
                
                from moviepy.editor import VideoFileClip
                video = VideoFileClip(input_video_path)
                video.audio.write_audiofile(audio_path)
                
                with open(audio_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Translate the following transcript into natural Khmer language suitable for a video voiceover."},
                        {"role": "user", "content": transcript.text}
                    ]
                )
                khmer_text = response.choices[0].message.content
                
                send_telegram_message_with_buttons(chat_id, f"✅ អត្ថបទបកប្រែជាភាសាខ្មែរ៖\n\n{khmer_text}")
                
                for p in [input_video_path, audio_path]:
                    if os.path.exists(p): os.remove(p)
                    
    except Exception as e:
        print(f"Error: {str(e)}")
        
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
