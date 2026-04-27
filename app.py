import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

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
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            db_info = {}
            for t in tables:
                cols = [c['name'] for c in inspector.get_columns(t)]
                db_info[t] = cols
            return {'status': 'ok', 'tables': db_info}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    @app.errorhandler(413)
    def too_large(e):
        from flask import flash, redirect, request
        flash('El archivo es demasiado grande (max 16MB).', 'danger')
        return redirect(request.referrer or '/'), 302

    @app.errorhandler(500)
    def internal_error(e):
        import logging
        logging.exception('Internal Server Error: %s', e)
        db.session.rollback()
        return render_template('error.html', error_code=500,
                               error_msg='Ocurrió un error interno. Por favor vuelve atrás e intenta de nuevo.'), 500

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', error_code=404,
                               error_msg='La página que buscas no existe.'), 404

    with app.app_context():
        db.create_all()
        # Log created tables for debugging
        try:
            insp = inspect(db.engine)
            tables = insp.get_table_names()
            logging.info(f'DB tables after create_all: {tables}')
            for t in ('sesiones_venta', 'sesion_integrantes', 'integrantes', 'ventas'):
                if t in tables:
                    cols = [c['name'] for c in insp.get_columns(t)]
                    logging.info(f'  {t} columns: {cols}')
                else:
                    logging.warning(f'  TABLE MISSING: {t}')
        except Exception as e:
            logging.warning(f'Could not inspect DB: {e}')

        # Add missing columns to existing tables (db.create_all doesn't alter existing tables)
        _add_missing_columns(db)
        # Migrate en_preparacion -> pendiente (state removed)
        try:
            db.session.execute(text(
                "UPDATE ventas SET estado_entrega='pendiente' WHERE estado_entrega='en_preparacion'"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    return app


def _add_missing_columns(db):
    """Add columns that db.create_all() can't add to existing tables."""
    import logging
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    for table_name, model in db.Model.metadata.tables.items():
        if table_name not in table_names:
            continue
        existing_cols = {c['name'] for c in inspector.get_columns(table_name)}
        for col in model.columns:
            if col.name not in existing_cols:
                try:
                    col_type = col.type.compile(db.engine.dialect)
                    nullable = "NULL" if col.nullable else "NOT NULL"
                    default = ""
                    if col.default is not None and col.default.is_scalar:
                        val = col.default.arg
                        if isinstance(val, bool):
                            default = f" DEFAULT {'true' if val else 'false'}"
                        elif isinstance(val, str):
                            safe_val = val.replace("'", "''")
                            default = f" DEFAULT '{safe_val}'"
                        elif isinstance(val, (int, float)):
                            default = f" DEFAULT {val}"
                    sql = f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} {nullable}{default}'
                    logging.info(f'Adding missing column: {sql}')
                    db.session.execute(text(sql))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logging.warning(f'Could not add column {table_name}.{col.name}: {e}')


app = create_app()
