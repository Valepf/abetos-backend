# C:\Abetos_app\backend\api.py
from functools import wraps
from datetime import datetime, timedelta
import os
import secrets

from flask import Blueprint, request, jsonify
from sqlalchemy import func
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt, create_access_token
)

from db import db
from models import User, Customer, Transaction, EarningRule, Reward, PasswordResetCode
from rules import find_rule, calculate_points


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
        data = dict(request.form) if request.form else {}
    return data or {}


def normalize_doc(doc: str) -> str:
    """Normaliza DNI: deja solo dígitos."""
    doc = (doc or "").strip()
    return "".join(ch for ch in doc if ch.isdigit())


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


def make_reset_code() -> str:
    """Genera un código numérico de 6 dígitos."""
    return f"{secrets.randbelow(1000000):06d}"


def find_user_for_password_reset(data):
    """
    Permite buscar usuario por DNI o email.
    """
    email = (data.get("email") or "").strip().lower()
    doc = normalize_doc(data.get("doc_number") or data.get("dni") or "")

    if email:
        return User.query.filter(func.lower(User.email) == email).first()

    if doc:
        c = Customer.query.filter_by(doc_number=doc).first()
        if c:
            return User.query.get(c.user_id)

    return None


# ----------------- Auth -----------------
@api.post("/auth/register")
def auth_register():
    data = get_json_body()

    email = (data.get("email") or "").strip().lower()
    password = data.get("password")
    full_name = (data.get("full_name") or "").strip()
    doc_number = normalize_doc(data.get("doc_number"))
    phone = (data.get("phone") or "").strip()

    # Seguridad: SIEMPRE customer. No permitimos role desde la app cliente.
    role = "customer"

    if not password or not full_name or not doc_number:
        return jsonify({
            "error": "password, full_name y doc_number son obligatorios"
        }), 400

    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "email ya registrado"}), 409

    if Customer.query.filter_by(doc_number=doc_number).first():
        return jsonify({"error": "doc_number (DNI) ya registrado"}), 409

    u = User(
        full_name=full_name,
        email=email or None,
        role=role,
        is_verified=True,
    )
    u.set_password(password)

    db.session.add(u)
    db.session.flush()

    member_number = (data.get("member_number") or "").strip() or f"A{doc_number[-6:].zfill(6)}"

    c = Customer(
        user_id=u.id,
        full_name=full_name,
        phone=phone or None,
        doc_number=doc_number,
        member_number=member_number,
    )

    db.session.add(c)
    db.session.commit()

    return jsonify({
        "ok": True,
        "message": "Usuario creado. Ya podés iniciar sesión.",
        "user": {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "full_name": u.full_name,
        },
        "customer": {
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "member_number": c.member_number,
        }
    }), 201


@api.post("/auth/login")
def auth_login():
    """
    Acepta email o doc_number.
    """
    data = get_json_body()

    email = (data.get("email") or "").strip().lower()
    doc = normalize_doc(data.get("doc_number"))
    pwd = data.get("password")

    if not pwd:
        return jsonify({
            "error": "missing_fields",
            "hint": "password_required"
        }), 400

    if not email and not doc:
        return jsonify({
            "error": "missing_fields",
            "hint": "email_or_doc_number_required"
        }), 400

    u = None

    if email:
        u = User.query.filter(func.lower(User.email) == email).first()
    else:
        c = Customer.query.filter_by(doc_number=doc).first()
        if c:
            u = User.query.get(c.user_id)

    if not u:
        return jsonify({
            "error": "invalid_credentials",
            "hint": "user_not_found"
        }), 401

    try:
        ok = u.check_password(pwd)
    except Exception:
        ok = False

    if not ok:
        return jsonify({
            "error": "invalid_credentials",
            "hint": "bad_password"
        }), 401

    claims = {
        "role": u.role,
        "email": u.email,
    }

    # Importante: identity como string para que JWT no falle con "Subject must be a string"
    token = create_access_token(identity=str(u.id), additional_claims=claims)

    cust = Customer.query.filter_by(user_id=u.id).first()

    return jsonify({
        "access_token": token,
        "role": u.role,
        "user": {
            "id": u.id,
            "email": u.email,
            "doc_number": cust.doc_number if cust else None,
            "full_name": cust.full_name if cust else u.full_name,
        }
    })


