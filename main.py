import requests
import smtplib
from email.mime.text import MIMEText
from groq import Groq
from datetime import date, datetime
import json
import os
import time
import pytz
import secrets

# 🔐 GitHub secrets are being used; no dotenv needed
SUPABASE_URL = os.getenv("SUPABASE_URL")  # Supabase REST endpoint
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

# 🤖 Setup Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

while True:
    print("Checking reminders....")
    try:
        response = requests.get(SUPABASE_URL, headers=headers)
        response.raise_for_status()
        users = response.json()

        # Ensure each user has unsubscribe_token
        for user in users:
            if not user.get("unsubscribe_token"):
                token = secrets.token_urlsafe(16)
                requests.patch(
                    SUPABASE_URL + f"?email=eq.{user['email']}",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"unsubscribe_token": token, "subscribed": True}
                )
                user["unsubscribe_token"] = token

        # Filter out unsubscribed users
        users = [u for u in users if u.get("subscribed", True)]

    except Exception as e:
        print("Error fetching users:", e)
        users = []

    # 🔁 Loop through each user
    for user in users:
        name = user.get("name", "")
        age = user.get("age", "")
        blood = user.get("blood_group", "")
        history = user.get("medical_history", "")
        email = user.get("email", "")
        token = user.get("unsubscribe_token")  # use existing token

        required_fields = ["name", "age", "blood_group", "email", "timezone", "medications"]
        missing = [f for f in required_fields if not user.get(f)]
        if missing:
            print(f"Skipping user, missing fields: {missing}")
            continue

        # User timezone
        user_timezone_str = user.get("timezone", "Asia/Kolkata")
        try:
            user_tz = pytz.timezone(user_timezone_str)
        except Exception:
            print(f"Invalid timezone {user_timezone_str}, defaulting to IST")
            user_tz = pytz.timezone("Asia/Kolkata")

        # Current time in user's timezone
        utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
        user_now = utc_now.astimezone(user_tz)

        # Convert medicines JSON string → list
        meds = json.loads(user.get("medications", "[]"))
        updated = False
        today = user_now.strftime("%Y-%m-%d")

        for m in meds:
            med_name = m['name']
            med_time_str = m['time']
            last_sent = m.get("last_sent", "")

            try:
                # Parse medicine time
                try:
                    med_time_obj = datetime.strptime(med_time_str.strip(), "%I:%M %p")
                except ValueError:
                    med_time_obj = datetime.strptime(med_time_str.strip(), "%I %p")
                med_time_obj = med_time_obj.replace(year=user_now.year, month=user_now.month, day=user_now.day)
                med_time_obj = user_tz.localize(med_time_obj)
                time_diff = (user_now - med_time_obj).total_seconds()

                # Check if already sent today
                if last_sent == today:
                    print(f"Already sent: {med_name}")
                    continue

                # Send if within 1 minute window
                if 0 <= time_diff < 60:
                    print(f"Sending reminder for {name} - {med_name} at {med_time_str}")

                    # 🧠 AI Prompt
                    prompt = f"""
                    Create a short daily health reminder for {name}.

                    Name: {name}
                    Age: {age}
                    Blood Group: {blood}
                    Medical History: {history}

                    Medicine:
                    - {med_name} at {med_time_str}

                    Rules:
                    - Max 5 bullet points
                    - No medical advice
                    - Friendly tone
                    """

                    # Generate AI response
                    summary = None
                    for attempt in range(5):
                        try:
                            res = client.chat.completions.create(
                                model="llama-3.1-8b-instant",
                                messages=[{"role": "user", "content": prompt}]
                            )
                            summary = res.choices[0].message.content
                            break
                        except Exception as e:
                            print(f"Attempt {attempt+1} failed:", e)
                            time.sleep(10)

                    # Fallback if AI fails
                    if summary is None:
                        summary = f"""
                        Hi {name},

                        Please take your medicines on time:

                        {med_name} at {med_time_str}

                        Stay healthy 💙
                        """

                    # Append unsubscribe link
                    unsubscribe_link = f"https://yourdomain.com/unsubscribe?token={token}"
                    summary += f"\n\nTo stop receiving these emails, click here: {unsubscribe_link}"

                    # Send email
                    msg = MIMEText(summary)
                    msg["Subject"] = f"Your Daily Health Reminder - {date.today()}"
                    msg["From"] = EMAIL
                    msg["To"] = email

                    try:
                        server = smtplib.SMTP("smtp.gmail.com", 587)
                        server.starttls()
                        server.login(EMAIL, APP_PASSWORD)
                        server.send_message(msg)
                        server.quit()
                        time.sleep(2)

                        print(f"Email sent to {email}")
                        m["last_sent"] = today
                        updated = True
                    except Exception as e:
                        print(f"Failed for {email}: {e}")
                else:
                    print(f"Not time yet for {name} - {med_name} at {med_time_str}")

            except Exception as e:
                print(f"Invalid medicine time format for {med_time_str}: {e}")
                continue

        # Update Supabase if any medicine sent
        if updated:
            try:
                requests.patch(
                    SUPABASE_URL + f"?email=eq.{email}",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"medications": json.dumps(meds)}
                )
                print("Updated last_sent in DB")
            except Exception as e:
                print("DB update failed:", e)

    print("Sleeping for 60 seconds!\n")
    time.sleep(60)