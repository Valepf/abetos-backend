# C:\Abetos_app\backend\seed_rules.py
# Crea/actualiza reglas de acumulación

from app import create_app
from db import db
from models import EarningRule

# product_code, unit, points_per_unit, is_active
DEFAULT_RULES = [
    ("INFINIA", "LITERS",   8.0, True),   # 8 pts por litro
    ("SUPER",   "LITERS",   4.0, True),   # 4 pts por litro
    ("GNC",     "CURRENCY", 0.5, True),   # 0.5 pt por peso ($)
    # Podés sumar más:
    # ("INFINIA_DIESEL", "LITERS", 8.0, True),
    # ("ULTRADIESEL",    "LITERS", 4.0, True),
]

def upsert_rule(code: str, unit: str, ppu: float, active: bool) -> bool:
    r = EarningRule.query.filter_by(product_code=code).first()
    if r:
        r.unit = unit
        r.points_per_unit = ppu
        r.is_active = active
        return False
    db.session.add(EarningRule(
        product_code=code,
        unit=unit,
        points_per_unit=ppu,
        is_active=active,
    ))
    return True

def main():
    app = create_app()
    with app.app_context():
        created, updated = 0, 0
        for code, unit, ppu, active in DEFAULT_RULES:
            is_new = upsert_rule(code, unit, ppu, active)
            if is_new:
                created += 1
            else:
                updated += 1
        db.session.commit()
        print(f"✔ Reglas OK. Creadas: {created} | Actualizadas: {updated}")
        for code, unit, ppu, active in DEFAULT_RULES:
            print(f" - {code:<12} | {unit:<8} | {ppu} pts/u | activo={active}")

if __name__ == "__main__":
    main()
