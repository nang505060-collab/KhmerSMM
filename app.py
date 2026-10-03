import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from moviepy.editor import VideoFileClip
from openai import OpenAI

# យក Token និង API Key របស់អ្នកមកដាក់ទីនេះ
TELEGRAM_BOT_TOKEN = "7690815836:AAHYf6OXsw3U7fzNBUo78-DPJls0ErIDxO8"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)

# បង្កើត Telegram Application
telegram_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ កំពុងទាញយក និងដំណើរការវីដេអូ... សូមរង់ចាំបន្តិច!")
    
    video_file = await update.message.video.get_file()
    input_video_path = "input_video.mp4"
    audio_path = "audio.mp3"
    
    await video_file.download_to_drive(input_video_path)
    
    try:
        # ដកសំឡេងចេញពីវីដេអូ
        video = VideoFileClip(input_video_path)
        video.audio.write_audiofile(audio_path)
        
        # ប្រើ Whisper ដើម្បីបម្លែងសំឡេងជាអត្ថបទ
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        # បកប្រែអត្ថបទទៅជាភាសាខ្មែរ
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Translate the following transcript into natural Khmer language suitable for a video voiceover."},
                {"role": "user", "content": transcript.text}
            ]
        )
        khmer_text = response.choices[0].message.content
        
        await msg.edit_text(f"✅ បានបកប្រែរួចរាល់!\n\nអត្ថបទបកប្រែជាភាសាខ្មែរ៖\n\n{khmer_text}")
        
    except Exception as e:
        await msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការ៖ {str(e)}")
        
    finally:
        if os.path.exists(input_video_path): os.path.exists(input_video_path) and os.remove(input_video_path)
        if os.path.exists(audio_path): os.path.exists(audio_path) and os.remove(audio_path)

# បន្ថែម Handler សម្រាប់វីដេអូ
telegram_app.add_handler(MessageHandler(filters.VIDEO, handle_video))

@app.route("/")
def home():
    return "Telegram Bot is running smoothly!"

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    # รับ update ពី Telegram Webhook
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put(update)
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
