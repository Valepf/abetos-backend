# C:\Abetos_app\backend\create_db_now.py
from app import app
from db import db

with app.app_context():
    db.create_all()
    print("✅ Tablas creadas en mi_inventario.db")
