# C:\Abetos_app\backend\api.py
from functools import wraps
from datetime import datetime
import os

from flask import Blueprint, request, jsonify
from sqlalchemy import func
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt, create_access_token
)

from db import db
from models import User, Customer, Transaction, EarningRule, Reward
from rules import find_rule, calculate_points
from email_utils import generate_verify_link, verify_token, send_verification_email

api = Blueprint("api", __name__)

# ----------------- Health (para /api/health) -----------------
@api.get("/health")
def api_health():
    return jsonify(ok=True), 200


# ----------------- Helpers -----------------
def current_balance(customer_id: int) -> int:
    return int(
        db.session.query(func.coalesce(func.sum(Transaction.points), 0))
        .filter(Transaction.customer_id == customer_id)
        .scalar() or 0
    )

def ensure_member_number(customer: Customer) -> None:
    if not customer.member_number:
        customer.member_number = f"31.{600000 + customer.id:06d}"
        db.session.commit()

def get_json_body():
    """Acepta JSON o x-www-form-urlencoded; evita 415 del frontend."""
    data = request.get_json(silent=True)
    if data is None:
        # fallback a form-encoded
        data = dict(request.form) if request.form else {}
    return data or {}

def roles_required(*roles):
    """Exige JWT y rol permitido."""
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorated(*args, **kwargs):
            claims = get_jwt()
            user_role = (claims.get("role") or "").lower()
            if user_role not in {r.lower() for r in roles}:
                return jsonify({
                    "error": "forbidden",
                    "message": "No tenés permisos para esta acción.",
                    "allowed_roles": list(roles),
                }), 403
            return fn(*args, **kwargs)
        return decorated
    return wrapper


