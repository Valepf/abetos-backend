# C:\Abetos_app\backend\seed_demo.py
"""
Seed de datos de demostración:
- Reglas de puntos (EarningRule)
- Recompensas (Reward)
- Cliente demo + transacciones

Seguro para correr varias veces (idempotente).
"""

from datetime import datetime, timedelta

from app import app
from db import db
from models import User, Customer, Transaction, EarningRule, Reward

def upsert_rule(product_code: str, unit: str, ppu: float, is_active: bool = True):
    r = EarningRule.query.filter_by(product_code=product_code).first()
    if r:
        r.unit = unit
        r.points_per_unit = ppu
        r.is_active = is_active
        print(f"↻ Regla actualizada: {product_code} ({unit} -> {ppu})")
    else:
        r = EarningRule(product_code=product_code, unit=unit, points_per_unit=ppu, is_active=is_active)
        db.session.add(r)
        print(f"✓ Regla creada: {product_code} ({unit} -> {ppu})")

def upsert_reward(title: str, required_points: int, days_from: int | None = None,
                  days_to: int | None = None, stock: int | None = None):
    rw = Reward.query.filter_by(title=title).first()
    vf = (datetime.utcnow() + timedelta(days=days_from)) if days_from is not None else None
    vt = (datetime.utcnow() + timedelta(days=days_to)) if days_to is not None else None

    if rw:
        rw.required_points = required_points
        rw.valid_from = vf
        rw.valid_to = vt
        rw.stock = stock
        print(f"↻ Recompensa actualizada: {title} ({required_points} pts)")
    else:
        rw = Reward(
            title=title,
            required_points=required_points,
            valid_from=vf,
            valid_to=vt,
            stock=stock,
        )
        db.session.add(rw)
        print(f"✓ Recompensa creada: {title} ({required_points} pts)")

def ensure_demo_customer():
    """
    Crea un cliente demo con DNI 12345678 para probar Mi Abetos.
    Devuelve (user, customer).
    """
    email = "juan.demo@abetos.test"
    doc = "12345678"
    full_name = "Juan Pérez"

    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email, role="customer", is_verified=True)
        u.set_password("Demo123!")  # contraseña simple para demo
        db.session.add(u)
        db.session.flush()
        print(f"✓ Usuario demo creado: {email} / pass=Demo123!")
    else:
        print(f"↻ Usuario demo ya existe: {email}")

    c = Customer.query.filter_by(user_id=u.id).first()
    if not c:
        c = Customer(
            user_id=u.id,
            full_name=full_name,
            doc_number=doc,
            phone=None,
            member_number="A123456",
        )
        db.session.add(c)
        db.session.flush()
        print(f"✓ Cliente demo creado: {full_name} (DNI {doc})")
    else:
        print(f"↻ Cliente demo ya existe: {full_name} (DNI {doc})")

    return u, c

def compute_points(product_code: str, liters: float | None, amount_pesos: float | None) -> int:
    code = (product_code or "").upper().strip()
    # 1) Buscar regla por LITERS
    if liters and liters > 0:
        r = EarningRule.query.filter_by(product_code=code, unit="LITERS", is_active=True).first()
        if r:
            return int(round(float(r.points_per_unit) * liters))
    # 2) Buscar regla por CURRENCY
    if amount_pesos and amount_pesos > 0:
        r = EarningRule.query.filter_by(product_code=code, unit="CURRENCY", is_active=True).first()
        if r:
            return int(round(float(r.points_per_unit) * amount_pesos))
    # 3) Sin regla: 0
    return 0

def ensure_demo_transactions(customer: Customer):
    """
    Crea algunas transacciones de ejemplo si no hay movimientos.
    """
    has_tx = Transaction.query.filter_by(customer_id=customer.id).first()
    if has_tx:
        print("↻ El cliente demo ya tiene transacciones, no se agregan nuevas.")
        return

    # Simular 3 cargas con productos que sí están en las reglas
    demo_rows = [
        {"product_code": "SUPER",   "liters": 20.0,    "amount_pesos": None,     "note": "Carga SUPER 20L"},
        {"product_code": "INFINIA", "liters": 15.0,    "amount_pesos": None,     "note": "Carga INFINIA 15L"},
        {"product_code": "GNC",     "liters": None,    "amount_pesos": 12000.0,  "note": "Carga GNC $12.000"},
    ]

    for d in demo_rows:
        pts = compute_points(d["product_code"], d["liters"], d["amount_pesos"])
        t = Transaction(
            customer_id=customer.id,
            kind="earn",
            points=pts,
            liters=d["liters"],
            amount_pesos=d["amount_pesos"],
            product_code=d["product_code"],
            note=d["note"],
            operator_user_id=None,
        )
        db.session.add(t)

    db.session.commit()
    print("✓ Transacciones demo creadas para el cliente (según reglas activas).")

def main():
    with app.app_context():
        db.create_all()

        # ---------- Reglas de puntos (coherentes con el front y el admin) ----------
        upsert_rule("INFINIA", "LITERS",   8.0, True)
        upsert_rule("SUPER",   "LITERS",   4.0, True)
        upsert_rule("GNC",     "CURRENCY", 0.5, True)

        # ---------- Recompensas ----------
        upsert_reward("Lavado premium",          200, days_from=0, days_to=60,  stock=50)
        upsert_reward("Café + medialuna",         60, days_from=0, days_to=90,  stock=200)
        upsert_reward("Descuento $2000 tienda",  250, days_from=0, days_to=45,  stock=100)
        upsert_reward("Cambio de aceite 10% OFF",150, days_from=0, days_to=120, stock=None)

        # ---------- Cliente + transacciones demo ----------
        _, customer = ensure_demo_customer()
        ensure_demo_transactions(customer)

        db.session.commit()
        print("✅ Seed demo completo.")

if __name__ == "__main__":
    main()
