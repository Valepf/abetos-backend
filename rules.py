# C:\Abetos_app\backend\rules.py
from math import floor, ceil
from typing import Optional

from models import EarningRule


def find_rule(product_code: str) -> Optional[EarningRule]:
    """
    Devuelve la regla activa más reciente para un product_code.
    """
    pc = (product_code or "").strip()
    if not pc:
        return None

    return (
        EarningRule.query
        .filter_by(product_code=pc, is_active=True)
        .order_by(EarningRule.id.desc())
        .first()
    )


def _to_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def calculate_points(
    rule: EarningRule,
    liters=None,
    amount_pesos=None,
    rounding: str = "floor",      # "floor" | "round" | "ceil"
    min_points: int = 0           # 0 = sin mínimo; 1 = al menos 1 punto si genera
) -> int:
    """
    Calcula puntos según la regla.
    - LITERS: usa liters
    - CURRENCY: usa amount_pesos

    rounding:
      - floor: siempre hacia abajo (default, como tu versión)
      - round: redondeo normal
      - ceil: siempre hacia arriba

    min_points:
      - si > 0, aplica mínimo cuando el cálculo da > 0 pero menor al mínimo
    """
    if not rule:
        return 0

    unit = (rule.unit or "").strip().upper()
    ppu = _to_float(rule.points_per_unit) or 0.0

    if ppu <= 0:
        return 0

    base = None
    if unit == "LITERS":
        base = _to_float(liters)
    elif unit == "CURRENCY":
        base = _to_float(amount_pesos)
    else:
        return 0

    if base is None or base <= 0:
        return 0

    raw = base * ppu

    if rounding == "ceil":
        points = int(ceil(raw))
    elif rounding == "round":
        points = int(round(raw))
    else:
        points = int(floor(raw))

    if points <= 0:
        return 0

    if min_points and points < int(min_points):
        return int(min_points)

    return int(points)