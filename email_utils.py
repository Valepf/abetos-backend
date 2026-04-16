# C:\Abetos_app\backend\email_utils.py
import os
import base64
import hmac
import hashlib
import time
import json
import smtplib
from email.mime.text import MIMEText

import requests

SECRET = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET") or "dev-secret-change-me"
BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://127.0.0.1:8000")


def _b64(s: bytes) -> str:
    return base64.urlsafe_b64encode(s).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def generate_verify_token(uid: int, email: str, ttl_sec: int = 3600) -> str:
    payload = {"uid": uid, "email": email, "exp": int(time.time()) + int(ttl_sec)}
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    return f"{_b64(data)}.{_b64(sig)}"


def verify_token(token: str) -> dict:
    parts = (token or "").split(".")
    if len(parts) != 2:
        raise ValueError("token malformado")

    data = _unb64(parts[0])
    sig = _unb64(parts[1])

    exp_sig = hmac.new(SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, exp_sig):
        raise ValueError("firma inválida")

    payload = json.loads(data.decode("utf-8"))
    if int(time.time()) > int(payload.get("exp", 0)):
        raise ValueError("token expirado")

    return payload


def generate_verify_link(uid: int, email: str) -> str:
    t = generate_verify_token(uid, email)
    return f"{BACKEND_ORIGIN}/api/auth/verify?token={t}"


def send_verification_email(to_email: str, link: str) -> bool:
    """
    Devuelve True si se intentó enviar (y salió OK), False si no se envió.
    Importante: NO debe romper el flujo de registro.
    """
    require_verif = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
    if not require_verif:
        return False

    to_email = (to_email or "").strip()
    if not to_email:
        return False

    subject = "Verificá tu cuenta"
    html = (
        "<p>Bienvenido/a a Abetos.</p>"
        f"<p>Verificá tu cuenta haciendo click: <a href='{link}'>Confirmar</a></p>"
    )
    text = f"Bienvenido/a a Abetos.\nVerificá tu cuenta: {link}"

    # -----------------------------
    # Opción 1: Resend
    # -----------------------------
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        try:
            resp = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": os.getenv("SMTP_FROM", "Abetos <no-reply@abetos.local>"),
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception:
            # No rompemos el registro; devolvemos False y listo
            return False

    # -----------------------------
    # Opción 2: SMTP (fallback)
    # Soporta SMTP_HOST o SMTP_SERVER
    # -----------------------------
    smtp_host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user

    if not smtp_host or not smtp_user or not smtp_pass or not smtp_from:
        return False

    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, [to_email], msg.as_string())
        return True
    except Exception:
        return False




