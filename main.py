Again I got multiple reminders for one time- 

import requests
import smtplib
from email.mime.text import MIMEText
from groq import Groq
from datetime import date, datetime, timedelta 
import json
import os
import time
import pytz 

# 🔐 ADD YOUR KEYS HERE
SUPABASE_URL = os.getenv("SUPABASE_URL")  # Your Supabase REST API URL
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

EMAIL = os.getenv("EMAIL")  # Your email address
APP_PASSWORD = os.getenv("APP_PASSWORD")

# 🤖 Setup Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# 📥 Fetch users from Supabase
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

while True:
    print("Checking reminders....")
    try:
        response = requests.get(SUPABASE_URL, headers=headers)
        response.raise_for_status()   # checks if request failed

        users = response.json()

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

        required_fields = ["name", "age", "blood_group", "email", "timezone", "medications"]
        missing = [f for f in required_fields if not user.get(f)]
        if missing:
            print(f"Skipping user, missing fields: {missing}")
            continue

        # Get user's timezone (default to IST if missing)
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
            med_time_str = m['time']  # HH:MM format
            last_sent = m.get("last_sent", "")

            try:
                try:
                    med_time_obj = datetime.strptime(med_time_str.strip(), "%I:%M %p")  # try HH:MM AM/PM
                except ValueError:
                    med_time_obj = datetime.strptime(med_time_str.strip(), "%I %p")      # fallback HH AM/PM
                med_time_obj = med_time_obj.replace(year=user_now.year, month=user_now.month, day=user_now.day)
                med_time_obj = user_tz.localize(med_time_obj)
                time_diff = (user_now - med_time_obj).total_seconds()

                if last_sent == today:
                    print(f"Already sent: {med_name}")
                    continue
                if 0 <= time_diff < 60:  # within the past 1 minute
                    print(f"Time to send reminder for {name} - {med_name} at {med_time_str}")
                    


                    # send email for this medicine
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

                    # 🤖 Generate response
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
                        

                    # fallback if AI fails
                    if summary is None:
                        summary = f"""
                    Hi {name},

                    Please take your medicines on time:

                    {med_name} at {med_time_str}

                    Stay healthy 💙
                    """

                    # 📩 Send Email
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
        
        # 🔄 Update Supabase if any medicine sent
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

print("Sleeping for 60 seconds..\n")
time.sleep(60)  # Wait for 1 minute before checking again