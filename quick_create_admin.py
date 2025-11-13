from app import create_app
from db import db
from models import User
a = create_app()
with a.app_context():
    u = User.query.filter_by(email="admin@abetos.com").first()
    if not u:
        u = User(email="admin@abetos.com", role="admin", is_verified=True, full_name="Admin Abetos")
        u.set_password("admin123")
        db.session.add(u)
        db.session.commit()
        print("admin creado:", u.id)
    else:
        print("admin ya existe:", u.id)
