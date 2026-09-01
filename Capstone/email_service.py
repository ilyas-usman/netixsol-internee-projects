"""Week 7 Day 4 — Email automation for the assigned employee (and client).

Supports both requested transports:
- Gmail API (OAuth / domain-wide-delegated service account)
- SMTP (works with Gmail "App Passwords" or any SMTP server)

If neither is configured, emails are written to EMAIL_LOG_FILE instead of
being sent, so booking/reschedule/cancel never fail just because email
credentials haven't been set up yet — see day4-README.md for real setup.
"""
from __future__ import annotations

import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import day4_config as cfg

_log = logging.getLogger("email_service")

try:
    from google.oauth2 import service_account as _svc_account
    from google.oauth2.credentials import Credentials as _OAuthCredentials
    from googleapiclient.discovery import build as _google_build
except ImportError:
    _svc_account = None
    _OAuthCredentials = None
    _google_build = None


class EmailError(Exception):
    pass


def _build_mime(to_email, subject, text_body, html_body=None, cc=None):
    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    from_display = f"{cfg.SMTP_FROM_NAME} <{cfg.SMTP_FROM_EMAIL}>" if cfg.SMTP_FROM_EMAIL else cfg.SMTP_FROM_NAME
    msg["From"] = from_display
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


class ConsoleEmailProvider:
    """Fallback: logs the email instead of sending it."""

    name = "console"

    def send(self, to_email, subject, body, cc=None, html_body=None):
        with open(cfg.EMAIL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(f"TO: {to_email}\nCC: {cc or ''}\nSUBJECT: {subject}\n\n{body}\n")
        return {"provider": self.name, "logged_to": cfg.EMAIL_LOG_FILE}


class SMTPEmailProvider:
    name = "smtp"

    def send(self, to_email, subject, body, cc=None, html_body=None):
        if not (cfg.SMTP_USER and cfg.SMTP_PASSWORD):
            _log.warning("[EMAIL FALLBACK] SMTP_USER / SMTP_PASSWORD not configured — logging to console file.")
            return ConsoleEmailProvider().send(to_email, subject, body, cc=cc, html_body=html_body)
        msg = _build_mime(to_email, subject, body, html_body=html_body, cc=cc)
        recipients = [to_email] + ([cc] if cc else [])
        try:
            with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=15) as server:
                if cfg.SMTP_USE_TLS:
                    server.starttls()
                server.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
                server.sendmail(cfg.SMTP_FROM_EMAIL or cfg.SMTP_USER, recipients, msg.as_string())
            return {"provider": self.name, "status": "sent"}
        except Exception as exc:
            _log.warning("[EMAIL FALLBACK] SMTP send failed (%s) — logging to console file.", exc)
            res = ConsoleEmailProvider().send(to_email, subject, body, cc=cc, html_body=html_body)
            res["smtp_error"] = str(exc)
            return res


class GmailAPIEmailProvider:
    name = "gmail_api"

    def __init__(self):
        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        if cfg.GMAIL_DELEGATED_USER:
            # Domain-wide-delegated service account (Google Workspace).
            creds = _svc_account.Credentials.from_service_account_file(
                cfg.GMAIL_SERVICE_ACCOUNT_FILE, scopes=scopes
            ).with_subject(cfg.GMAIL_DELEGATED_USER)
        else:
            # Personal @gmail.com via a pre-authorized OAuth user token.
            creds = _OAuthCredentials.from_authorized_user_file(
                cfg.GMAIL_OAUTH_TOKEN_FILE, scopes
            )
        self._service = _google_build("gmail", "v1", credentials=creds, cache_discovery=False)

    def send(self, to_email, subject, body, cc=None, html_body=None):
        msg = _build_mime(to_email, subject, body, html_body=html_body, cc=cc)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            self._service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return {"provider": self.name, "status": "sent"}
        except Exception as exc:
            _log.warning("[EMAIL FALLBACK] Gmail API send failed (%s) — logging to console file.", exc)
            res = ConsoleEmailProvider().send(to_email, subject, body, cc=cc, html_body=html_body)
            res["gmail_error"] = str(exc)
            return res


_provider = None


