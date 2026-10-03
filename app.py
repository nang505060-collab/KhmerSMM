import os
import requests
from flask import Flask, request
from openai import OpenAI

# ដាក់ Token និង API Key របស់អ្នកទីនេះ
TELEGRAM_BOT_TOKEN = "7690815836:AAHYf6OXsw3U7fzNBUo78-DPJls0ErIDxO8"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

@app.route("/")
def home():
    print("Health check endpoint accessed.")
    return "Telegram Bot Webhook is running successfully!"

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        print(f"Received data: {data}")
        
        # ពិនិត្យមើលថាតើมีសារ ឬវីដេអូផ្ញើមកដែរឬទេ
        if "message" in data and "video" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            file_id = data["message"]["video"]["file_id"]
            
            send_telegram_message(chat_id, "⏳ កំពុងទទួលបានវីដេអូ... សូមរង់ចាំបន្តិច!")
            
            # ទាញយក Link ឯកសារពី Telegram
            file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
            file_info_res = requests.get(file_info_url).json()
            
            if file_info_res.get("ok"):
                file_path = file_info_res["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                
                # ဒោនឡូតវីដេអូទុករយៈពេលខ្លី
                video_bytes = requests.get(download_url).content
                input_video_path = "input_video.mp4"
                audio_path = "audio.mp3"
                
                with open(input_video_path, "wb") as f:
                    f.write(video_bytes)
                
                # ទាញយកសំឡេងចេញពីវីដេអូ (ប្រើ MoviePy)
                from moviepy.editor import VideoFileClip
                video = VideoFileClip(input_video_path)
                video.audio.write_audiofile(audio_path)
                
                # បម្លែងសំឡេងទៅជាអត្ថបទជាមួយ Whisper
                with open(audio_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                
                # បកប្រែអត្ថបទទៅជាភាសាខ្មែរជាមួយ GPT-4o
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Translate the following transcript into natural Khmer language suitable for a video voiceover."},
                        {"role": "user", "content": transcript.text}
                    ]
                )
                khmer_text = response.choices[0].message.content
                
                # ផ្ញើលទ្ធផលអត្ថបទបកប្រែត្រឡប់ទៅ Telegram វិញ
                send_telegram_message(chat_id, f"✅ បានបកប្រែរួចរាល់!\n\nអត្ថបទបកប្រែជាភាសាខ្មែរ៖\n\n{khmer_text}")
                
                # លុបឯកសារបណ្តោះអាសន្នចេញ
                for p in [input_video_path, audio_path]:
                    if os.path.exists(p): os.remove(p)
            else:
                send_telegram_message(chat_id, "❌ មិនអាចទាញយកឯកសារវីដេអូបានទេ។")
                
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
