from fastapi import FastAPI, Request, HTTPException
from brain import get_ai_answer
import requests
import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()
processed_messages = set()  # To track processed message IDs and avoid duplicates

paused_users = {}
PAUSE_DURATION = 1800 # 30 minutes in seconds

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_ID = os.getenv("APP_ID")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def get_fb_username(user_id):
    url = f"https://graph.facebook.com/{user_id}?fields=first_name,last_name&access_token={PAGE_ACCESS_TOKEN}"
    try:
        response = requests.get(url)
        data = response.json()
        return f"{data.get("first_name", "")} {data.get("last_name", "")}".strip() or "Unknown User"
    except Exception as e:
        print(f"Error fetching Facebook username: {e}")
        return "Customer"

def notify_admin_via_email(sender_id, page_id):
    if not ADMIN_EMAIL or not EMAIL_PASSWORD:
        print("Admin email or password not set. Skipping email notification.")
        return
    
    username = get_fb_username(sender_id)
    inbox_url = f"https://business.facebook.com/latest/inbox/all?asset_id={page_id}&selected_item_id={sender_id}"

    msg = MIMEMultipart("alternative")
    msg['Subject'] = '🔔 ახალი სურათი Aqua Clean-ის ბოტში!'
    msg['From'] = ADMIN_EMAIL
    msg['To'] = ADMIN_EMAIL

    text_body = f"მომხმარებელი: {username}\nჩატში გადასვლა: {inbox_url}"

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 10px;">
          <h2 style="color: #007bff; margin-top: 0;">🔔 ახალი შეტყობინება</h2>
          <p>მომხმარებელმა <b>{username}</b> გამოაგზავნა ფოტო და ელოდება თქვენს პასუხს.</p>
          
          <div style="margin: 30px 0; text-align: center;">
            <a href="{inbox_url}" 
               style="background-color: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
               ნახვა და პასუხი
            </a>
          </div>
          
          <hr style="border: 0; border-top: 1px solid #eee;">
          <p style="font-size: 12px; color: #888;">
            ეს არის ავტომატური შეტყობინება Aqua Clean-ის ბოტიდან. მომხმარებელი ამჟამად პაუზაზეა.
          </p>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(ADMIN_EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"Admin notified via email about image from user {sender_id}")
    except Exception as e:
        print(f"Error sending email notification: {e}")

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

                    if sender_id in paused_users:
                        time_since_pause = time.time() - paused_users[sender_id]
                        if time_since_pause < PAUSE_DURATION:
                            print(f"--- Bot is paused for user {sender_id}. Time since pause: {time_since_pause:.2f} seconds ---")
                            continue
                        else:
                            del paused_users[sender_id]
                            print(f"--- Pause expired. Resuming bot for user {sender_id} ---")

                    
                    attachments = message_data.get("attachments", [])
                    is_image = False

                    for att in attachments:
                        if att.get("type") == "image":
                            is_image = True
                            break

                    if is_image:
                        print(f"--- Image received from {sender_id}. Pausing bot and notifying admin. ---")
                        paused_users[sender_id] = time.time()

                        notify_admin_via_email(sender_id, recipient_id)

                        send_fb_message(sender_id, "თქვენი სურათი მიღებულია. ჩვენი ადმინისტრატორი მალე დაგიკავშირდებათ.")
                        continue

                    user_text = message_data.get("text", "")

                    if not user_text:
                        continue

                    try:
                        print(f"User sent: {user_text}")
                        ai_response = get_ai_answer(user_text)
                    except Exception as e:
                        print(f"AI Error: {e}")
                        ai_response = "ბოდიში, ამჟამად ტექნიკური პრობლემაა. გთხოვთ, მოგვიანებით სცადოთ."
                    
                    send_fb_message(sender_id, ai_response)
                    print(f"Sent AI response to {sender_id} : {ai_response}")

    return {"status": "success"}