@api.get("/auth/me")
@jwt_required()
def auth_me():
    uid = get_jwt_identity()

    try:
        uid = int(uid)
    except Exception:
        pass

    return jsonify({
        "user_id": uid,
        "claims": {
            "role": get_jwt().get("role"),
            "email": get_jwt().get("email"),
            "exp": get_jwt().get("exp"),
        }
    })


# ----------------- Recuperación de contraseña -----------------
@api.post("/auth/request-password-reset")
def request_password_reset():
    """
    Paso 1:
    El usuario ingresa DNI o email.
    Se genera un código temporal.

    En modo prueba devolvemos el código en dev_code.
    Más adelante se puede enviar por email, SMS o WhatsApp.
    """
    data = get_json_body()
    u = find_user_for_password_reset(data)

    if not u:
        return jsonify({
            "ok": False,
            "error": "user_not_found",
            "message": "No encontramos una cuenta con esos datos."
        }), 404

    code = make_reset_code()
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    reset = PasswordResetCode(
        user_id=u.id,
        code=code,
        expires_at=expires_at,
    )

    db.session.add(reset)
    db.session.commit()

    return jsonify({
        "ok": True,
        "message": "Código de recuperación generado.",
        "expires_in_minutes": 15,

        # Solo para pruebas.
        # En producción esto no debería devolverse,
        # debería enviarse por email, SMS o WhatsApp.
        "dev_code": code,
    }), 200


@api.post("/auth/reset-password")
def reset_password():
    """
    Paso 2:
    El usuario ingresa DNI/email + código + nueva contraseña.
    """
    data = get_json_body()

    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or data.get("password") or ""

    if not code:
        return jsonify({
            "ok": False,
            "error": "missing_code",
            "message": "Ingresá el código de recuperación."
        }), 400

    if len(new_password) < 4:
        return jsonify({
            "ok": False,
            "error": "weak_password",
            "message": "La nueva contraseña debe tener al menos 4 caracteres."
        }), 400

    u = find_user_for_password_reset(data)

    if not u:
        return jsonify({
            "ok": False,
            "error": "user_not_found",
            "message": "No encontramos una cuenta con esos datos."
        }), 404

    reset = (
        PasswordResetCode.query
        .filter_by(user_id=u.id, code=code, used_at=None)
        .order_by(PasswordResetCode.created_at.desc())
        .first()
    )

    if not reset:
        return jsonify({
            "ok": False,
            "error": "invalid_code",
            "message": "El código es inválido o ya fue usado."
        }), 400

    if reset.is_expired:
        return jsonify({
            "ok": False,
            "error": "expired_code",
            "message": "El código venció. Solicitá uno nuevo."
        }), 400

    u.set_password(new_password)
    reset.used_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "ok": True,
        "message": "Contraseña actualizada correctamente. Ya podés iniciar sesión."
    }), 200


# ----------------- Perfil del usuario logueado -----------------
@api.get("/me")
@jwt_required()
def me_profile():
    uid = int(get_jwt_identity())

    u = User.query.get(uid)
    if not u:
        return jsonify({"error": "usuario no encontrado"}), 404

    c = Customer.query.filter_by(user_id=uid).first()
    if c:
        ensure_member_number(c)

    return jsonify({
        "email": u.email,
        "role": u.role,
        "full_name": c.full_name if c else u.full_name,
        "points_balance": c.points_balance if c else 0,
        "customer_id": c.id if c else None,
        "member_number": c.member_number if c else None,
        "doc_number": c.doc_number if c else None,
    })


