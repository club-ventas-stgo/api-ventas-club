from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy import func
from app import db
from models import Stand, Producto, Promocion, Venta
from routes.main import comprimir_imagen

stand_bp = Blueprint('stand', __name__, url_prefix='/s')


def get_stand_or_404(codigo):
    stand = Stand.query.filter_by(codigo_acceso=codigo, activo=True).first()
    if not stand:
        abort(404)
    return stand


@stand_bp.route('/<codigo>', methods=['GET', 'POST'])
def dashboard(codigo):
    stand = get_stand_or_404(codigo)

    if request.method == 'POST' and 'inversion' in request.form:
        try:
            stand.inversion = int(request.form.get('inversion', 0))
            db.session.commit()
            flash('Inversion actualizada.', 'success')
        except ValueError:
            flash('El valor de inversion debe ser un numero.', 'danger')
        return redirect(url_for('stand.dashboard', codigo=codigo))

    total_ventas = stand.ventas.count()
    productos_activos = stand.productos.filter_by(activo=True).count()
    ventas_pendientes = stand.ventas.filter_by(estado_entrega='pendiente').count()
    ventas_en_prep = stand.ventas.filter_by(estado_entrega='en_preparacion').count()
    total_recaudado = db.session.query(func.coalesce(func.sum(Venta.total_final), 0)).filter_by(stand_id=stand.id).scalar()
    ganancia_neta = total_recaudado - (stand.inversion or 0)
    return render_template('stand/dashboard.html', stand=stand,
                           total_ventas=total_ventas,
                           productos_activos=productos_activos,
                           ventas_pendientes=ventas_pendientes,
                           ventas_en_prep=ventas_en_prep,
                           total_recaudado=total_recaudado,
                           ganancia_neta=ganancia_neta)


@stand_bp.route('/<codigo>/productos', methods=['GET', 'POST'])
def productos(codigo):
    stand = get_stand_or_404(codigo)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        precio = request.form.get('precio', '0')

        if not nombre:
            flash('El nombre del producto es obligatorio.', 'danger')
            return redirect(url_for('stand.productos', codigo=codigo))

        try:
            precio = int(precio)
        except ValueError:
            flash('El precio debe ser un número entero.', 'danger')
            return redirect(url_for('stand.productos', codigo=codigo))

        foto = None
        if 'foto' in request.files and request.files['foto'].filename:
            try:
                foto = comprimir_imagen(request.files['foto'])
            except Exception:
                flash('Error al procesar la imagen.', 'danger')
                return redirect(url_for('stand.productos', codigo=codigo))

        producto = Producto(stand_id=stand.id, nombre=nombre, precio=precio, foto=foto)
        db.session.add(producto)
        db.session.commit()
        flash(f'Producto "{nombre}" agregado.', 'success')
        return redirect(url_for('stand.productos', codigo=codigo))

    todos = stand.productos.order_by(Producto.activo.desc(), Producto.created_at.desc()).all()
    return render_template('stand/productos.html', stand=stand, productos=todos)


@stand_bp.route('/<codigo>/productos/<int:producto_id>/editar', methods=['POST'])
def editar_producto(codigo, producto_id):
    stand = get_stand_or_404(codigo)
    producto = Producto.query.filter_by(id=producto_id, stand_id=stand.id).first_or_404()

    nombre = request.form.get('nombre', '').strip()
    precio = request.form.get('precio', '0')

    if nombre:
        producto.nombre = nombre
    try:
        producto.precio = int(precio)
    except ValueError:
        flash('El precio debe ser un número entero.', 'danger')
        return redirect(url_for('stand.productos', codigo=codigo))

    if 'foto' in request.files and request.files['foto'].filename:
        try:
            producto.foto = comprimir_imagen(request.files['foto'])
        except Exception:
            flash('Error al procesar la imagen.', 'danger')
            return redirect(url_for('stand.productos', codigo=codigo))

    db.session.commit()
    flash(f'Producto "{producto.nombre}" actualizado.', 'success')
    return redirect(url_for('stand.productos', codigo=codigo))


@stand_bp.route('/<codigo>/productos/<int:producto_id>/toggle', methods=['POST'])
def toggle_producto(codigo, producto_id):
    stand = get_stand_or_404(codigo)
    producto = Producto.query.filter_by(id=producto_id, stand_id=stand.id).first_or_404()
    producto.activo = not producto.activo
    db.session.commit()
    estado = "activado" if producto.activo else "desactivado"
    flash(f'Producto "{producto.nombre}" {estado}.', 'info')
    return redirect(url_for('stand.productos', codigo=codigo))


@stand_bp.route('/<codigo>/promociones', methods=['GET', 'POST'])
def promociones(codigo):
    stand = get_stand_or_404(codigo)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()

        if not nombre:
            flash('El nombre de la promoción es obligatorio.', 'danger')
            return redirect(url_for('stand.promociones', codigo=codigo))

        promo = Promocion(stand_id=stand.id, nombre=nombre, descripcion=descripcion)
        db.session.add(promo)
        db.session.commit()
        flash(f'Promoción "{nombre}" creada.', 'success')
        return redirect(url_for('stand.promociones', codigo=codigo))

    todas = stand.promociones.order_by(Promocion.activa.desc(), Promocion.created_at.desc()).all()
    return render_template('stand/promociones.html', stand=stand, promociones=todas)


@stand_bp.route('/<codigo>/promociones/<int:promo_id>/toggle', methods=['POST'])
def toggle_promocion(codigo, promo_id):
    stand = get_stand_or_404(codigo)
    promo = Promocion.query.filter_by(id=promo_id, stand_id=stand.id).first_or_404()
    promo.activa = not promo.activa
    db.session.commit()
    estado = "activada" if promo.activa else "desactivada"
    flash(f'Promoción "{promo.nombre}" {estado}.', 'info')
    return redirect(url_for('stand.promociones', codigo=codigo))


@stand_bp.route('/<codigo>/promociones/<int:promo_id>/eliminar', methods=['POST'])
def eliminar_promocion(codigo, promo_id):
    stand = get_stand_or_404(codigo)
    promo = Promocion.query.filter_by(id=promo_id, stand_id=stand.id).first_or_404()
    db.session.delete(promo)
    db.session.commit()
    flash(f'Promoción eliminada.', 'info')
    return redirect(url_for('stand.promociones', codigo=codigo))
