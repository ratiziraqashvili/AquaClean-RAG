from fastapi import FastAPI, Request, HTTPException
from brain import get_ai_answer
import requests
import os
import json
import time

app = FastAPI()
processed_messages = set()  # To track processed message IDs and avoid duplicates

paused_users = {}
PAUSE_DURATION = 1800 # 30 minutes in seconds

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_ID = os.getenv("APP_ID")

def send_fb_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"

    payload = {
        "recipient": {"id": str(recipient_id)},
        "message": {"text": message_text.strip()},
        "messaging_type": "RESPONSE"
    }

    encoded_payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    print(f"--- Debug: Payload size: {len(encoded_payload)} bytes ---")
    print(f"--- Debug: Message length: {len(message_text)} chars ---")
    print(f"--- Debug: Message text: {message_text} ---")

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
                    message_data = messaging_event["message"]
                    sender_id = messaging_event["sender"]["id"]
                    recipient_id = messaging_event["recipient"]["id"]

                    if msg_id:
                        processed_messages.add(msg_id)
                        if len(processed_messages) > 1000:
                            processed_messages.pop()  # Remove the oldest message ID to prevent memory bloat
                    
                    if message_data.get("is_echo"):
                        target_user_id = recipient_id
                        echo_app_id = message_data.get("app_id")
                        admin_text = message_data.get("text", "")

                        if admin_text.strip().lower() == "/resume":
                            if target_user_id in paused_users:
                                del paused_users[target_user_id]
                                print(f"Resumed messages for user: {target_user_id}")

                        elif str(echo_app_id) != str(APP_ID):
                            paused_users[target_user_id] = time.time()
                            print(f"--- Human admin intervened. Pausing bot for user {target_user_id} ---")

                        continue

                    user_text = message_data.get("text", "")

                    if sender_id in paused_users:
                        time_since_pause = time.time() - paused_users[sender_id]
                        if time_since_pause < PAUSE_DURATION:
                            print(f"--- Bot is paused for user {sender_id}. Time since pause: {time_since_pause:.2f} seconds ---")
                            continue
                        else:
                            del paused_users[sender_id]
                            print(f"--- Pause expired. Resuming bot for user {sender_id} ---")

                    try:
                        print(f"User sent: {user_text}")
                        ai_response = get_ai_answer(user_text)
                    except Exception as e:
                        print(f"AI Error: {e}")
                        ai_response = "ბოდიში, ამჟამად ტექნიკური პრობლემაა. გთხოვთ, მოგვიანებით სცადოთ."
                    
                    send_fb_message(sender_id, ai_response)
                    print(f"Sent AI response to {sender_id} : {ai_response}")

    return {"status": "success"}