import os
import time
import threading
from flask import Flask, request
from huggingface_hub import InferenceClient
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pathlib import Path

app = Flask(__name__)

TOKEN_FILE = "youtube_token.json"

# 🔐 Environment Variables
HF_API_KEY = os.getenv("HF_API_KEY")
YOUTUBE_ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("VIDEO_ID")

# 🤖 Hugging Face LLM Client
client = InferenceClient(token=HF_API_KEY)

# Globals for YouTube client and live chat ID
youtube = None
live_chat_id = None


# 🔌 YouTube API Client Initialization
def get_youtube_client():
    creds = None

    # ✅ Load credentials from file if exists
    if Path(TOKEN_FILE).exists():
        print("🔐 Loading credentials from saved file...")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)

    else:
        print("🪪 Loading credentials from environment...")
        creds = Credentials(
            token=YOUTUBE_ACCESS_TOKEN,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
        )

    # 🔄 Refresh if expired
    if creds.expired and creds.refresh_token:
        print("🔁 Access token expired, refreshing...")
        creds.refresh(Request())

        # 💾 Save updated token
        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            print("✅ Token refreshed and saved.")
        except Exception as e:
            print(f"❌ Failed to save token: {e}")

    return build("youtube", "v3", credentials=creds)


def get_live_chat_id(youtube_client):
    try:
        response = youtube_client.videos().list(
            part="liveStreamingDetails", id=VIDEO_ID
        ).execute()
        live_chat_id = response["items"][0]["liveStreamingDetails"]["activeLiveChatId"]
        print(f"✅ Live Chat ID: {live_chat_id}")
        return live_chat_id
    except Exception as e:
        print(f"❌ Failed to get liveChatId: {e}")
        return None


def init_youtube():
    global youtube, live_chat_id
    youtube = get_youtube_client()
    live_chat_id = get_live_chat_id(youtube)
    if not live_chat_id:
        print("❌ No active live chat ID.")
        return False
    return True


def get_chat_messages(youtube_client, live_chat_id, page_token=None):
    kwargs = {
        "liveChatId": live_chat_id,
        "part": "snippet,authorDetails",
        "maxResults": 200,
    }
    if page_token:
        kwargs["pageToken"] = page_token

    return youtube_client.liveChatMessages().list(**kwargs).execute()


def send_message(text):
    global youtube, live_chat_id
    if not youtube or not live_chat_id:
        print("❌ YouTube client or live_chat_id not initialized.")
        return
    try:
        print(f"📤 Sending message: {text}")
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
        print(f"❌ send_message error: {e}")


def ask_sunnie(question):
    prompt = f"{question} - reply like a friendly study assistant named Sunnie Study GPT. Under 200 characters, no token count info."

    print(f"🤖 Asking Sunnie: {question}")

    messages = [
        {
            "role": "system",
            "content": "You're Sunnie Study GPT 🌞 — a friendly, helpful study assistant. Answer warmly and simply. Under 200 characters, no token count info.",
        },
        {"role": "user", "content": prompt},
    ]

    stream = client.chat.completions.create(
        model="Qwen/Qwen2.5-72B-Instruct",
        messages=messages,
        temperature=0.5,
        max_tokens=200,
        top_p=0.7,
        stream=True,
    )

    reply = ""
    for chunk in stream:
        if chunk.choices[0].delta.get("content"):
            reply += chunk.choices[0].delta["content"]

    print(f"🤖 Sunnie replied: {reply}")
    return reply[:200]


def handle_ask_command(username, question):
    try:
        answer = ask_sunnie(question)
        send_message(f"@{username} {answer}")
    except Exception as e:
        print(f"❌ Error in handle_ask_command: {e}")
        send_message(f"⚠️ @{username}, Sunnie is sleeping. Try again later!")


def monitor_chat():
    global youtube, live_chat_id
    print("📺 Starting YouTube chat monitor (via API)...")

    if not youtube or not live_chat_id:
        print("❌ YouTube client or live_chat_id not initialized.")
        return

    next_page_token = None

    while True:
        try:
            response = get_chat_messages(youtube, live_chat_id, next_page_token)
            next_page_token = response.get("nextPageToken")
            items = response.get("items", [])

            for item in items:
                user = item["authorDetails"]["displayName"]
                msg = item["snippet"]["textMessageDetails"]["messageText"]
                print(f"💬 {user}: {msg}")

                if msg.lower().startswith("!ask "):
                    question = msg[5:].strip()
                    if question:
                        threading.Thread(
                            target=handle_ask_command, args=(user, question)
                        ).start()
                    else:
                        send_message(f"@{user} Please type your question after !ask 😚")

            time.sleep(3)

        except Exception as e:
            print(f"❌ YouTube API monitor_chat error: {e}")
            time.sleep(10)


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


if __name__ == "__main__":
    if not init_youtube():
        print("❌ Initialization failed. Exiting.")
        exit(1)

    def run_flask():
        app.run(host="0.0.0.0", port=10000)

    threading.Thread(target=run_flask).start()

    monitor_chat()
