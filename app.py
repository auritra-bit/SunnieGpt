import os
import time
import threading
from flask import Flask, request
from huggingface_hub import InferenceClient
import pytchat
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

app = Flask(__name__)

# Hugging Face and YouTube API
HF_API_KEY = os.getenv("HF_API_KEY")
client = InferenceClient(token=HF_API_KEY)

YOUTUBE_ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("VIDEO_ID")

messages = [
    {
        "role": "assistant",
        "content": "Hello! I'm Sunnie Study GPT 🌞 — your friendly study buddy! Ask me anything, or just tell me how you're feeling today.",
    }
]

def get_youtube_client():
    creds = Credentials(
        token=YOUTUBE_ACCESS_TOKEN,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )
    return build("youtube", "v3", credentials=creds)

def get_live_chat_id(youtube):
    try:
        response = youtube.videos().list(
            part="liveStreamingDetails", id=VIDEO_ID
        ).execute()
        live_chat_id = response["items"][0]["liveStreamingDetails"]["activeLiveChatId"]
        print(f"✅ Live Chat ID: {live_chat_id}")
        return live_chat_id
    except Exception as e:
        print(f"❌ Failed to get liveChatId: {e}")
        return None

def send_message(text):
    try:
        youtube = get_youtube_client()
        live_chat_id = get_live_chat_id(youtube)
        if not live_chat_id:
            print("❌ live_chat_id not found. Skipping message.")
            return
        print(f"📤 Sending: {text}")
        youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text},
                }
            },
        ).execute()
        print("✅ Message sent.")
    except Exception as e:
        print(f"❌ send_message() error: {e}")

def ask_sunnie(question):
    prompt = f"{question} - reply like a friendly study assistant named Sunnie Study GPT. Under 200 characters, no token count info."

    messages.append({"role": "user", "content": prompt})
    print(f"🤖 Asking Sunnie: {question}")
    stream = client.chat.completions.create(
        model="Qwen/Qwen2.5-72B-Instruct",
        messages=messages,
        temperature=0.5,
        max_tokens=2048,
        top_p=0.7,
        stream=True
    )

    reply = ""
    for chunk in stream:
        if chunk.choices[0].delta.get("content"):
            reply += chunk.choices[0].delta["content"]

    messages.append({"role": "assistant", "content": reply})
    print(f"🤖 Sunnie replied: {reply}")
    return reply[:200]

def monitor_chat():
    print("📺 Starting YouTube chat monitor...")
    chat = pytchat.create(video_id=VIDEO_ID)
    while chat.is_alive():
        for c in chat.get().sync_items():
            msg = c.message
            user = c.author.name
            print(f"💬 {user}: {msg}")

            if msg.lower().startswith("!ask "):
                question = msg[5:].strip()
                try:
                    answer = ask_sunnie(question)
                    send_message(f"@{user} {answer}")
                except Exception as e:
                    print(f"❌ Error processing '!ask': {e}")
        time.sleep(1)

@app.route("/")
def hello():
    return "Sunnie Study GPT is running!"

@app.route("/ask")
def ask_query():
    question = request.args.get("msg", "")
    if not question:
        return "❌ Please provide a message using ?msg=your question"
    
    try:
        reply = ask_sunnie(question)
        return reply
    except Exception as e:
        return f"❌ Error: {e}"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    monitor_chat()
