# C:\Abetos_app\backend\db.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

# Naming convention (útil para migraciones y constraints más predecibles)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)

# Instancia única, usada por toda la app
db = SQLAlchemy(
    metadata=metadata,
    session_options={"expire_on_commit": False},
)