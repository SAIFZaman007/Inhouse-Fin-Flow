"""
app/core/email.py
==================
Async SMTP email service.
"""
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """
    Send an HTML email via SMTP with STARTTLS.

    Returns True on success, False on any failure (never raises).
    """
    if not settings.smtp_configured:
        logger.warning(
            "SMTP not configured (SMTP_USER/SMTP_PASSWORD missing) — skipping email to %s", to
        )
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.smtp_from_header
    message["To"] = to

    if text_body is None:
        text_body = re.sub(r"<[^>]+>", "", html_body).strip()

    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_TLS,
        )
        logger.info("Email sent → %s | subject: %s", to, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email → %s: %s", to, exc)
        return False


# ─── Typed Email Templates ────────────────────────────────────────────────────

async def send_welcome_email(to: str, name: str, role: str, temp_password: str) -> bool:
    """Welcome email sent when CEO creates a user directly (temp-password flow)."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#1F3864,#2d5be3);padding:36px 48px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">MAKTech Financial Flow</h1>
            <p style="margin:8px 0 0;color:#aac4ff;font-size:13px;">Your account has been created</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 48px;">
            <p style="margin:0 0 6px;font-size:20px;font-weight:600;color:#1a1a2e;">Hi {name} 👋</p>
            <p style="margin:0 0 24px;color:#555;font-size:14px;line-height:1.6;">
              Your <strong>MAKTech Finance</strong> account has been set up by your administrator.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f8f9ff;border-radius:8px;border:1px solid #e0e7ff;margin-bottom:24px;">
              <tr>
                <td style="padding:14px 20px;color:#555;font-size:13px;border-bottom:1px solid #e0e7ff;">Email</td>
                <td style="padding:14px 20px;font-weight:600;font-size:13px;border-bottom:1px solid #e0e7ff;">{to}</td>
              </tr>
              <tr>
                <td style="padding:14px 20px;color:#555;font-size:13px;border-bottom:1px solid #e0e7ff;">Role</td>
                <td style="padding:14px 20px;font-weight:600;font-size:13px;border-bottom:1px solid #e0e7ff;">{role}</td>
              </tr>
              <tr>
                <td style="padding:14px 20px;color:#555;font-size:13px;">Temp Password</td>
                <td style="padding:14px 20px;font-family:monospace;font-weight:700;
                           font-size:15px;color:#e53e3e;letter-spacing:1px;">{temp_password}</td>
              </tr>
            </table>
            <table cellpadding="0" cellspacing="0"
                   style="background:#fff5f5;border-left:4px solid #e53e3e;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:24px;width:100%;">
              <tr>
                <td style="font-size:13px;color:#c53030;">
                  ⚠ Change your password immediately after your first login.
                </td>
              </tr>
            </table>
            <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
            <p style="margin:0;color:#aaa;font-size:12px;">MAKTech Financial Flow &mdash; Finance Management System</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    text = (
        f"Hi {name},\n\n"
        f"Your MAKTech Finance account has been created.\n\n"
        f"Email:         {to}\n"
        f"Role:          {role}\n"
        f"Temp Password: {temp_password}\n\n"
        f"Please change your password immediately after login.\n\n"
        f"MAKTech Financial Flow"
    )
    return await send_email(to, "Welcome to MAKTech — Your Account Details", html, text)


async def send_password_reset_email(to: str, name: str, new_password: str) -> bool:
    """Password reset email sent when CEO resets a user's password."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#1F3864,#2d5be3);padding:36px 48px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">MAKTech Financial Flow</h1>
            <p style="margin:8px 0 0;color:#aac4ff;font-size:13px;">Password Reset</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 48px;">
            <p style="margin:0 0 6px;font-size:20px;font-weight:600;color:#1a1a2e;">Hi {name},</p>
            <p style="margin:0 0 24px;color:#555;font-size:14px;line-height:1.6;">
              Your password has been reset by an administrator.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f8f9ff;border-radius:8px;border:1px solid #e0e7ff;margin-bottom:24px;">
              <tr>
                <td style="padding:14px 20px;color:#555;font-size:13px;">New Password</td>
                <td style="padding:14px 20px;font-family:monospace;font-weight:700;
                           font-size:16px;color:#e53e3e;letter-spacing:1px;">{new_password}</td>
              </tr>
            </table>
            <table cellpadding="0" cellspacing="0"
                   style="background:#fff5f5;border-left:4px solid #e53e3e;padding:12px 16px;border-radius:0 6px 6px 0;width:100%;">
              <tr>
                <td style="font-size:13px;color:#c53030;">
                  ⚠ Please change your password immediately after logging in.
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    text = (
        f"Hi {name},\n\n"
        f"Your password has been reset by an administrator.\n\n"
        f"New Password: {new_password}\n\n"
        f"Please change your password immediately after logging in.\n\n"
        f"MAKTech Financial Flow"
    )
    return await send_email(to, "MAKTech — Password Reset", html, text)


async def send_invitation_email(
    to: str,
    inviter_name: str,
    role_label: str,
    invite_token: str,
    base_url: str,
    app_name: str,
    expire_days: int = 7,
) -> bool:
    """Invitation email sent to new team members."""
    accept_url = (
        f"{base_url.rstrip('/')}/"
        f"api/v1/users/invitations/accept-form?token={invite_token}"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#1F3864,#2d5be3);padding:40px 48px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">{app_name}</h1>
            <p style="margin:8px 0 0;color:#aac4ff;font-size:13px;">Team Invitation</p>
          </td>
        </tr>
        <tr>
          <td style="padding:40px 48px;">
            <p style="margin:0 0 8px;font-size:22px;font-weight:600;color:#1a1a2e;">Hi there 👋</p>
            <p style="margin:0 0 24px;font-size:14px;color:#555;line-height:1.7;">
              <strong style="color:#1F3864;">{inviter_name}</strong> has invited you to join
              <strong>{app_name}</strong> as a
              <strong style="color:#1F3864;">{role_label}</strong>.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 0 28px;">
              <tr>
                <td style="border-radius:7px;background:linear-gradient(135deg,#1F3864,#2d5be3);">
                  <a href="{accept_url}"
                     style="display:inline-block;padding:15px 40px;color:#fff;font-size:15px;
                            font-weight:600;text-decoration:none;border-radius:7px;letter-spacing:0.3px;">
                    Accept Invitation &rarr;
                  </a>
                </td>
              </tr>
            </table>
            <hr style="border:none;border-top:1px solid #eee;margin:0 0 20px;" />
            <p style="margin:0 0 6px;font-size:12px;color:#999;">Or copy this link into your browser:</p>
            <p style="margin:0 0 24px;font-size:11px;color:#2d5be3;word-break:break-all;
                      background:#f0f4ff;padding:12px 14px;border-radius:5px;
                      border-left:3px solid #2d5be3;">{accept_url}</p>
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="background:#fffbeb;border-left:4px solid #f59e0b;
                           padding:12px 16px;border-radius:0 5px 5px 0;">
                  <p style="margin:0;font-size:13px;color:#92400e;">
                    ⏰ <strong>This invitation expires in {expire_days} days.</strong>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f9f9f9;padding:20px 48px;border-top:1px solid #eee;text-align:center;">
            <p style="margin:0;font-size:12px;color:#aaa;">&copy; {app_name}. All rights reserved.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text = (
        f"Hi,\n\n"
        f"{inviter_name} has invited you to join {app_name} as a {role_label}.\n\n"
        f"Accept your invitation:\n{accept_url}\n\n"
        f"This invitation expires in {expire_days} days.\n\n"
        f"{app_name}"
    )
    return await send_email(to, f"You're invited to join {app_name}", html, text)