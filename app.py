import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text
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

    CHILE_TZ = ZoneInfo('America/Santiago')

    @app.template_filter('local_time')
    def local_time_filter(dt, fmt='%H:%M'):
        if dt is None:
            return ''
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CHILE_TZ).strftime(fmt)

    @app.template_filter('local_date')
    def local_date_filter(dt, fmt='%Y-%m-%d'):
        if dt is None:
            return ''
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CHILE_TZ).strftime(fmt)

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

    @app.errorhandler(413)
    def too_large(e):
        from flask import flash, redirect, request
        flash('El archivo es demasiado grande (max 16MB).', 'danger')
        return redirect(request.referrer or '/'), 302

    with app.app_context():
        db.create_all()
        # Add missing columns to existing tables (db.create_all doesn't alter existing tables)
        _add_missing_columns(db)

    return app


def _add_missing_columns(db):
    """Add columns that db.create_all() can't add to existing tables."""
    inspector = inspect(db.engine)
    for table_name, model in db.Model.metadata.tables.items():
        if table_name not in inspector.get_table_names():
            continue
        existing_cols = {c['name'] for c in inspector.get_columns(table_name)}
        for col in model.columns:
            if col.name not in existing_cols:
                col_type = col.type.compile(db.engine.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                default = ""
                if col.default is not None and col.default.is_scalar:
                    default = f" DEFAULT {col.default.arg!r}"
                db.session.execute(text(
                    f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} {nullable}{default}'
                ))
                db.session.commit()


app = create_app()
