import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

log = logging.getLogger(__name__)

WHAT = {
    "register": ("verify your email address", "Verify your email"),
    "reset": ("reset your password", "Reset your password"),
    "email_change": ("confirm your new email address", "Confirm your new email"),
}


def _shell(body_html):
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;padding:28px;color:#1c1f1d">'
        '<div style="font-weight:700;font-size:18px;letter-spacing:-.01em;color:#1f5d4c;margin-bottom:22px">Vecta</div>'
        f"{body_html}"
        '<div style="margin-top:28px;font-size:12px;color:#6b726d">You are receiving this because of activity on your Vecta account.</div></div>'
    )


def send(to, subject, text, html=None):
    try:
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
        if html:
            msg.attach_alternative(html, "text/html")
        return msg.send() == 1
    except Exception:  # never let a mail outage break the request or reveal whether an account exists
        log.exception("Could not send email to %s", to)
        return False


def send_code(to, code, purpose, name=""):
    action, title = WHAT[purpose]
    minutes = settings.CODE_TTL_MINUTES
    hi = f"Hi {name}," if name else "Hi,"
    text = (f"{hi}\n\nUse this code to {action}. Your code is {code}\n\n"
            f"It expires in {minutes} minutes and works once. If you did not ask for it, ignore this email: "
            "nobody can use it without access to your inbox.\n\n- Vecta\n")
    html = _shell(
        f'<h1 style="font-size:20px;margin:0 0 10px">{escape(title)}</h1><p style="margin:0 0 18px;line-height:1.5">{escape(hi)} use this code to {escape(action)}.</p>'
        f'<div style="font-size:34px;letter-spacing:.35em;font-weight:700;padding:16px 18px;background:#f1f3f1;border-radius:8px;display:inline-block">{code}</div>'
        f'<p style="margin:18px 0 0;color:#4d5550;line-height:1.5">It expires in {minutes} minutes and works once. If you did not ask for it, you can ignore this email.</p>'
    )
    return send(to, f"{code} is your Vecta verification code", text, html)


def send_notice(to, subject, message):
    text = f"{message}\n\nIf this was not you, reset your password straight away and tell HR.\n\n- Vecta\n"
    html = _shell(f'<h1 style="font-size:20px;margin:0 0 10px">{escape(subject)}</h1><p style="line-height:1.55">{escape(message)}</p>'
                  '<p style="color:#4d5550;line-height:1.55">If this was not you, reset your password straight away and tell HR.</p>')
    return send(to, subject, text, html)
