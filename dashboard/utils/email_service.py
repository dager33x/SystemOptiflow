"""Email-only one-time codes. Failed delivery never creates a usable OTP."""
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import hmac
import html
import logging
import os
from pathlib import Path
import secrets
import smtplib
import ssl
import string

from dotenv import load_dotenv
from dashboard.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        # Resolve configuration from the app, regardless of the launch directory.
        for path in (Path(get_resource_path('.env')), Path(__file__).resolve().parents[3] / '.env'):
            if path.is_file():
                load_dotenv(path, override=False)
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com').strip()
        try:
            self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        except ValueError:
            self.smtp_port = 0
        self.sender_email = os.environ.get('SENDER_EMAIL', '').strip()
        self.sender_password = os.environ.get('SENDER_PASSWORD', '')
        self.smtp_username = os.environ.get('SMTP_USERNAME', self.sender_email).strip()
        self.verification_codes = {}
        self.verified_emails = set()
        self.last_error = ''

    def generate_verification_code(self, length=6):
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    def send_verification_email(self, recipient_email, username):
        return self._send_code(recipient_email, username, reset=False)

    def send_password_reset_email(self, recipient_email, username):
        return self._send_code(recipient_email, username, reset=True)

    def _send_code(self, recipient, username, reset):
        key = f'reset_{recipient}' if reset else recipient
        self.verification_codes.pop(key, None)
        self.last_error = ''
        if (not self.sender_email or self.sender_email == 'your_email@gmail.com' or
                not self.sender_password or self.sender_password == 'your_app_password'):
            self.last_error = ('Email delivery is not configured. Set SENDER_EMAIL and SENDER_PASSWORD '
                               'in the application .env file, then restart. No code was sent.')
            return False, None, False
        if not self.smtp_server or not 1 <= self.smtp_port <= 65535:
            self.last_error = 'Email server settings are invalid. Check SMTP_SERVER and SMTP_PORT.'
            return False, None, False
        code = self.generate_verification_code()
        minutes = 15 if reset else 10
        title = 'Password Reset Request' if reset else 'Email Verification'
        purpose = ('We received a request to reset your Optiflow password.' if reset else
                   'Welcome to Optiflow! Verify your email address to complete registration.')
        try:
            message = MIMEMultipart('alternative')
            message['Subject'] = f'OptiFlow - {title}'
            message['From'] = self.sender_email
            message['To'] = recipient
            text = (f'Hello {username},\n\n{purpose}\n\nYour verification code is: {code}\n'
                    f'This code expires in {minutes} minutes.\n\n'
                    'If you did not request this, please ignore this email.\n\nOptiflow Team')
            body = f'''<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#0f172a;padding:24px;color:#f8fafc">
              <div style="max-width:560px;margin:auto;background:#1e293b;border:1px solid #334155;border-radius:16px;padding:36px">
                <h2 style="color:#3b82f6;text-align:center">Optiflow</h2>
                <h3 style="text-align:center">{title}</h3>
                <p>Hello <strong>{html.escape(username)}</strong>,</p><p>{purpose}</p>
                <div style="background:#0f172a;border:1px solid #3b82f6;border-radius:12px;padding:24px;text-align:center">
                  <p style="color:#94a3b8">VERIFICATION CODE</p>
                  <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#3b82f6">{code}</div>
                </div><p style="text-align:center">This code expires in {minutes} minutes.</p>
                <p style="color:#94a3b8">If you did not request this, please ignore this email.</p>
              </div></body></html>'''
            message.attach(MIMEText(text, 'plain', 'utf-8'))
            message.attach(MIMEText(body, 'html', 'utf-8'))
            context = ssl.create_default_context()
            if self.smtp_port == 465:
                connection = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=15, context=context)
            else:
                connection = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15)
            with connection as server:
                if self.smtp_port != 465:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(self.smtp_username, self.sender_password)
                refused = server.sendmail(self.sender_email, [recipient], message.as_string())
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
        except smtplib.SMTPAuthenticationError:
            self.last_error = 'The email provider rejected the sender credentials. Check the sender account and SMTP/app password. No code was sent.'
        except smtplib.SMTPRecipientsRefused:
            self.last_error = 'The email server rejected this recipient. Check the email address and try again.'
        except (OSError, smtplib.SMTPException, ValueError):
            self.last_error = 'Unable to send the verification email. Check the email server settings and internet connection, then try again.'
        else:
            self.verification_codes[key] = {'code': code, 'expires': datetime.now()+timedelta(minutes=minutes),
                                             'username': username, 'attempts': 0}
            # Keep the legacy tuple contract, without exposing the OTP to callers.
            return True, None, True
        logger.warning('Verification email was not delivered; request rejected')
        return False, None, False

    def _verify(self, key, code):
        stored = self.verification_codes.get(key)
        if stored is None:
            return False, 'No active code found. Request a new email code.'
        if datetime.now() >= stored['expires']:
            del self.verification_codes[key]
            return False, 'The code has expired. Request a new email code.'
        stored['attempts'] += 1
        if not hmac.compare_digest(stored['code'], str(code).strip()):
            if stored['attempts'] >= 5:
                del self.verification_codes[key]
                return False, 'Too many incorrect attempts. Request a new email code.'
            return False, 'Invalid verification code'
        del self.verification_codes[key]
        return True, 'Code verified successfully'

    def verify_code(self, email, code):
        success, message = self._verify(email, code)
        if success:
            self.verified_emails.add(email)
        return success, message

    def verify_reset_code(self, email, code):
        return self._verify(f'reset_{email}', code)

    def is_email_verified(self, email):
        return email in self.verified_emails
