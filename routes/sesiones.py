from datetime import date, datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from app import db
from models import SesionVenta, SesionIntegrante, Integrante, Venta
from routes.stand import get_stand_or_404

sesiones_bp = Blueprint('sesiones', __name__, url_prefix='/s')


@sesiones_bp.route('/<codigo>/sesiones')
def lista(codigo):
    stand = get_stand_or_404(codigo)
    sesiones = stand.sesiones.order_by(SesionVenta.fecha.desc()).all()
    return render_template('sesiones/lista.html', stand=stand, sesiones=sesiones, today=date.today().isoformat())


@sesiones_bp.route('/<codigo>/sesiones/nueva', methods=['POST'])
def nueva(codigo):
    stand = get_stand_or_404(codigo)
    fecha_str = request.form.get('fecha', '')
    nombre = request.form.get('nombre', '').strip()

    try:
        fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except ValueError:
        fecha = date.today()

    sesion = SesionVenta(
        stand_id=stand.id,
        fecha=fecha,
        nombre=nombre or None,
        estado='programada'
    )
    db.session.add(sesion)
    db.session.commit()
    flash('Sesion creada.', 'success')
    return redirect(url_for('sesiones.detalle', codigo=codigo, sesion_id=sesion.id))


@sesiones_bp.route('/<codigo>/sesiones/<int:sesion_id>')
def detalle(codigo, sesion_id):
    stand = get_stand_or_404(codigo)
    sesion = SesionVenta.query.filter_by(id=sesion_id, stand_id=stand.id).first_or_404()
    ventas = sesion.ventas.order_by(Venta.created_at.desc()).all()
    integrantes_disponibles = stand.integrantes.filter_by(activo=True).order_by(Integrante.nombre).all()

    total_ventas = len(ventas)
    total_recaudado = sum(v.total_final for v in ventas)
    total_pagado = sum(v.monto_pagado or 0 for v in ventas)

    return render_template('sesiones/detalle.html', stand=stand, sesion=sesion,
                           ventas=ventas, integrantes_disponibles=integrantes_disponibles,
                           total_ventas=total_ventas, total_recaudado=total_recaudado,
                           total_pagado=total_pagado)


@sesiones_bp.route('/<codigo>/sesiones/<int:sesion_id>/estado', methods=['POST'])
def cambiar_estado(codigo, sesion_id):
    stand = get_stand_or_404(codigo)
    sesion = SesionVenta.query.filter_by(id=sesion_id, stand_id=stand.id).first_or_404()
    nuevo_estado = request.form.get('estado')

    if nuevo_estado in ('programada', 'abierta', 'cerrada'):
        sesion.estado = nuevo_estado
        db.session.commit()
        flash(f'Sesion {nuevo_estado}.', 'success')

    return redirect(url_for('sesiones.detalle', codigo=codigo, sesion_id=sesion.id))


@sesiones_bp.route('/<codigo>/sesiones/<int:sesion_id>/nuevo-integrante', methods=['POST'])
def nuevo_integrante(codigo, sesion_id):
    stand = get_stand_or_404(codigo)
    sesion = SesionVenta.query.filter_by(id=sesion_id, stand_id=stand.id).first_or_404()

    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip()

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('sesiones.detalle', codigo=codigo, sesion_id=sesion.id))

    integrante = Integrante(
        stand_id=stand.id,
        nombre=nombre,
        telefono=telefono or None
    )
    db.session.add(integrante)
    db.session.commit()
    flash(f'Integrante "{nombre}" creado.', 'success')
    return redirect(url_for('sesiones.detalle', codigo=codigo, sesion_id=sesion.id))


@sesiones_bp.route('/<codigo>/sesiones/<int:sesion_id>/integrantes', methods=['POST'])
def gestionar_integrantes(codigo, sesion_id):
    stand = get_stand_or_404(codigo)
    sesion = SesionVenta.query.filter_by(id=sesion_id, stand_id=stand.id).first_or_404()

    # Remove existing assignments
    SesionIntegrante.query.filter_by(sesion_id=sesion.id).delete()

    # Add new assignments from form
    integrantes_disponibles = stand.integrantes.filter_by(activo=True).all()
    for integrante in integrantes_disponibles:
        roles = request.form.getlist(f'roles_{integrante.id}')
        for rol in roles:
            if rol in ('cocina', 'atencion', 'entrega'):
                si = SesionIntegrante(
                    sesion_id=sesion.id,
                    integrante_id=integrante.id,
                    rol=rol
                )
                db.session.add(si)

    db.session.commit()
    flash('Roles actualizados.', 'success')
    return redirect(url_for('sesiones.detalle', codigo=codigo, sesion_id=sesion.id))
