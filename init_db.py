"""
Crea la base y todas las tablas definidas en models.py.

- Usa la misma config del backend (SQLALCHEMY_DATABASE_URI).
- Muestra qué URI está usando y dónde queda el archivo si es SQLite.
"""

import os
from urllib.parse import urlparse

from app import create_app
from db import db
import models  # asegura que SQLAlchemy conozca todas las tablas


def _sqlite_path_from_uri(uri: str) -> str | None:
    if not uri or not uri.startswith("sqlite:///"):
        return None
    # sqlite:///archivo.db -> archivo.db (relativo al directorio actual)
    return uri.replace("sqlite:///", "", 1)


def main():
    app = create_app()
    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI")
        db.create_all()

        print("✅ Base creada/actualizada.")
        print(f"   SQLALCHEMY_DATABASE_URI = {uri}")

        sqlite_path = _sqlite_path_from_uri(uri or "")
        if sqlite_path:
            abs_path = os.path.abspath(sqlite_path)
            print(f"   SQLite file: {abs_path}")


if __name__ == "__main__":
    main()