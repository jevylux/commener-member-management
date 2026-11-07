import smtplib
import ssl
import zipfile
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

# Email configuration for sending bills
EMAIL_CONFIG = {
    'SMTP_SERVER': os.getenv('SMTP_SERVER', 'securemail.aplus.net'),
    'SMTP_PORT': int(os.getenv('SMTP_PORT', '465')),
    'SMTP_USER': os.getenv('SMTP_USER'),
    'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD'),
    'FROM_EMAIL': os.getenv('FROM_EMAIL'),
    'FROM_NAME': os.getenv('FROM_NAME', 'Communauté Energétique')
}


def send_bill_email(member_email, member_name, is_resend=False):
    """
    Send a bill via email to a member.
    
    Args:
        member_email: Recipient email address
        member_name: Member full name

        is_resend: Whether this is a resend
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not member_email:
        return False, "No email address on file"
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['FROM_NAME']} <{EMAIL_CONFIG['FROM_EMAIL']}>"
        msg['To'] = member_email
        
        subject_prefix = "RESEND: " if is_resend else ""
        msg['Subject'] = f"{subject_prefix}Communauté Energétique - Bill Q1, Year 2025"
        
        # Email body in 3 languages
        body = f"""Dear {member_name},

Please find attached your bill for Quarter 1, Year 2025.

If you have any questions, please contact us.

Best regards,
Communauté Energétique

---

Cher(e) {member_name},

Veuillez trouver ci-joint votre facture pour le Trimestre 1, Year 2025.

En cas de questions, n'hésitez pas à nous contacter.

Cordialement,
Communauté Energétique

---

Léif {member_name},

Am Annex fannt Dir Är Rechnung fir d'Quartal 1, Year 2025.

Bei Froen kontaktéiert eis w.e.g.

Mat beschte Gréiss,
Communauté Energétique
"""
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Attach bill file
        if os.path.exists('/Users/marcdurbach/Development/python/ComEner-data-management/app/data/databills/bill_Q1_2025.pdf'):
            filename = os.path.basename(bill_path)
            with open(bill_path, 'rb') as f:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(f.read())
                encoders.encode_base64(attachment)
                attachment.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(attachment)
        else:
            return False, f"Bill file not found: {bill_path}"
        
        # Send email
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT'], context=ctx) as server:
            server.login(EMAIL_CONFIG['SMTP_USER'], EMAIL_CONFIG['SMTP_PASSWORD'])
            server.sendmail(EMAIL_CONFIG['FROM_EMAIL'], member_email, msg.as_string())
        
        return True, f"Email sent successfully to {member_email}"
        
    except Exception as e:
        return False, f"Error sending email: {str(e)}"


# Add generate_ce_forms script path

send_bill_email('marc@durbach.com§', member_name,)