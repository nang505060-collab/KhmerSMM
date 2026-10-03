import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from moviepy.editor import VideoFileClip
from openai import OpenAI

# ដាក់ Token និង API Key ដែលអ្នកទើបតែទទួលបានទីនេះ
TELEGRAM_BOT_TOKEN = "7690815836:AAHYf6OXsw3U7fzNBUo78-DPJls0ErIDxO8"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ កំពុងទាញយក និងដំណើរការវីដេអូ... សូមរង់ចាំបន្តិច!")
    
    video_file = await update.message.video.get_file()
    input_video_path = "input_video.mp4"
    audio_path = "audio.mp3"
    
    await video_file.download_to_drive(input_video_path)
    
    try:
        # ជំហានទី 1: ដកសំឡេងចេញពីវីដេអូ
        video = VideoFileClip(input_video_path)
        video.audio.write_audiofile(audio_path)
        
        # ជំហានទី 2: ប្រើ Whisper ដើម្បីបម្លែងសំឡេងជាអត្ថបទ (Transcript)
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        # ជំហានទី 3: បកប្រែអត្ថបទទៅជាភាសាខ្មែរ
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
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)

def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))

    print("🤖 Bot កំពុងដំណើរការហើយ...")
    application.run_polling()

if __name__ == "__main__":
    main()
