import json
import os
import urllib.error
import urllib.request

from flask import current_app, url_for

from app.db.models import TierThreeRequest, User
from app.services.auth import Auth

RESEND_URL = 'https://api.resend.com/emails'
FROM_ADDRESS = 'Stat Line <no-reply@stat-line.app>'


def notify_tier3_interest(request: TierThreeRequest) -> None:
    """Stub -- will send mail via the email service once it exists. Logs for now."""
    current_app.logger.info(f"Tier 3 interest: {request.org_name} <{request.contact_email}>")


def send_email(to: str, subject: str, html: str, headers: dict | None = None) -> bool:
    """Send one email through Resend. Logs and returns False on failure -- never raises,
    so a mail outage can't break the request that triggered it."""
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key:
        current_app.logger.warning(f"RESEND_API_KEY not set; email to {to} not sent")
        return False
    req = urllib.request.Request(
        RESEND_URL,
        data=json.dumps({'from': FROM_ADDRESS, 'to': [to], 'subject': subject, 'html': html,
                         **({'headers': headers} if headers else {})}).encode(),
        # Cloudflare in front of Resend 403s urllib's default User-Agent
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
                 'User-Agent': 'stat-line/1.0'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        current_app.logger.error(f"Resend rejected email to {to}: {e.code} {e.read().decode(errors='replace')}")
        return False
    except Exception:
        current_app.logger.exception(f"Resend failed for {to}")
        return False


def send_verification_email(user: User) -> bool:
    """Email the user a signed, expiring link that marks their address verified."""
    base = current_app.config.get('APP_BASE_URL') or ''
    link = base + url_for('auth.verify_email', token=Auth.verification_token(user.email))
    html = (f'<p>Hi {user.first_name},</p>'
            f'<p><a href="{link}">Verify your email address</a> to finish setting up your Stat Line account. '
            f'This link expires in 24 hours.</p>')
    return send_email(user.email, 'Verify your Stat Line email', html)


def send_password_reset_email(user: User, code: str) -> bool:
    """Email the user their one-time password-reset code."""
    html = (f'<p>Hi {user.first_name},</p>'
            f'<p>Your Stat Line password reset code is <strong style="font-size:20px;letter-spacing:2px">{code}</strong>. '
            f'It expires in 15 minutes. If you did not request this, you can ignore this email.</p>')
    return send_email(user.email, 'Your Stat Line password reset code', html)


def send_newsletter_email(user: User, subject: str, html: str) -> bool:
    """Send one newsletter with the user's own one-click unsubscribe link (footer + RFC 8058 headers)."""
    base = current_app.config.get('APP_BASE_URL') or ''
    unsub = f"{base}/unsubscribe/{Auth.unsubscribe_token(user.email)}"
    footer = (f'<hr><p style="font-size:12px;color:#666">You are receiving this because you opted in. '
              f'<a href="{unsub}">Unsubscribe</a><br>{os.environ.get("NEWSLETTER_ADDRESS", "")}</p>')
    return send_email(user.email, subject, html + footer, headers={
        'List-Unsubscribe': f'<{unsub}>',
        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    })
