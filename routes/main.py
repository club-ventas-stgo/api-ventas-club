import string
import random
import base64
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash
from PIL import Image
from app import db
from models import Stand

main_bp = Blueprint('main', __name__)


def generar_codigo(length=6):
    chars = string.ascii_uppercase + string.digits
    while True:
        codigo = ''.join(random.choices(chars, k=length))
        if not Stand.query.filter_by(codigo_acceso=codigo).first():
            return codigo


def comprimir_imagen(file_storage, max_size=800):
    img = Image.open(file_storage)
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img.thumbnail((max_size, max_size))
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=75)
    buffer.seek(0)
    b64 = base64.b64encode(buffer.read()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"


@main_bp.route('/')
def index():
    stands = Stand.query.filter_by(activo=True).order_by(Stand.created_at.desc()).all()
    return render_template('index.html', stands=stands)


@main_bp.route('/crear-stand', methods=['POST'])
def crear_stand():
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre del stand es obligatorio.', 'danger')
        return redirect(url_for('main.index'))

    foto = None
    if 'foto' in request.files and request.files['foto'].filename:
        try:
            foto = comprimir_imagen(request.files['foto'])
        except Exception:
            flash('Error al procesar la imagen.', 'danger')
            return redirect(url_for('main.index'))

    codigo = generar_codigo()
    stand = Stand(nombre=nombre, foto=foto, codigo_acceso=codigo)
    db.session.add(stand)
    db.session.commit()

    return render_template('stand_creado.html', stand=stand)
