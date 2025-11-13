# C:\Abetos_app\backend\init_db.py
"""
Crea el archivo SQLite y todas las tablas definidas en models.py.
Si el archivo mi_inventario.db no existe, se crea automáticamente.
"""

from app import app
from db import db
import models  # importa los modelos para que SQLAlchemy conozca todas las tablas

def main():
    with app.app_context():
        db.create_all()
        print("✅ Base creada/actualizada: mi_inventario.db")

if __name__ == "__main__":
    main()