@api.get("/me/transactions")
@jwt_required()
def me_transactions():
    uid = int(get_jwt_identity())

    c = Customer.query.filter_by(user_id=uid).first()
    if not c:
        return jsonify([])

    txs = (
        Transaction.query
        .filter_by(customer_id=c.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )

    return jsonify([{
        "id": t.id,
        "kind": t.kind,
        "points": t.points,
        "amount_pesos": float(t.amount_pesos) if t.amount_pesos is not None else None,
        "liters": float(t.liters) if t.liters is not None else None,
        "product_code": t.product_code,
        "note": t.note,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in txs])


# ----------------- Rules (semilla) -----------------
@api.post("/rules/seed")
@roles_required("admin")
def seed_rules():
    payload = get_json_body()

    rules_in = payload.get("rules") or [
        {
            "product_code": "NAFTA_SUPER",
            "unit": "LITERS",
            "points_per_unit": 1.0,
            "is_active": True,
        },
        {
            "product_code": "GASOIL",
            "unit": "LITERS",
            "points_per_unit": 1.0,
            "is_active": True,
        },
        {
            "product_code": "GNC",
            "unit": "CURRENCY",
            "points_per_unit": 0.5,
            "is_active": True,
        },
    ]

    created, updated, errors = 0, 0, []

    for r in rules_in:
        try:
            pc = r["product_code"]
            unit = r["unit"]
            ppu = float(r["points_per_unit"])
            act = bool(r.get("is_active", True))
        except Exception:
            errors.append({
                "input": r,
                "error": "faltan campos o tipos inválidos"
            })
            continue

        existing = EarningRule.query.filter_by(product_code=pc).first()

        if existing:
            existing.unit = unit
            existing.points_per_unit = ppu
            existing.is_active = act
            updated += 1
        else:
            db.session.add(EarningRule(
                product_code=pc,
                unit=unit,
                points_per_unit=ppu,
                is_active=act,
            ))
            created += 1

    db.session.commit()

    return jsonify({
        "ok": True,
        "created": created,
        "updated": updated,
        "errors": errors,
    })


# ----------------- Catálogo/Canje -----------------
@api.get("/rewards")
def list_rewards():
    rows = Reward.query.order_by(Reward.required_points.asc()).all()

    return jsonify([{
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "required_points": r.required_points,
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "stock": r.stock,
        "is_active": r.is_active,
    } for r in rows if r.is_active])


@api.post("/me/redeem/<int:reward_id>")
@jwt_required()
def redeem_reward(reward_id):
    uid = int(get_jwt_identity())

    c = Customer.query.filter_by(user_id=uid).first()
    if not c:
        return jsonify({
            "ok": False,
            "error": "Cliente no encontrado"
        }), 404

    r = Reward.query.get(reward_id)
    if not r:
        return jsonify({
            "ok": False,
            "error": "Recompensa no encontrada"
        }), 404

    now = datetime.utcnow()

    if r.valid_from and now < r.valid_from:
        return jsonify({
            "ok": False,
            "error": "Recompensa aún no disponible"
        }), 409

    if r.valid_to and now > r.valid_to:
        return jsonify({
            "ok": False,
            "error": "Recompensa vencida"
        }), 409

    if r.stock is not None and r.stock <= 0:
        return jsonify({
            "ok": False,
            "error": "Sin stock"
        }), 409

    balance = current_balance(c.id)

    if balance < r.required_points:
        return jsonify({
            "ok": False,
            "error": "Puntos insuficientes"
        }), 409

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

    return jsonify({
        "ok": True,
        "new_balance": current_balance(c.id)
    })


# ----------------- Cargas genéricas (por IDs) -----------------
@api.post("/purchases")
@roles_required("admin", "clerk")
def create_purchase():
    data = get_json_body()

    customer_id = data.get("customer_id")
    user_id = data.get("user_id")
    product_code = (data.get("product_code") or "").strip()
    liters = data.get("liters")
    amount_pesos = data.get("amount_pesos")
    note = data.get("note")
    payment_method = data.get("payment_method") or None
    ticket_number = data.get("ticket_number") or None

    c = None

    if customer_id:
        c = Customer.query.get(customer_id)
    elif user_id:
        c = Customer.query.filter_by(user_id=user_id).first()

    if not c:
        return jsonify({
            "ok": False,
            "error": "Cliente no encontrado"
        }), 404

    if not product_code:
        return jsonify({
            "ok": False,
            "error": "product_code es requerido"
        }), 400

    rule = find_rule(product_code)

    if not rule:
        return jsonify({
            "ok": False,
            "error": f"No hay regla activa para {product_code}"
        }), 409

    unit = (getattr(rule, "unit", "") or "").upper()

    liters_f, amount_f = None, None

    if unit == "LITERS":
        try:
            liters_f = float(liters)
        except (TypeError, ValueError):
            liters_f = None

        if not liters_f or liters_f <= 0:
            return jsonify({
                "ok": False,
                "error": "Se requieren 'liters' > 0 para esta regla"
            }), 400

    elif unit == "CURRENCY":
        try:
            amount_f = float(amount_pesos)
        except (TypeError, ValueError):
            amount_f = None

        if not amount_f or amount_f <= 0:
            return jsonify({
                "ok": False,
                "error": "Se requiere 'amount_pesos' > 0 para esta regla"
            }), 400

    points = calculate_points(rule, liters=liters_f, amount_pesos=amount_f)

    try:
        points = int(points)
    except Exception:
        pass

    if not points or points <= 0:
        return jsonify({
            "ok": False,
            "error": "La operación no genera puntos"
        }), 400

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
            "member_number": c.member_number,
        }
    }), 201


