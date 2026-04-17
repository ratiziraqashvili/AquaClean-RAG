from fastapi import FastAPI, Request, HTTPException
from brain import get_ai_answer
import requests
import os
import json
import time

app = FastAPI()

processed_messages = set()  # To track processed message IDs and avoid duplicates
paused_users = {}  # To track users for whom the bot is paused
PAUSE_DURATION = 30 * 60  # 30 Min in seconds

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
EMAIL = os.getenv("EMAIL")

def send_fb_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"

    payload = {
        "recipient": {"id": str(recipient_id)},
        "message": {"text": message_text.strip()},
        "messaging_type": "RESPONSE"
    }

    encoded_payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }

    try:
        response = requests.post(url, data=encoded_payload, headers=headers,  timeout=10)
        print(f"--- Debug: Facebook API response: {response.status_code} - {response.text} ---")
        return response.json()
    except Exception as e:
        print(f"Error sending message to Facebook: {e}")
        return None
    
def is_paused(sender_id: str) -> bool:
    """Returns True if the bot should stay silent for this user."""
    expiry = paused_users.get(sender_id)
    if expiry is None:
        return False
    if time.time() > expiry:
        del paused_users[sender_id]  # Unpause after duration
        return False
    return True


@app.get("/webhook")
async def verify(request: Request):
    """This endpoint is only for Meta to verify your server exists."""
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/webhook")
async def handle_messages(request: Request):
    """This is where the actual social media messages arrive."""
    data = await request.json()

    if data.get("object") in ["page", "instagram"]:
        print(f"--- Debug: Webhook object type: {data.get('object')} ---")
        for entry in data["entry"]:
            for messaging_event in entry.get("messaging", []):
                msg_id = messaging_event.get("message", {}).get("mid")

                if msg_id in processed_messages:
                    print(f"Skipping duplicate message: {msg_id}")
                    continue

                if "message" in messaging_event:
                    user_text = messaging_event["message"]["text"]
                    sender_id = messaging_event["sender"]["id"]

                    print(f"--- Debug: Raw sender_id: '{sender_id}' ---")
                    print(f"--- Debug: Full messaging_event: {messaging_event} ---")

                    processed_messages.add(msg_id)

                    if len(processed_messages) > 1000:
                        processed_messages.pop()  # Remove the oldest message ID to prevent memory bloat
                    
                    try:
                        # 1. AI starts thinking
                        print(f"User sent: {user_text}")
                        ai_response = get_ai_answer(user_text)
                    except Exception as e:
                        print(f"AI Error: {e}")
                        ai_response = "ბოდიში, ამჟამად ტექნიკური პრობლემაა. გთხოვთ, მოგვიანებით სცადოთ."

                    # 2. AI sends the answer back to the user
                    send_fb_message(sender_id, ai_response)
                    print(f"Sent AI response to {sender_id} : {ai_response}")
                    

    return {"status": "success"}