# C:\Abetos_app\backend\rules.py
from math import floor
from models import EarningRule

def find_rule(product_code: str):
    if not product_code:
        return None
    return EarningRule.query.filter_by(product_code=product_code, is_active=True)\
                            .order_by(EarningRule.id.desc()).first()

def calculate_points(rule: EarningRule, liters=None, amount_pesos=None) -> int:
    if not rule:
        return 0
    unit = (rule.unit or "").upper()
    ppu = float(rule.points_per_unit or 0.0)

    if unit == "LITERS":
        if liters is None: 
            return 0
        return int(floor(float(liters) * ppu))
    elif unit == "CURRENCY":
        if amount_pesos is None:
            return 0
        return int(floor(float(amount_pesos) * ppu))
    return 0