# ----------------- Buscar cliente por DNI -----------------
@api.get("/admin/customers/find")
@roles_required("admin", "clerk")
def admin_find_customer():
    doc_number = normalize_doc(request.args.get("doc_number") or request.args.get("dni") or "")

    if not doc_number:
        return jsonify({
            "ok": False,
            "error": "doc_number requerido"
        }), 400

    c = Customer.query.filter_by(doc_number=doc_number).first()

    if not c:
        return jsonify({
            "ok": False,
            "error": "Cliente no encontrado"
        }), 404

    ensure_member_number(c)

    return jsonify({
        "ok": True,
        "customer": {
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "phone": c.phone,
            "member_number": c.member_number,
            "points_balance": current_balance(c.id),
        }
    })


# ----------------- Acreditar puntos por DNI -----------------
@api.post("/admin/accredit-by-dni")
@roles_required("admin", "clerk")
def admin_accredit_by_dni():
    data = get_json_body()

    doc_number = normalize_doc(data.get("doc_number"))
    product_code = (data.get("product_code") or "").strip()
    liters = data.get("liters")
    amount_pesos = data.get("amount_pesos")
    note = data.get("note")
    payment_method = data.get("payment_method") or None
    ticket_number = data.get("ticket_number") or None

    if not doc_number:
        return jsonify({
            "ok": False,
            "error": "doc_number requerido"
        }), 400

    c = Customer.query.filter_by(doc_number=doc_number).first()

    if not c:
        return jsonify({
            "ok": False,
            "error": "Cliente no encontrado"
        }), 404

    if not product_code:
        return jsonify({
            "ok": False,
            "error": "product_code es requerido"
        }), 400

    rule = find_rule(product_code)

    if not rule:
        return jsonify({
            "ok": False,
            "error": f"No hay regla activa para {product_code}"
        }), 409

    unit = (getattr(rule, "unit", "") or "").upper()

    liters_f, amount_f = None, None

    if unit == "LITERS":
        try:
            liters_f = float(liters)
        except (TypeError, ValueError):
            liters_f = None

        if not liters_f or liters_f <= 0:
            return jsonify({
                "ok": False,
                "error": "Se requieren 'liters' > 0 para esta regla"
            }), 400

    elif unit == "CURRENCY":
        try:
            amount_f = float(amount_pesos)
        except (TypeError, ValueError):
            amount_f = None

        if not amount_f or amount_f <= 0:
            return jsonify({
                "ok": False,
                "error": "Se requiere 'amount_pesos' > 0 para esta regla"
            }), 400

    points = calculate_points(rule, liters=liters_f, amount_pesos=amount_f)

    try:
        points = int(points)
    except Exception:
        pass

    if not points or points <= 0:
        return jsonify({
            "ok": False,
            "error": "La operación no genera puntos"
        }), 400

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
            "doc_number": c.doc_number,
            "member_number": c.member_number,
        }
    }), 201