# C:\Abetos_app\backend\email_utils.py
import os
import base64
import hmac
import hashlib
import time
import json
import requests
import smtplib
from email.mime.text import MIMEText

SECRET = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET") or "dev-secret-change-me"
BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://127.0.0.1:8000")

def _b64(s: bytes) -> str:
    return base64.urlsafe_b64encode(s).decode().rstrip("=")

def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def generate_verify_token(uid: int, email: str, ttl_sec=3600) -> str:
    payload = {"uid": uid, "email": email, "exp": int(time.time()) + ttl_sec}
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), data, hashlib.sha256).digest()
    return f"{_b64(data)}.{_b64(sig)}"

def verify_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("token malformado")
    data = _unb64(parts[0])
    sig = _unb64(parts[1])
    exp_sig = hmac.new(SECRET.encode(), data, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, exp_sig):
        raise ValueError("firma inválida")
    payload = json.loads(data.decode())
    if int(time.time()) > int(payload.get("exp", 0)):
        raise ValueError("token expirado")
    return payload

def generate_verify_link(uid: int, email: str) -> str:
    t = generate_verify_token(uid, email)
    return f"{BACKEND_ORIGIN}/api/auth/verify?token={t}"

def send_verification_email(to_email: str, link: str):
    # Opción Resend
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={
                "from": "Abetos <no-reply@abetos.local>",
                "to": [to_email],
                "subject": "Verificá tu cuenta",
                "html": f"<p>Bienvenido/a a Abetos.</p><p>Verificá tu cuenta haciendo click: <a href='{link}'>Confirmar</a></p>",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return

    # Fallback SMTP
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not smtp_server or not smtp_user or not smtp_pass:
        # sin configuración de email: no rompemos el flujo
        return

    msg = MIMEText(f"Bienvenido/a a Abetos.\nVerificá tu cuenta: {link}", "plain", "utf-8")
    msg["Subject"] = "Verificá tu cuenta"
    msg["From"] = smtp_user
    msg["To"] = to_email

    with smtplib.SMTP(smtp_server, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.sendmail(smtp_user, [to_email], msg.as_string())
