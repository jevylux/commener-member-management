#!/usr/bin/env python3
"""
Quick email test - minimal version for rapid debugging.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Edit these values
SMTP_SERVER = 'securemail.aplus.net'
SMTP_PORT = 465
SMTP_USER = 'marc@durbach.com'
SMTP_PASSWORD = 'XJ!s9TeQZ32BcPQu@k'
FROM_EMAIL = 'marc@durbach.com'
TO_EMAIL = 'marc@durbach.com'  # <-- CHANGE THIS to your email

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
