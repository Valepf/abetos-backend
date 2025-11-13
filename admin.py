# C:\Abetos_app\backend\admin.py
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from sqlalchemy import or_

from db import db
from models import Customer, Transaction, EarningRule

admin_api = Blueprint("admin_api", __name__)

# -------------------------
# Helper: solo admin/clerk
# -------------------------
def admin_only(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt() or {}
        role = claims.get("role", "")
        if role not in ("admin", "clerk"):
            return jsonify({"error": "forbidden", "detail": "admin_or_clerk_required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# -------------------------
# GET /api/admin/customers/find?doc_number=...
# -------------------------
@admin_api.get("/customers/find")
@admin_only
def customers_find():
    doc = request.args.get("doc_number") or request.args.get("doc")
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

    data = []
    for c in rows:
        data.append({
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "phone": c.phone,
            "member_number": c.member_number,
            "points_balance": c.points_balance,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return jsonify({"total": total, "items": data})


# -------------------------
# POST /api/admin/accredit-by-dni
# body:
#   doc_number (str) *
#   product_code (str) *
#   liters (float)  |  (amount, unit_price) -> calcula litros
#   paid_with_app, payment_method, ticket_number, note (opc)
# -------------------------
@admin_api.post("/accredit-by-dni")
@admin_only
def accredit_by_dni():
    body = request.get_json(silent=True) or {}
    doc_number   = (body.get("doc_number") or "").strip()
    product_code = (body.get("product_code") or "").strip()
    liters       = body.get("liters")
    amount       = body.get("amount")
    unit_price   = body.get("unit_price")
    paid_with_app = bool(body.get("paid_with_app") or False)
    payment_method = (body.get("payment_method") or "").strip() or None
    ticket_number  = (body.get("ticket_number") or "").strip() or None
    note           = (body.get("note") or "").strip() or None

    if not doc_number or not product_code:
        return jsonify({"error": "bad_request", "detail": "doc_number and product_code required"}), 400

    # buscar cliente
    c = Customer.query.filter_by(doc_number=doc_number).first()
    if not c:
        return jsonify({"error": "not_found", "detail": "customer_not_found"}), 404

    # calcular litros si vino amount + unit_price
    if liters is None:
        if amount is not None and unit_price is not None:
            try:
                a = float(amount)
                p = float(unit_price)
                if a <= 0 or p <= 0:
                    return jsonify({"error": "bad_request", "detail": "invalid amount/unit_price"}), 400
                liters = round(a / p, 4)
            except Exception:
                return jsonify({"error": "bad_request", "detail": "invalid amount/unit_price"}), 400
        else:
            return jsonify({"error": "bad_request", "detail": "liters or (amount + unit_price) required"}), 400

    # buscar regla de puntos
    rule = EarningRule.query.filter_by(product_code=product_code, is_active=True).first()
    if not rule:
        return jsonify({"error": "not_found", "detail": "earning_rule_not_found"}), 404

    # soportamos solo reglas por LITERS aquí
    if (rule.unit or "").upper() != "LITERS":
        return jsonify({"error": "bad_request", "detail": "rule unit not supported for this endpoint"}), 400

    try:
        liters_f = float(liters)
    except Exception:
        return jsonify({"error": "bad_request", "detail": "invalid liters"}), 400
    if liters_f <= 0:
        return jsonify({"error": "bad_request", "detail": "liters must be > 0"}), 400

    # calcular puntos
    points = int(round(liters_f * float(rule.points_per_unit or 0)))

    # IMPORTANTE: usar 'kind', no 'type'
    tx = Transaction(
        customer_id=c.id,
        kind="earn",                    # ← FIX: antes usabas type=...
        points=points,
        product_code=product_code,
        liters=liters_f,
        amount=None if amount is None else float(amount),
        unit_price=None if unit_price is None else float(unit_price),
        paid_with_app=paid_with_app,
        payment_method=payment_method,
        ticket_number=ticket_number,
        note=note,
        # purchase_id: opcional si lo usás
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        "ok": True,
        "transaction": {
            "id": tx.id,
            "customer_id": tx.customer_id,
            "kind": tx.kind,
            "points": tx.points,
            "product_code": tx.product_code,
            "liters": tx.liters,
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
