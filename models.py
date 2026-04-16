# C:\Abetos_app\backend\models.py
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import CheckConstraint, UniqueConstraint, func, select
from db import db


# ------------------------------------------------------
# Users
# ------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"

    ROLE_ADMIN = "admin"
    ROLE_CLERK = "clerk"
    ROLE_CUSTOMER = "customer"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(db.String(120))

    # Si en algún momento querés permitir registro solo con DNI,
    # email debería poder ser NULL. En SQLite/Postgres múltiples NULL no rompen UNIQUE.
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)

    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default=ROLE_CUSTOMER, index=True)  # admin | clerk | customer

    is_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relación 1–a–1 con Customer
    customer = db.relationship("Customer", back_populates="user", uselist=False, lazy=True)

    # Transacciones operadas (admin/clerk)
    operated_transactions = db.relationship(
        "Transaction",
        back_populates="operator",
        foreign_keys="Transaction.operator_user_id",
        lazy=True,
    )

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


# ------------------------------------------------------
# Customers
# ------------------------------------------------------
class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    full_name = db.Column(db.String(120), nullable=False)
    doc_number = db.Column(db.String(20), unique=True, nullable=False, index=True)  # DNI
    phone = db.Column(db.String(40))
    member_number = db.Column(db.String(30), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="customer", lazy=True)

    transactions = db.relationship("Transaction", back_populates="customer", lazy=True)
    redemptions = db.relationship("Redemption", back_populates="customer", lazy=True)

    @hybrid_property
    def points_balance(self) -> int:
        # IMPORTANTE: para que esto funcione, guardá redeem como puntos NEGATIVOS.
        return int(sum((t.points or 0) for t in (self.transactions or [])))

    @points_balance.expression
    def points_balance(cls):
        # Permite calcular saldo en SQL (más eficiente)
        return (
            select(func.coalesce(func.sum(Transaction.points), 0))
            .where(Transaction.customer_id == cls.id)
            .scalar_subquery()
        )


# ------------------------------------------------------
# Purchases (opcional, si querés atar a un ticket/operación)
# ------------------------------------------------------
class Purchase(db.Model):
    __tablename__ = "purchases"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ------------------------------------------------------
# Transactions (earn / redeem)
# ------------------------------------------------------
class Transaction(db.Model):
    __tablename__ = "transactions"

    KIND_EARN = "earn"
    KIND_REDEEM = "redeem"

    __table_args__ = (
        CheckConstraint("kind IN ('earn','redeem')", name="ck_transactions_kind"),
    )

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    customer = db.relationship("Customer", back_populates="transactions", lazy=True)

    kind = db.Column(db.String(20), nullable=False, default=KIND_EARN)
    points = db.Column(db.Integer, nullable=False, default=0)  # earn: + / redeem: -

    # datos del despacho / operación
    amount_pesos = db.Column(db.Float)        # $ total (si aplica)
    liters = db.Column(db.Float)              # litros o m3 (si aplica)
    product_code = db.Column(db.String(50))   # INFINIA / SUPER / GNC / ...
    unit_price = db.Column(db.Float)          # $ por unidad (opcional)

    paid_with_app = db.Column(db.Boolean, default=False)
    note = db.Column(db.String(200))

    payment_method = db.Column(db.String(30))  # efectivo | debito | credito | qr
    ticket_number = db.Column(db.String(50))

    # ✅ nullable=True porque canjes pueden no tener operador
    operator_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    operator = db.relationship("User", back_populates="operated_transactions", lazy=True)

    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=True)
    purchase = db.relationship("Purchase", lazy=True)

    # Si querés vincular el redeem con un reward específico
    reward_id = db.Column(db.Integer, db.ForeignKey("rewards.id"), nullable=True, index=True)
    reward = db.relationship("Reward", lazy=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ------------------------------------------------------
# Earning Rules
# ------------------------------------------------------
class EarningRule(db.Model):
    __tablename__ = "earning_rules"

    UNIT_LITERS = "LITERS"
    UNIT_CURRENCY = "CURRENCY"

    # no podemos hacer "unique solo si active" fácil en SQLite,
    # pero sí evitamos duplicados exactos:
    __table_args__ = (
        UniqueConstraint("product_code", "unit", "created_at", name="uq_rule_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(50), nullable=False, index=True)
    unit = db.Column(db.String(20), nullable=False)  # LITERS | CURRENCY
    points_per_unit = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ------------------------------------------------------
# Rewards
# ------------------------------------------------------
class Reward(db.Model):
    __tablename__ = "rewards"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300))
    required_points = db.Column(db.Integer, nullable=False)

    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)

    stock = db.Column(db.Integer)  # NULL = ilimitado
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    redemptions = db.relationship("Redemption", back_populates="reward", lazy=True)


# ------------------------------------------------------
# Redemptions (canjes)
# ------------------------------------------------------
class Redemption(db.Model):
    __tablename__ = "redemptions"

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_redemptions_status"),
    )

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    reward_id = db.Column(db.Integer, db.ForeignKey("rewards.id"), nullable=False, index=True)

    # puntos consumidos (normalmente == reward.required_points)
    points_spent = db.Column(db.Integer, nullable=False)

    # código de canje (para mostrárselo al cliente / validar en caja)
    code = db.Column(db.String(30), unique=True, index=True)

    status = db.Column(db.String(20), default=STATUS_PENDING, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    customer = db.relationship("Customer", back_populates="redemptions", lazy=True)
    reward = db.relationship("Reward", back_populates="redemptions", lazy=True)