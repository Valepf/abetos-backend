# C:\Abetos_app\backend\models.py
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.ext.hybrid import hybrid_property
from db import db

# ------------------------------------------------------
# Users
# ------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="customer", index=True)  # 'admin' | 'clerk' | 'customer'
    is_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relación 1–a–1 con Customer
    customer = db.relationship("Customer", backref="user", uselist=False, lazy=True)

    # helpers de password
    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
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
    phone = db.Column(db.String(40))            # permitir NULL/duplicados si hace falta
    member_number = db.Column(db.String(30), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relación 1–a–N con transactions
    transactions = db.relationship("Transaction", backref="customer", lazy=True)

    @hybrid_property
    def points_balance(self):
        total = 0
        for t in self.transactions or []:
            total += int(t.points or 0)
        return int(total)


# ------------------------------------------------------
# (Opcional) Purchases - tabla mínima para habilitar FK desde Transaction
# ------------------------------------------------------
class Purchase(db.Model):
    __tablename__ = "purchases"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ------------------------------------------------------
# Transactions
# ------------------------------------------------------
class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)

    # tu convención actual
    kind = db.Column(db.String(20), nullable=False)              # 'earn' | 'redeem'
    points = db.Column(db.Integer, nullable=False, default=0)    # ← corregido

    # datos del despacho / operación
    amount_pesos = db.Column(db.Float)                           # $ total (si aplica)
    liters = db.Column(db.Float)                                 # litros
    product_code = db.Column(db.String(50))                      # INFINIA / SUPER / ...
    unit_price = db.Column(db.Float)                             # $ por litro (opcional)
    paid_with_app = db.Column(db.Boolean, default=False)         # (opcional)
    note = db.Column(db.String(200))

    payment_method = db.Column(db.String(30))                    # efectivo | debito | credito | qr
    ticket_number = db.Column(db.String(50))

    # quién operó (admin/clerk)
    operator_user_id = db.Column(db.Integer)

    # relación opcional a Purchase
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ------------------------------------------------------
# Earning Rules
# ------------------------------------------------------
class EarningRule(db.Model):
    __tablename__ = "earning_rules"

    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(50), nullable=False, index=True)
    unit = db.Column(db.String(20), nullable=False)              # 'LITERS' | 'CURRENCY'
    points_per_unit = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ------------------------------------------------------
# Rewards
# ------------------------------------------------------
class Reward(db.Model):
    __tablename__ = "rewards"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    required_points = db.Column(db.Integer, nullable=False)
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    stock = db.Column(db.Integer)  # NULL = ilimitado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
