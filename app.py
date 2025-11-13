# C:\Abetos_app\backend\app.py
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from db import db
from api import api as api_bp
from admin import admin_api as admin_bp

def create_app():
    app = Flask(__name__)

    # ---------- CONFIG ----------
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///mi_inventario.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"),
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "dev-jwt-secret"),
        JWT_TOKEN_LOCATION=["headers"],
        JWT_HEADER_TYPE="Bearer",
        JSON_SORT_KEYS=False,
    )

    # ---------- EXTENSIONES ----------
    db.init_app(app)
    jwt = JWTManager(app)

    # ---------- CORS ----------
    origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    CORS(
        app,
        resources={
            r"/api/*":   {"origins": origins},
            r"/health":  {"origins": origins},
        },
        supports_credentials=False,  # usás Bearer, no cookies
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    app.url_map.strict_slashes = False

    # ---------- BLUEPRINTS ----------
    app.register_blueprint(api_bp,   url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    # ---------- MODELOS / DB ----------
    with app.app_context():
        import models  # asegura que los modelos se registren
        db.create_all()  # Nota: create_all no hace ALTER; para nuevas columnas, usar migración/ALTER

    # ---------- SALUD ----------
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    # ---------- HANDLERS DE ERRORES (JSON) ----------
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(400)
    def bad_request(_e):
        return jsonify({"error": "Bad request"}), 400

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "Server error"}), 500

    # ---------- JWT CALLBACKS ----------
    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": "Invalid token", "detail": reason}), 401

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": "Missing token", "detail": reason}), 401

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({"error": "Token expired"}), 401

    return app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
