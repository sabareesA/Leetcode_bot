import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

# Schedule times (24-hour format)
DAILY_QUESTION_TIME = "09:00"  # 9 AM - Daily question
REMINDER_TIME = "20:00"        # 8 PM - Reminder
WEEKLY_SUMMARY_TIME = "21:00"  # 9 PM Sunday - Weekly summary
TIMEZONE = "Asia/Kolkata"      # Change to your timezone
