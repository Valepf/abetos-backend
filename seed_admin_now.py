# C:\Abetos_app\backend\seed_admin_now.py
from app import app
from db import db
from models import User, Customer

ADMIN_EMAIL = "admin@abetos.com"
ADMIN_PASS = "admin123"

with app.app_context():
    # ¿ya existe?
    u = User.query.filter_by(email=ADMIN_EMAIL).first()
    if u:
        print(f"⚠️ Ya existe admin con email {ADMIN_EMAIL} (id={u.id}). Nada que hacer.")
    else:
        u = User(email=ADMIN_EMAIL, role="admin", is_verified=True)
        u.set_password(ADMIN_PASS)  # usa el método del modelo
        db.session.add(u)
        db.session.flush()  # para obtener u.id

        # crear Customer vinculado (por comodidad)
        c = Customer(
            user_id=u.id,
            full_name="Administrador",
            doc_number="00000000",
            phone=None,
            member_number="A000000"
        )
        db.session.add(c)
        db.session.commit()
        print(f"✅ Admin creado: {ADMIN_EMAIL} / {ADMIN_PASS} (user_id={u.id})")