def get_email_provider():
    global _provider
    if _provider is not None:
        return _provider

    mode = cfg.EMAIL_PROVIDER

    def _try_gmail_api():
        if _google_build is None:
            return None
        try:
            return GmailAPIEmailProvider()
        except Exception:
            return None

    def _try_smtp():
        if cfg.SMTP_USER and cfg.SMTP_PASSWORD:
            return SMTPEmailProvider()
        return None

    if mode == "gmail_api":
        _provider = _try_gmail_api() or ConsoleEmailProvider()
    elif mode == "smtp":
        _provider = _try_smtp() or ConsoleEmailProvider()
    elif mode == "console":
        _provider = ConsoleEmailProvider()
    else:  # auto
        _provider = _try_gmail_api() or _try_smtp() or ConsoleEmailProvider()

    return _provider


def _appointment_body(appointment: dict, heading: str) -> str:
    return (
        f"{heading}\n\n"
        f"Client name : {appointment.get('client_name') or 'N/A'}\n"
        f"Property    : {appointment.get('property_label') or 'N/A'}\n"
        f"Date        : {appointment.get('appt_date')}\n"
        f"Time        : {appointment.get('appt_time')}\n"
        f"Duration    : {appointment.get('duration_minutes')} minutes\n\n"
        f"— Sent automatically by {cfg.COMPANY_NAME} scheduling assistant."
    )


def _appointment_html_body(
    appointment: dict,
    heading: str,
    badge_text: str = "Appointment Update",
    accent_color: str = "#2563eb",
) -> str:
    client_name = appointment.get("client_name") or "N/A"
    property_label = appointment.get("property_label") or "N/A"
    appt_date = appointment.get("appt_date") or "N/A"
    appt_time = appointment.get("appt_time") or "N/A"
    duration = appointment.get("duration_minutes") or 30
    company_name = cfg.COMPANY_NAME

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f4f6f9; padding: 30px 15px;">
    <tr>
      <td align="center">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #e5e7eb;">
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 32px 36px; text-align: left;">
              <span style="display: inline-block; background-color: {accent_color}; color: #ffffff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; padding: 4px 12px; border-radius: 20px; margin-bottom: 12px;">{badge_text}</span>
              <h1 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0; line-height: 1.3;">{company_name}</h1>
            </td>
          </tr>

          <!-- Content Area -->
          <tr>
            <td style="padding: 36px;">
              <p style="color: #334155; font-size: 16px; font-weight: 600; line-height: 1.5; margin: 0 0 24px 0;">{heading}</p>
              
              <!-- Details Card -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0; border-collapse: separate; overflow: hidden;">
                <tr>
                  <td style="padding: 16px 20px; border-bottom: 1px solid #e2e8f0;">
                    <span style="color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Client Name</span>
                    <strong style="color: #0f172a; font-size: 15px; font-weight: 600;">{client_name}</strong>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 16px 20px; border-bottom: 1px solid #e2e8f0;">
                    <span style="color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Property</span>
                    <strong style="color: #0f172a; font-size: 15px; font-weight: 600;">{property_label}</strong>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 16px 20px; border-bottom: 1px solid #e2e8f0;">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                      <tr>
                        <td width="50%" style="vertical-align: top;">
                          <span style="color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Date</span>
                          <strong style="color: #0f172a; font-size: 15px; font-weight: 600;">{appt_date}</strong>
                        </td>
                        <td width="50%" style="vertical-align: top;">
                          <span style="color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Time</span>
                          <strong style="color: {accent_color}; font-size: 15px; font-weight: 600;">{appt_time}</strong>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 16px 20px;">
                    <span style="color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Duration</span>
                    <strong style="color: #0f172a; font-size: 15px; font-weight: 600;">{duration} minutes</strong>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer Banner -->
          <tr>
            <td style="background-color: #f1f5f9; padding: 20px 36px; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="color: #64748b; font-size: 13px; margin: 0;">Sent automatically by <strong>{company_name}</strong> scheduling assistant.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _resolve_employee_email(appointment: dict) -> str:
    email = (appointment or {}).get("employee_email")
    if email:
        return email
    emp_name = (appointment or {}).get("employee_name")
    if emp_name:
        try:
            from appointment_agent import _match_single_employee_name
            for emp in cfg.load_employees():
                if _match_single_employee_name(emp_name, emp):
                    if emp.get("email"):
                        return emp["email"]
        except Exception:
            for emp in cfg.load_employees():
                if emp.get("name") and (emp["name"].lower() in emp_name.lower() or emp_name.lower() in emp["name"].lower()):
                    if emp.get("email"):
                        return emp["email"]
    return cfg.ADMIN_NOTIFICATION_EMAIL or ""