# ----------------- Auth -----------------
@api.post("/auth/register")
def auth_register():
    data = get_json_body()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")
    full_name = (data.get("full_name") or "").strip()
    doc_number = (data.get("doc_number") or "").strip()
    phone = (data.get("phone") or "").strip()
    role = (data.get("role") or "customer").lower()

    if not email or not password or not full_name or not doc_number:
        return jsonify({"error": "email, password, full_name y doc_number son obligatorios"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email ya registrado"}), 409

    if Customer.query.filter_by(doc_number=doc_number).first():
        return jsonify({"error": "doc_number (DNI) ya registrado"}), 409

    u = User(email=email, role=role, is_verified=False)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()

    member_number = data.get("member_number") or f"A{doc_number[-6:].zfill(6)}"
    c = Customer(
        user_id=u.id,
        full_name=full_name,
        phone=phone or None,
        doc_number=doc_number,
        member_number=member_number,
    )
    db.session.add(c)
    db.session.commit()

    # Envío de verificación (opcional)
    try:
        link = generate_verify_link(u.id, u.email)
        send_verification_email(u.email, link)
        return jsonify({
            "ok": True,
            "message": "Usuario creado. Te enviamos un email para activar tu cuenta.",
            "user": {"id": u.id, "email": u.email, "role": u.role},
            "customer": {
                "id": c.id, "full_name": c.full_name,
                "doc_number": c.doc_number, "member_number": c.member_number
            }
        }), 201
    except Exception:
        return jsonify({
            "ok": True,
            "warn": "Usuario creado, pero no se pudo enviar el email de verificación.",
            "user": {"id": u.id, "email": u.email, "role": u.role},
            "customer": {
                "id": c.id, "full_name": c.full_name,
                "doc_number": c.doc_number, "member_number": c.member_number
            }
        }), 201


@api.post("/auth/login")
def auth_login():
    """
    Parche: acepta email o doc_number; búsqueda de email case-insensitive;
    errores con 'hint' para depurar credenciales.
    """
    data = get_json_body()
    email = (data.get("email") or "").strip().lower()
    doc   = (data.get("doc_number") or "").strip()
    pwd   = data.get("password")

    if not pwd:
        return jsonify({"error": "missing_fields", "hint": "password_required"}), 400
    if not email and not doc:
        return jsonify({"error": "missing_fields", "hint": "email_or_doc_number_required"}), 400

    # Buscar usuario
    u = None
    if email:
        # Email case-insensitive
        u = User.query.filter(func.lower(User.email) == email).first()
    else:
        c = Customer.query.filter_by(doc_number=doc).first()
        if c:
            u = User.query.get(c.user_id)

    if not u:
        return jsonify({"error": "invalid_credentials", "hint": "user_not_found"}), 401

    # Verificar contraseña (hash)
    try:
        ok = u.check_password(pwd)
    except Exception:
        ok = False
    if not ok:
        return jsonify({"error": "invalid_credentials", "hint": "bad_password"}), 401

    # ¿Requerir verificación de email?
    require_verif = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
    if require_verif and not getattr(u, "is_verified", False):
        return jsonify({
            "error": "Cuenta no verificada. Revisá tu email o pedí reenvío.",
            "needs_verification": True
        }), 403

    claims = {"role": u.role, "email": u.email}
    token = create_access_token(identity=str(u.id), additional_claims=claims)

    # Devolvemos info útil para el front
    cust = Customer.query.filter_by(user_id=u.id).first()
    return jsonify({
        "access_token": token,
        "role": u.role,
        "user": {
            "id": u.id,
            "email": u.email,
            "doc_number": cust.doc_number if cust else None,
            "full_name": cust.full_name if cust else None,
        }
    })


@api.get("/auth/me")
@jwt_required()
def auth_me():
    return jsonify({
        "user_id": get_jwt_identity(),
        "claims": {
            "role": get_jwt().get("role"),
            "email": get_jwt().get("email"),
            "exp": get_jwt().get("exp"),
        }
    })


@api.get("/auth/verify")
def auth_verify():
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token requerido"}), 400
    try:
        data = verify_token(token)
        uid = int(data["uid"])
        email = (data["email"] or "").lower()
    except Exception:
        return jsonify({"error": "token inválido o expirado"}), 400

    u = User.query.get(uid)
    if not u or u.email.lower() != email:
        return jsonify({"error": "usuario no encontrado"}), 404

    if not getattr(u, "is_verified", False):
        u.is_verified = True
        u.email_verified_at = datetime.utcnow()
        db.session.commit()

    return jsonify({"ok": True, "message": "Cuenta verificada. Ya podés iniciar sesión."})


@api.post("/auth/resend-verification")
def resend_verification():
    data = get_json_body()
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email requerido"}), 400

    u = User.query.filter_by(email=email).first()
    if not u:
        return jsonify({"ok": True})

    if getattr(u, "is_verified", False):
        return jsonify({"ok": True, "message": "La cuenta ya está verificada."})

    link = generate_verify_link(u.id, u.email)
    try:
        send_verification_email(u.email, link)
        return jsonify({"ok": True, "message": "Email de verificación reenviado."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------- Perfil del usuario logueado -----------------
@api.get("/me")
@jwt_required()
def me_profile():
    uid = int(get_jwt_identity())
    u = User.query.get(uid)
    if not u:
        return jsonify({'error': 'usuario no encontrado'}), 404

    c = Customer.query.filter_by(user_id=uid).first()
    if c:
        ensure_member_number(c)

    return jsonify({
        'email': u.email,
        'role': u.role,
        'full_name': (c.full_name if c else None),
        'points_balance': (c.points_balance if c else 0),
        'customer_id': (c.id if c else None),
        'member_number': (c.member_number if c else None),
        'doc_number': (c.doc_number if c else None),
    })


@api.get("/me/transactions")
@jwt_required()
def me_transactions():
    uid = int(get_jwt_identity())
    c = Customer.query.filter_by(user_id=uid).first()
    if not c:
        return jsonify([])

    txs = (Transaction.query
           .filter_by(customer_id=c.id)
           .order_by(Transaction.created_at.desc())
           .all())
    return jsonify([{
        'id': t.id,
        'kind': t.kind,
        'points': t.points,
        'amount_pesos': float(t.amount_pesos) if t.amount_pesos is not None else None,
        'liters': float(t.liters) if t.liters is not None else None,
        'product_code': t.product_code,
        'note': t.note,
        'created_at': t.created_at.isoformat()
    } for t in txs])


# ----------------- Rules (semilla) -----------------
@api.post("/rules/seed")
@roles_required('admin')
def seed_rules():
    payload = get_json_body()
    rules_in = (payload.get("rules") or [
        {"product_code": "NAFTA_SUPER", "unit": "LITERS",   "points_per_unit": 1.0, "is_active": True},
        {"product_code": "GASOIL",      "unit": "LITERS",   "points_per_unit": 1.0, "is_active": True},
        {"product_code": "GNC",         "unit": "CURRENCY", "points_per_unit": 0.5, "is_active": True},
    ])

    created, updated, errors = 0, 0, []
    for r in rules_in:
        try:
            pc   = r["product_code"]
            unit = r["unit"]
            ppu  = float(r["points_per_unit"])
            act  = bool(r.get("is_active", True))
        except Exception:
            errors.append({"input": r, "error": "faltan campos o tipos inválidos"})
            continue

        existing = EarningRule.query.filter_by(product_code=pc).first()
        if existing:
            existing.unit = unit
            existing.points_per_unit = ppu
            existing.is_active = act
            updated += 1
        else:
            db.session.add(EarningRule(product_code=pc, unit=unit, points_per_unit=ppu, is_active=act))
            created += 1

    db.session.commit()
    return jsonify({"ok": True, "created": created, "updated": updated, "errors": errors})


# ----------------- Catálogo/Canje -----------------
@api.get("/rewards")
def list_rewards():
    rows = Reward.query.order_by(Reward.required_points.asc()).all()
    return jsonify([{
        "id": r.id,
        "title": r.title,
        "required_points": r.required_points,
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "stock": r.stock
    } for r in rows])


@api.post("/me/redeem/<int:reward_id>")
@jwt_required()
def redeem_reward(reward_id):
    uid = int(get_jwt_identity())
    c = Customer.query.filter_by(user_id=uid).first()
    if not c:
        return jsonify({"ok": False, "error": "Cliente no encontrado"}), 404

    r = Reward.query.get(reward_id)
    if not r:
        return jsonify({"ok": False, "error": "Recompensa no encontrada"}), 404

    now = datetime.utcnow()
    if r.valid_from and now < r.valid_from:
        return jsonify({"ok": False, "error": "Recompensa aún no disponible"}), 409
    if r.valid_to and now > r.valid_to:
        return jsonify({"ok": False, "error": "Recompensa vencida"}), 409

    if r.stock is not None and r.stock <= 0:
        return jsonify({"ok": False, "error": "Sin stock"}), 409

    balance = current_balance(c.id)
    if balance < r.required_points:
        return jsonify({"ok": False, "error": "Puntos insuficientes"}), 409

    tx = Transaction(
        customer_id=c.id,
        kind="redeem",
        points=-int(r.required_points),
        amount_pesos=None,
        liters=None,
        product_code=f"REWARD:{r.id}",
        note=f"Canje '{r.title}'",
        operator_user_id=None,
    )
    db.session.add(tx)
    if r.stock is not None:
        r.stock -= 1
    db.session.commit()

    return jsonify({"ok": True, "new_balance": current_balance(c.id)})


# ----------------- Cargas genéricas (por IDs) -----------------
@api.post("/purchases")
@roles_required('admin', 'clerk')
def create_purchase():
    # Esta ruta queda para flujos por ID; la carga por DNI está en admin.py
    data = get_json_body()
    customer_id = data.get("customer_id")
    user_id = data.get("user_id")
    product_code = (data.get("product_code") or "").strip()
    liters = data.get("liters")
    amount_pesos = data.get("amount_pesos")
    note = data.get("note")
    payment_method = (data.get("payment_method") or None)
    ticket_number = (data.get("ticket_number") or None)

    # buscar cliente
    c = None
    if customer_id:
        c = Customer.query.get(customer_id)
    elif user_id:
        c = Customer.query.filter_by(user_id=user_id).first()
    if not c:
        return jsonify({"ok": False, "error": "Cliente no encontrado"}), 404

    if not product_code:
        return jsonify({"ok": False, "error": "product_code es requerido"}), 400

    rule = find_rule(product_code)
    if not rule:
        return jsonify({"ok": False, "error": f"No hay regla activa para {product_code}"}), 409

    unit = (getattr(rule, "unit", "") or "").upper()
    liters_f, amount_f = None, None

    if unit == "LITERS":
        try:
            liters_f = float(liters)
        except (TypeError, ValueError):
            liters_f = None
        if not liters_f or liters_f <= 0:
            return jsonify({"ok": False, "error": "Se requieren 'liters' > 0 para esta regla"}), 400

    elif unit == "CURRENCY":
        try:
            amount_f = float(amount_pesos)
        except (TypeError, ValueError):
            amount_f = None
        if not amount_f or amount_f <= 0:
            return jsonify({"ok": False, "error": "Se requiere 'amount_pesos' > 0 para esta regla"}), 400

    points = calculate_points(rule, liters=liters_f, amount_pesos=amount_f)
    try:
        points = int(points)
    except Exception:
        pass

    if not points or points <= 0:
        return jsonify({"ok": False, "error": "La operación no genera puntos"}), 400

    operator_uid = int(get_jwt_identity())

    tx = Transaction(
        customer_id=c.id,
        kind="earn",
        points=int(points),
        amount_pesos=amount_f,
        liters=liters_f,
        product_code=product_code,
        note=note,
        payment_method=payment_method,
        ticket_number=ticket_number,
        operator_user_id=operator_uid,
    )
    db.session.add(tx)
    db.session.commit()

    ensure_member_number(c)
    balance = current_balance(c.id)

    return jsonify({
        "ok": True,
        "transaction_id": tx.id,
        "points_awarded": int(points),
        "new_balance": int(balance),
        "customer": {
            "id": c.id,
            "full_name": c.full_name,
            "member_number": c.member_number
        }
    }), 201
