import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ventas_club.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    # Fix Neon/Render postgres:// → postgresql://
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = uri.replace('postgres://', 'postgresql://', 1)

    db.init_app(app)
    migrate.init_app(app, db)

    import models  # noqa: F401 - ensure models are loaded for migrations

    from routes.main import main_bp
    from routes.stand import stand_bp
    from routes.ventas import ventas_bp
    from routes.cocina import cocina_bp
    from routes.registros import registros_bp
    from routes.sesiones import sesiones_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(stand_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(cocina_bp)
    app.register_blueprint(registros_bp)
    app.register_blueprint(sesiones_bp)

    @app.route('/api/health')
    def health():
        return {'status': 'ok'}

    with app.app_context():
        db.create_all()

    return app


app = create_app()
