# C:\Abetos_app\backend\seed.py
from app import create_app
from db import db
from models import User, Customer, EarningRule, Reward


ADMIN_EMAIL = "admin@abetos.local"
ADMIN_PASS = "Admin123"
ADMIN_DNI = "00000000"

CLERK_EMAIL = "clerk@abetos.local"
CLERK_PASS = "Clerk123"
CLERK_DNI = "11111111"


def upsert_user(email: str, password: str, role: str, full_name: str, dni: str):
    email = (email or "").strip().lower()
    dni = "".join(ch for ch in (dni or "").strip() if ch.isdigit())

    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email, role=role, is_verified=True, full_name=full_name)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()
    else:
        u.role = role
        u.full_name = full_name

    c = Customer.query.filter_by(user_id=u.id).first()
    if not c:
        c = Customer(
            user_id=u.id,
            full_name=full_name,
            doc_number=dni,
            phone=None,
            member_number=f"A{dni[-6:].zfill(6)}",
        )
        db.session.add(c)
    else:
        c.full_name = full_name
        c.doc_number = dni

    return u, c


def upsert_rule(product_code: str, unit: str, points_per_unit: float, active: bool = True):
    product_code = (product_code or "").strip()
    unit = (unit or "").strip().upper()

    r = EarningRule.query.filter_by(product_code=product_code).first()
    if not r:
        r = EarningRule(product_code=product_code, unit=unit, points_per_unit=float(points_per_unit), is_active=active)
        db.session.add(r)
    else:
        r.unit = unit
        r.points_per_unit = float(points_per_unit)
        r.is_active = active
    return r


def ensure_rewards():
    # Si ya existen rewards, no toca nada
    if Reward.query.count() > 0:
        return

    db.session.add_all([
        Reward(title="Café", description="Un café en la tienda", required_points=200, stock=None, is_active=True),
        Reward(title="Lavado", description="Lavado básico", required_points=600, stock=None, is_active=True),
        Reward(title="Descuento $1000", description="Descuento en carga", required_points=1200, stock=None, is_active=True),
    ])


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        upsert_user(
            email=ADMIN_EMAIL,
            password=ADMIN_PASS,
            role="admin",
            full_name="Administrador",
            dni=ADMIN_DNI,
        )
        upsert_user(
            email=CLERK_EMAIL,
            password=CLERK_PASS,
            role="clerk",
            full_name="Operador",
            dni=CLERK_DNI,
        )

        # Reglas de ejemplo (ajustalas a tu estación)
        upsert_rule("NAFTA_SUPER", "LITERS", 1.0, True)      # 1 punto por litro
        upsert_rule("INFINIA", "LITERS", 1.5, True)          # 1.5 puntos por litro
        upsert_rule("GNC", "CURRENCY", 0.01, True)           # 0.01 punto por peso (ejemplo)

        ensure_rewards()

        db.session.commit()
        print("✅ Seed listo.")
        print(f"   Admin:  {ADMIN_EMAIL} / {ADMIN_PASS}  (DNI {ADMIN_DNI})")
        print(f"   Clerk:  {CLERK_EMAIL} / {CLERK_PASS}  (DNI {CLERK_DNI})")
        print("   Reglas: NAFTA_SUPER, INFINIA, GNC")
        print("   Rewards: Café, Lavado, Descuento")


if __name__ == "__main__":
    main()