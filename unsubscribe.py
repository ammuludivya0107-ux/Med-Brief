from flask import Flask, request, render_template_string
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")  # e.g., https://yourproject.supabase.co/users
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

app = Flask(__name__)

# Simple unsubscribe page template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Unsubscribe</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: Arial; text-align:center; padding:50px; background:#f2f2f2;}
    .box { background:white; padding:30px; border-radius:10px; display:inline-block;}
    h2 { color:#333; }
    p { color:#555; }
  </style>
</head>
<body>
  <div class="box">
    <h2>{{ message }}</h2>
    <p>{{ sub_message }}</p>
  </div>
</body>
</html>
"""

@app.route("/unsubscribe")
def unsubscribe():
    token = request.args.get("token")
    if not token:
        return render_template_string(HTML_TEMPLATE,
                                      message="Invalid Link",
                                      sub_message="No token provided.")
    try:
        # Find user with this token
        query_url = f"{SUPABASE_URL}?unsubscribe_token=eq.{token}"
        response = requests.get(query_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if not data:
            return render_template_string(HTML_TEMPLATE,
                                          message="Invalid Link",
                                          sub_message="No user found with this token.")

        # Update user's subscribed status
        user_email = data[0]["email"]
        patch_url = f"{SUPABASE_URL}?email=eq.{user_email}"
        patch_data = {"subscribed": False}
        patch_resp = requests.patch(patch_url, headers=headers, json=patch_data)
        patch_resp.raise_for_status()

        return render_template_string(HTML_TEMPLATE,
                                      message="Unsubscribed Successfully",
                                      sub_message=f"{user_email} will no longer receive emails.")

    except Exception as e:
        print("Error:", e)
        return render_template_string(HTML_TEMPLATE,
                                      message="Error",
                                      sub_message="Something went wrong. Please try again later.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)