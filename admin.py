# Abetos_app/backend/admin.py
from flask import Blueprint, request, jsonify, make_response
from sqlalchemy import func, desc
from db import db
from models import Customer, Transaction
from api import roles_required  # tu decorador de roles

admin_api = Blueprint("admin_api", __name__)

# Tabla de factores: puntos por litro
POINTS_TABLE = {
    "INFINIA": 10,
    "SUPER": 8,
    # agrega más si es necesario
}

def _points_for(product_code: str, liters: float) -> int:
    if liters is None or liters <= 0:
        raise ValueError("Litros inválidos")
    code = (product_code or "").strip().upper()
    factor = POINTS_TABLE.get(code)
    if factor is None:
        raise ValueError("product_code inválido")
    return int(round(liters * factor))

@admin_api.post("/accredit-by-dni")
@roles_required("admin", "clerk")
def accredit_by_dni():
    """
    Body:
    {
      "doc_number": "32123456",
      "product_code": "INFINIA|SUPER|...",
      "liters": 35.0,                  # opcional si mandan amount+unit_price
      "amount": 3000.0,                # opcional
      "unit_price": 1796.0,            # opcional
      "paid_with_app": true|false,
      "payment_method": "efectivo|debito|credito|qr",
      "ticket_number": "A001-000123",
      "note": "texto opcional"
    }
    """
    data = request.get_json(silent=True) or dict(request.form) or {}

    doc_number   = (data.get("doc_number") or "").strip()
    product_code = (data.get("product_code") or "").strip()

    liters      = data.get("liters")
    amount      = data.get("amount")
    unit_price  = data.get("unit_price")

    paid_with_app  = bool(data.get("paid_with_app", False))
    payment_method = data.get("payment_method")
    ticket_number  = data.get("ticket_number")
    note           = data.get("note")

    if not doc_number:
        return jsonify({"error": "doc_number requerido"}), 400
    if not product_code:
        return jsonify({"error": "product_code requerido"}), 400

    # Buscar cliente por DNI
    c = db.session.query(Customer).filter_by(doc_number=doc_number).first()
    if not c:
        return jsonify({"error": "Cliente no encontrado"}), 404

    # Calcular litros si no vinieron, usando amount y unit_price
    def _to_float(x):
        try:
            return float(x) if x is not None and f"{x}".strip() != "" else None
        except Exception:
            return None

    liters = _to_float(liters)
    amount = _to_float(amount)
    unit_price = _to_float(unit_price)

    if (liters is None or liters <= 0) and (amount and unit_price and amount > 0 and unit_price > 0):
        liters = round(amount / unit_price, 4)

    if liters is None or liters <= 0:
        return jsonify({"error": "liters inválido (o amount/unit_price inválidos)"}), 400

    # Calcular puntos
    try:
        earned = _points_for(product_code, liters)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Crear transacción y actualizar saldo del cliente
    tx = Transaction(
        customer_id=c.id,
        type="accrual",
        points=int(earned),
        product_code=product_code,
        liters=float(liters),
        amount=amount,
        unit_price=unit_price,
        paid_with_app=paid_with_app,
        payment_method=payment_method,
        ticket_number=ticket_number,
        note=note,
    )
    c.add_points(earned)

    db.session.add(tx)
    db.session.commit()

    return jsonify({
        "ok": True,
        "customer": {
            "id": c.id,
            "full_name": c.full_name,
            "doc_number": c.doc_number,
            "points_balance": int(c.points_balance or 0),
        },
        "transaction": {
            "id": tx.id,
            "type": tx.type,
            "points": tx.points,
            "product_code": tx.product_code,
            "liters": tx.liters,
            "amount": tx.amount,
            "unit_price": tx.unit_price,
            "created_at": tx.created_at.isoformat(),
            "payment_method": tx.payment_method,
            "ticket_number": tx.ticket_number,
        }
    }), 201
