#!/usr/bin/env python3
"""
Quick email test - minimal version for rapid debugging.
"""

import smtplib
import ssl
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# Load configuration from environment variables
SMTP_SERVER = os.getenv('SMTP_SERVER', 'securemail.aplus.net')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
FROM_EMAIL = os.getenv('FROM_EMAIL')
TO_EMAIL = os.getenv('FROM_EMAIL')  # For testing, send to yourself

def quick_test():
    print(f"Testing email to {TO_EMAIL}...")
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL
        msg['Subject'] = 'Quick Test - ComEner Email'
        
        body = "This is a quick test email.\n\nIf you see this, SMTP is working!"
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ctx) as server:
            print(f"Connected to {SMTP_SERVER}...")
            server.login(SMTP_USER, SMTP_PASSWORD)
            print("Login successful...")
            server.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
            print("Email sent!")
        
        print(f"\n✅ SUCCESS! Check {TO_EMAIL}")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        return False

if __name__ == '__main__':
    quick_test()
