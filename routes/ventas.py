import json
from collections import OrderedDict
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from models import Stand, Producto, Venta, DetalleVenta
from routes.stand import get_stand_or_404

ventas_bp = Blueprint('ventas', __name__, url_prefix='/s')


def siguiente_numero_orden(stand_id):
    ultima = Venta.query.filter_by(stand_id=stand_id).order_by(Venta.numero_orden.desc()).first()
    return (ultima.numero_orden + 1) if ultima else 1


@ventas_bp.route('/<codigo>/ventas')
def lista(codigo):
    stand = get_stand_or_404(codigo)
    filtro_estado = request.args.get('estado_entrega', '')
    filtro_pago = request.args.get('estado_pago', '')

    query = stand.ventas
    if filtro_estado:
        query = query.filter_by(estado_entrega=filtro_estado)
    if filtro_pago:
        query = query.filter_by(estado_pago=filtro_pago)

    ventas = query.order_by(Venta.created_at.desc()).all()

    ventas_por_dia = OrderedDict()
    for v in ventas:
        dia = v.created_at.strftime('%Y-%m-%d')
        if dia not in ventas_por_dia:
            ventas_por_dia[dia] = {'ventas': [], 'total': 0, 'count': 0}
        ventas_por_dia[dia]['ventas'].append(v)
        ventas_por_dia[dia]['total'] += v.total_final
        ventas_por_dia[dia]['count'] += 1

    return render_template('ventas/lista.html', stand=stand, ventas_por_dia=ventas_por_dia,
                           filtro_estado=filtro_estado, filtro_pago=filtro_pago)


@ventas_bp.route('/<codigo>/ventas/nueva', methods=['GET', 'POST'])
def nueva(codigo):
    stand = get_stand_or_404(codigo)

    if request.method == 'POST':
        cliente = request.form.get('cliente_nombre', '').strip()
        metodo_pago = request.form.get('metodo_pago', 'efectivo')
        notas = request.form.get('notas', '').strip()
        total_final_str = request.form.get('total_final', '0')
        items_json = request.form.get('items', '[]')

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            flash('Error en los datos de productos.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        if not items:
            flash('Debe agregar al menos un producto.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        detalles = []
        total_original = 0

        for item in items:
            producto = Producto.query.get(item.get('producto_id'))
            if not producto or producto.stand_id != stand.id:
                continue

            cantidad = max(1, int(item.get('cantidad', 1)))
            try:
                precio_unitario = int(item.get('precio', producto.precio))
            except (ValueError, TypeError):
                precio_unitario = producto.precio
            subtotal = precio_unitario * cantidad
            total_original += subtotal

            detalles.append(DetalleVenta(
                producto_id=producto.id,
                nombre_producto=producto.nombre,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal
            ))

        if not detalles:
            flash('No se encontraron productos válidos.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        try:
            total_final = int(total_final_str)
        except ValueError:
            total_final = total_original

        sesion_id = request.form.get('sesion_id', type=int)
        venta = Venta(
            stand_id=stand.id,
            sesion_id=sesion_id,
            numero_orden=siguiente_numero_orden(stand.id),
            cliente_nombre=cliente,
            metodo_pago=metodo_pago,
            total_original=total_original,
            total_final=total_final,
            notas=notas
        )
        db.session.add(venta)
        db.session.flush()

        for detalle in detalles:
            detalle.venta_id = venta.id
            db.session.add(detalle)

        db.session.commit()
        flash(f'Venta #{venta.numero_orden} creada.|{venta.id}', 'venta_creada')
        redirect_args = {'codigo': codigo}
        if sesion_id:
            redirect_args['sesion_id'] = sesion_id
        return redirect(url_for('ventas.nueva', **redirect_args))

    productos = stand.productos.filter_by(activo=True).order_by(Producto.nombre).all()
    promociones = stand.promociones.filter_by(activa=True).all()
    sesion_id = request.args.get('sesion_id', type=int)
    return render_template('ventas/nueva.html', stand=stand, productos=productos, promociones=promociones, sesion_id=sesion_id)


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>', methods=['GET', 'POST'])
def detalle(codigo, venta_id):
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()

    if request.method == 'POST':
        estado_pago = request.form.get('estado_pago', venta.estado_pago)
        monto_pagado = request.form.get('monto_pagado', str(venta.monto_pagado))
        estado_entrega = request.form.get('estado_entrega', venta.estado_entrega)
        total_final = request.form.get('total_final', str(venta.total_final))
        notas = request.form.get('notas', venta.notas or '')

        venta.estado_pago = estado_pago
        venta.estado_entrega = estado_entrega
        venta.notas = notas.strip()

        try:
            venta.monto_pagado = int(monto_pagado)
        except ValueError:
            pass

        try:
            venta.total_final = int(total_final)
        except ValueError:
            pass

        db.session.commit()
        flash('Venta actualizada.', 'success')
        return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))

    return render_template('ventas/detalle.html', stand=stand, venta=venta)


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/estado', methods=['POST'])
def cambiar_estado(codigo, venta_id):
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()

    nuevo_estado = request.form.get('estado_entrega')
    if nuevo_estado in ('pendiente', 'en_preparacion', 'listo', 'entregado'):
        venta.estado_entrega = nuevo_estado
        db.session.commit()

    referer = request.form.get('redirect', '')
    if 'cocina' in referer:
        return redirect(url_for('cocina.panel', codigo=codigo))
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/marcar-pagado', methods=['POST'])
def marcar_pagado(codigo, venta_id):
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()
    venta.monto_pagado = venta.total_final
    venta.estado_pago = 'pagado'
    db.session.commit()
    flash('Venta marcada como pagada.', 'success')
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/marcar-entregado', methods=['POST'])
def marcar_entregado(codigo, venta_id):
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()
    venta.estado_entrega = 'entregado'
    db.session.commit()
    flash('Venta marcada como entregada.', 'success')
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))
