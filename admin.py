# C:\Abetos_app\backend\admin.py
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy import or_

from db import db
from models import Customer, Transaction
from rules import find_rule, calculate_points

admin_api = Blueprint("admin_api", __name__)

# -------------------------
# Helper: solo admin/clerk
# -------------------------
def admin_only(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt() or {}
        role = (claims.get("role") or "").strip().lower()
        if role not in ("admin", "clerk"):
            return jsonify({"error": "forbidden", "detail": "admin_or_clerk_required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def normalize_doc(doc: str) -> str:
    """Normaliza DNI: deja solo dígitos."""
    doc = (doc or "").strip()
    return "".join(ch for ch in doc if ch.isdigit())


# -------------------------
# GET /api/admin/customers/find?doc_number=...
# -------------------------
@admin_api.get("/customers/find")
@admin_only
def customers_find():
    doc = normalize_doc(request.args.get("doc_number") or request.args.get("doc"))
    if not doc:
        return jsonify({"error": "bad_request", "detail": "doc_number required"}), 400

    c = Customer.query.filter_by(doc_number=doc).first()
    if not c:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "id": c.id,
        "full_name": c.full_name,
        "doc_number": c.doc_number,
        "phone": c.phone,
        "member_number": c.member_number,
        "points_balance": c.points_balance,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    })


# -------------------------
# GET /api/admin/customers/summary
#   params: q, limit, offset
# -------------------------
@admin_api.get("/customers/summary")
@admin_only
def customers_summary():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or request.args.get("size") or 50)
    offset = int(request.args.get("offset") or 0)

    qry = Customer.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                Customer.full_name.ilike(like),
                Customer.doc_number.ilike(like),
                Customer.phone.ilike(like),
                Customer.member_number.ilike(like),
            )
        )

    total = qry.count()
    rows = qry.order_by(Customer.created_at.desc()).limit(limit).offset(offset).all()

    items = []
    for c in rows:
        items.append({
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "phone": c.phone,
            "member_number": c.member_number,
            "points_balance": c.points_balance,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return jsonify({"total": total, "items": items})


# -------------------------
# POST /api/admin/accredit-by-dni
# body:
#   doc_number (str) *
#   product_code (str) *
#   liters (float) OR amount_pesos (float) según regla
#   unit_price (float) opcional (para calcular litros si viene amount_pesos)
#   paid_with_app, payment_method, ticket_number, note (opc)
# -------------------------
@admin_api.post("/accredit-by-dni")
@admin_only
def accredit_by_dni():
    body = request.get_json(silent=True) or {}

    doc_number = normalize_doc(body.get("doc_number"))
    product_code = (body.get("product_code") or "").strip()

    liters = body.get("liters")
    amount_pesos = body.get("amount_pesos", body.get("amount"))  # compat
    unit_price = body.get("unit_price")

    paid_with_app = bool(body.get("paid_with_app") or False)
    payment_method = (body.get("payment_method") or "").strip() or None
    ticket_number = (body.get("ticket_number") or "").strip() or None
    note = (body.get("note") or "").strip() or None

    if not doc_number or not product_code:
        return jsonify({"error": "bad_request", "detail": "doc_number and product_code required"}), 400

    # buscar cliente
    c = Customer.query.filter_by(doc_number=doc_number).first()
    if not c:
        return jsonify({"error": "not_found", "detail": "customer_not_found"}), 404

    # buscar regla activa (usamos helper común)
    rule = find_rule(product_code)
    if not rule:
        return jsonify({"error": "not_found", "detail": "earning_rule_not_found"}), 404

    rule_unit = (rule.unit or "").upper().strip()
    if rule_unit not in ("LITERS", "CURRENCY"):
        return jsonify({"error": "bad_request", "detail": "invalid rule unit"}), 400

    # parseos seguros
    liters_f = None
    amount_f = None
    unit_price_f = None

    if liters is not None:
        try:
            liters_f = float(liters)
        except Exception:
            return jsonify({"error": "bad_request", "detail": "invalid liters"}), 400

    if amount_pesos is not None:
        try:
            amount_f = float(amount_pesos)
        except Exception:
            return jsonify({"error": "bad_request", "detail": "invalid amount_pesos"}), 400

    if unit_price is not None:
        try:
            unit_price_f = float(unit_price)
        except Exception:
            return jsonify({"error": "bad_request", "detail": "invalid unit_price"}), 400

    # completar datos según unidad
    if rule_unit == "LITERS":
        # necesito liters o calcularlos con amount + unit_price
        if liters_f is None:
            if amount_f is not None and unit_price_f is not None and unit_price_f > 0:
                liters_f = round(amount_f / unit_price_f, 4)
            else:
                return jsonify({"error": "bad_request", "detail": "liters or (amount_pesos + unit_price) required"}), 400
        if liters_f <= 0:
            return jsonify({"error": "bad_request", "detail": "liters must be > 0"}), 400

        points = calculate_points(rule, liters=liters_f, rounding="floor", min_points=0)

    else:  # CURRENCY
        if amount_f is None:
            return jsonify({"error": "bad_request", "detail": "amount_pesos required for CURRENCY rule"}), 400
        if amount_f <= 0:
            return jsonify({"error": "bad_request", "detail": "amount_pesos must be > 0"}), 400

        # si mandan unit_price, calculo litros solo para guardar el dato
        if liters_f is None and unit_price_f is not None and unit_price_f > 0:
            liters_f = round(amount_f / unit_price_f, 4)

        points = calculate_points(rule, amount_pesos=amount_f, rounding="floor", min_points=0)

    if not points or points <= 0:
        return jsonify({"error": "bad_request", "detail": "calculated points must be > 0"}), 400

    # quién operó
    operator_id = get_jwt_identity()
    try:
        operator_id = int(operator_id) if operator_id is not None else None
    except Exception:
        operator_id = None

    tx = Transaction(
        customer_id=c.id,
        kind="earn",
        points=int(points),
        product_code=product_code,
        liters=liters_f,
        amount_pesos=amount_f,
        unit_price=unit_price_f,
        paid_with_app=paid_with_app,
        payment_method=payment_method,
        ticket_number=ticket_number,
        note=note,
        operator_user_id=operator_id,
    )

    try:
        db.session.add(tx)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "server_error", "detail": "db_commit_failed"}), 500

    return jsonify({
        "ok": True,
        "transaction": {
            "id": tx.id,
            "customer_id": tx.customer_id,
            "kind": tx.kind,
            "points": tx.points,
            "product_code": tx.product_code,
            "liters": tx.liters,
            "amount_pesos": tx.amount_pesos,
            "unit_price": tx.unit_price,
            "operator_user_id": tx.operator_user_id,
            "payment_method": tx.payment_method,
            "ticket_number": tx.ticket_number,
            "note": tx.note,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        },
        "customer": {
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "points_balance": c.points_balance,
        }
    })