def send_employee_notification(appointment: dict):
    """Task 2: email the assigned employee — meeting time, property, client."""
    provider = get_email_provider()
    to_email = _resolve_employee_email(appointment)
    if not to_email:
        _log.info("[EMAIL SKIPPED] send_employee_notification: no employee_email on file")
        return {"skipped": "no employee_email on file"}
    subject = f"New appointment: {appointment.get('client_name') or 'Client'} — {appointment.get('appt_date')} {appointment.get('appt_time')}"
    text_body = _appointment_body(appointment, "You have a new property viewing appointment.")
    html_body = _appointment_html_body(
        appointment,
        "You have a new property viewing appointment.",
        badge_text="New Appointment",
        accent_color="#2563eb",
    )
    res = provider.send(to_email, subject, text_body, cc=cfg.ADMIN_NOTIFICATION_EMAIL or None, html_body=html_body)
    _log.info("[EMAIL SENT] send_employee_notification to=%s subject=%s result=%s", to_email, subject, res)
    return res


def send_employee_reschedule_notice(appointment: dict, old_date: str, old_time: str):
    provider = get_email_provider()
    to_email = _resolve_employee_email(appointment)
    if not to_email:
        _log.info("[EMAIL SKIPPED] send_employee_reschedule_notice: no employee_email on file")
        return {"skipped": "no employee_email on file"}
    subject = f"Rescheduled: {appointment.get('client_name') or 'Client'} — now {appointment.get('appt_date')} {appointment.get('appt_time')}"
    heading = f"This appointment was rescheduled from {old_date} {old_time}."
    text_body = _appointment_body(appointment, heading)
    html_body = _appointment_html_body(
        appointment,
        heading,
        badge_text="Rescheduled",
        accent_color="#d97706",
    )
    res = provider.send(to_email, subject, text_body, cc=cfg.ADMIN_NOTIFICATION_EMAIL or None, html_body=html_body)
    _log.info("[EMAIL SENT] send_employee_reschedule_notice to=%s subject=%s result=%s", to_email, subject, res)
    return res


def send_employee_cancellation_notice(appointment: dict):
    provider = get_email_provider()
    to_email = _resolve_employee_email(appointment)
    if not to_email:
        _log.info("[EMAIL SKIPPED] send_employee_cancellation_notice: no employee_email on file")
        return {"skipped": "no employee_email on file"}
    subject = f"Cancelled: {appointment.get('client_name') or 'Client'} — was {appointment.get('appt_date')} {appointment.get('appt_time')}"
    heading = "This appointment has been cancelled by the client."
    text_body = _appointment_body(appointment, heading)
    html_body = _appointment_html_body(
        appointment,
        heading,
        badge_text="Cancelled",
        accent_color="#dc2626",
    )
    res = provider.send(to_email, subject, text_body, cc=cfg.ADMIN_NOTIFICATION_EMAIL or None, html_body=html_body)
    _log.info("[EMAIL SENT] send_employee_cancellation_notice to=%s subject=%s result=%s", to_email, subject, res)
    return res


def send_client_confirmation(appointment: dict):
    """Optional: only sent if the client provided an email address."""
    to_email = appointment.get("client_email")
    if not to_email:
        _log.info("[EMAIL SKIPPED] send_client_confirmation: no client_email on file")
        return {"skipped": "no client_email on file"}
    provider = get_email_provider()
    subject = f"Your appointment with {cfg.COMPANY_NAME} is confirmed"
    heading = "Your property viewing appointment is confirmed."
    text_body = _appointment_body(appointment, heading)
    html_body = _appointment_html_body(
        appointment,
        heading,
        badge_text="Confirmed",
        accent_color="#16a34a",
    )
    res = provider.send(to_email, subject, text_body, html_body=html_body)
    _log.info("[EMAIL SENT] send_client_confirmation to=%s subject=%s result=%s", to_email, subject, res)
    return res
