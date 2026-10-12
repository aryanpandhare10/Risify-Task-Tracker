"""
Email reminders for expiring licenses, sent over plain SMTP (e.g. a Gmail /
Google Workspace or Outlook / Microsoft 365 mailbox with an app password), so
no paid email service is needed.

Optional: if the SMTP_* secrets aren't set, reminders are shown on the portal
only and no email is attempted. Reminders go out when someone opens the
dashboard (Streamlit has no background scheduler), at most once per license
per expiry date.
"""
import smtplib
from email.message import EmailMessage

import streamlit as st

from db import claim_license_reminder, release_license_reminder
import utils

DEFAULT_REMINDER_TO = "aryaan.pandhare@risify.ai"


def _smtp_config():
    try:
        secrets = st.secrets
        if not (secrets.get("SMTP_HOST") and secrets.get("SMTP_USER") and secrets.get("SMTP_PASSWORD")):
            return None
        return {
            "host": secrets["SMTP_HOST"],
            "port": int(secrets.get("SMTP_PORT", 587)),
            "user": secrets["SMTP_USER"],
            "password": secrets["SMTP_PASSWORD"],
            "sender": secrets.get("SMTP_FROM", secrets["SMTP_USER"]),
            "to": secrets.get("LICENSE_REMINDER_TO", DEFAULT_REMINDER_TO),
        }
    except Exception:
        return None


def email_enabled() -> bool:
    return _smtp_config() is not None


def _send(cfg: dict, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["to"]
    msg.set_content(body)
    if cfg["port"] == 465:
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        server.starttls()
    with server:
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)


def send_license_reminders(licenses: list) -> None:
    """Email one reminder per license that is expired or expiring within
    LICENSE_REMINDER_DAYS and hasn't been reminded for its current expiry date."""
    cfg = _smtp_config()
    if cfg is None:
        return

    for lic in licenses:
        if utils.license_category(lic) == "active":
            continue
        if lic.get("reminder_sent_for") == lic["expiry_date"]:
            continue
        if not claim_license_reminder(lic["id"], lic["expiry_date"]):
            continue  # another session already sent it

        days = utils.license_days_left(lic)
        when = f"expired {-days} day(s) ago" if days < 0 else (
            "expires today" if days == 0 else f"expires in {days} day(s)"
        )
        label = lic["name"] + (f" ({lic['vendor']})" if lic.get("vendor") else "")
        body = (
            f"License reminder from the Risify Task Tracker:\n\n"
            f"  {label}\n"
            f"  Expiry date: {lic['expiry_date']} — {when}\n"
        )
        if lic.get("notes"):
            body += f"  Notes: {lic['notes']}\n"
        body += "\nUpdate the expiry date on the dashboard once it has been renewed.\n"

        try:
            _send(cfg, f"License {when}: {label}", body)
        except Exception as e:
            release_license_reminder(lic["id"])
            st.toast(f"Couldn't send license reminder email: {e}", icon="⚠️")
