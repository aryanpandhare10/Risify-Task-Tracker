"""
Email reminders for digital-asset invoices due within a week, sent over plain
SMTP (e.g. a Gmail / Google Workspace or Outlook / Microsoft 365 mailbox with
an app password), so no paid email service is needed.

Optional: if the SMTP_* secrets aren't set, reminders are shown on the portal
only and no email is attempted. Reminders go out when someone opens the
dashboard (Streamlit has no background scheduler), at most once per item per
due date.
"""
import smtplib
from email.message import EmailMessage

import streamlit as st

from db import claim_asset_reminder, release_asset_reminder
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
            # LICENSE_REMINDER_TO is the older name for this setting; still honoured.
            "to": secrets.get("PAYMENT_REMINDER_TO")
            or secrets.get("LICENSE_REMINDER_TO")
            or DEFAULT_REMINDER_TO,
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


def send_payment_reminders(assets: list) -> None:
    """Email one reminder per item that is overdue or due within
    ASSET_REMINDER_DAYS and hasn't been reminded for its current due date."""
    cfg = _smtp_config()
    if cfg is None:
        return

    for a in assets:
        if utils.asset_status(a) == "upcoming":
            continue
        if a.get("reminder_sent_for") == a["due_date"]:
            continue
        if not claim_asset_reminder(a["id"], a["due_date"]):
            continue  # another session already sent it

        when = utils.due_when(utils.asset_days_left(a))
        label = utils.asset_label(a)
        body = (
            f"Payment reminder from the Risify Task Tracker:\n\n"
            f"  Service type:   {utils.service_type_label(a)}\n"
            f"  Entity:         {a['entity']}\n"
            f"  Owner:          {(a.get('owner') or {}).get('full_name') or 'Unassigned'}\n"
            f"  Billing cycle:  {utils.BILLING_CYCLE_LABELS.get(a['billing_cycle'], a['billing_cycle'])}\n"
            f"  Invoice amount: {float(a.get('invoice_amount') or 0):,.2f}\n"
            f"  Due date:       {a['due_date']} ({when})\n"
            "\nOnce paid, use \"Mark paid\" on the dashboard to roll it to the next due date.\n"
        )

        try:
            _send(cfg, f"Invoice {when}: {label}", body)
        except Exception as e:
            release_asset_reminder(a["id"])
            st.toast(f"Couldn't send payment reminder email: {e}", icon="⚠️")
