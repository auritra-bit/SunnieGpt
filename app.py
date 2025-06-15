import os
import time
import threading
from flask import Flask, request
from huggingface_hub import InferenceClient
import pytchat
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

app = Flask(__name__)

# 🔐 Environment Variables
HF_API_KEY = os.getenv("HF_API_KEY")
YOUTUBE_ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("VIDEO_ID")

# 🤖 Hugging Face LLM Client
client = InferenceClient(token=HF_API_KEY)

# 💬 Chat memory
messages = [
    {
        "role": "assistant",
        "content": "Hello! I'm Sunnie Study GPT 🌞 — your friendly study buddy! Ask me anything, or just tell me how you're feeling today.",
    }
]

# 🔌 YouTube API Client
def get_youtube_client():
    creds = Credentials(
        token=YOUTUBE_ACCESS_TOKEN,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET
    )

    if creds.expired and creds.refresh_token:
        print("🔁 Access token expired, refreshing...")
        creds.refresh(Request())

    return build("youtube", "v3", credentials=creds)

# 📺 Get Live Chat ID
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

# ✉️ Send Message to YouTube Chat
def send_message(text):
    try:
        youtube = get_youtube_client()
        if not youtube:
            print("❌ YouTube client not initialized.")
            return

        live_chat_id = get_live_chat_id(youtube)
        if not live_chat_id:
            print("❌ live_chat_id is None, skipping send.")
            return

        print(f"📤 Sending message to chat: {text}")
        response = youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text},
                }
            },
        ).execute()
        print("✅ Message sent successfully.")
    except Exception as e:
        print(f"❌ send_message() error: {e}")

# 🧠 Call Hugging Face LLM
def ask_sunnie(question):
    prompt = f"{question} - reply like a friendly study assistant named Sunnie Study GPT. Under 200 characters, no token count info."

    print(f"🤖 Asking Sunnie: {question}")

    messages = [
        {"role": "system", "content": "You're Sunnie Study GPT 🌞 — a friendly, helpful study assistant. Answer warmly and simply. Under 200 characters, no token count info."},
        {"role": "user", "content": prompt}
    ]

    stream = client.chat.completions.create(
        model="Qwen/Qwen2.5-72B-Instruct",
        messages=messages,
        temperature=0.5,
        max_tokens=200,
        top_p=0.7,
        stream=True
    )

    reply = ""
    for chunk in stream:
        if chunk.choices[0].delta.get("content"):
            reply += chunk.choices[0].delta["content"]

    print(f"🤖 Sunnie replied: {reply}")
    return reply[:200]

# 🌟 Handle !ask in a separate thread
def handle_ask_command(username, question):
    try:
        answer = ask_sunnie(question)
        send_message(f"@{username} {answer}")
    except Exception as e:
        print(f"❌ Error in handle_ask_command: {e}")
        send_message(f"⚠️ @{username}, Sunnie is sleeping. Try again later!")

# 👁️ Monitor YouTube Chat with auto-reconnect
def monitor_chat():
    print("📺 Starting YouTube chat monitor...")

    while True:
        try:
            chat = pytchat.create(video_id=VIDEO_ID)
            print("🔁 pytchat connection established.")

            while chat.is_alive():
                for c in chat.get().sync_items():
                    msg = c.message
                    user = c.author.name
                    print(f"💬 {user}: {msg}")

                    if msg.lower().startswith("!ask "):
                        question = msg[5:].strip()
                        if question:
                            threading.Thread(target=handle_ask_command, args=(user, question)).start()
                        else:
                            send_message(f"@{user} Please type your question after !ask 😚")

                time.sleep(1)

            print("⚠️ Chat disconnected. Reconnecting...")
        except Exception as e:
            print(f"❌ monitor_chat() error: {e}")
            print("⏳ Retrying in 10 seconds...")
            time.sleep(10)

# 🌐 Flask Web Server
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

# 🚀 Run Flask and Monitor Chat
if __name__ == "__main__":
    threading.Thread(target=run_flask := lambda: app.run(host="0.0.0.0", port=10000)).start()
    threading.Thread(target=monitor_chat).start()
