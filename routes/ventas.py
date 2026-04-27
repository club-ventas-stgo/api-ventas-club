import json
from collections import OrderedDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from models import Stand, Producto, Promocion, Venta, DetalleVenta, SesionVenta
from routes.stand import get_stand_or_404

CHILE_TZ = ZoneInfo('America/Santiago')

ventas_bp = Blueprint('ventas', __name__, url_prefix='/s')


def siguiente_numero_orden(stand_id):
    ultima = Venta.query.filter_by(stand_id=stand_id).order_by(Venta.numero_orden.desc()).first()
    return (ultima.numero_orden + 1) if ultima else 1


def calcular_subtotal_con_promo(producto_id, cantidad, precio_unitario, promos_activas):
    """Calculate subtotal applying promotions if applicable.
    promos_activas: dict {producto_id: Promocion}
    Returns (subtotal, promo_id, promo_texto)
    """
    promo = promos_activas.get(producto_id)
    if promo and promo.cantidad and promo.precio_promocion and cantidad >= promo.cantidad:
        batches = cantidad // promo.cantidad
        remainder = cantidad % promo.cantidad
        subtotal = batches * promo.precio_promocion + remainder * precio_unitario
        texto = f"{promo.cantidad}x${promo.precio_promocion:,}"
        return subtotal, promo.id, texto
    return cantidad * precio_unitario, None, None


def get_promos_activas_dict(stand_id):
    """Get active promos indexed by producto_id."""
    promos = Promocion.query.filter_by(stand_id=stand_id, activa=True).filter(
        Promocion.producto_id.isnot(None)
    ).all()
    return {p.producto_id: p for p in promos}


def get_or_create_session(stand_id):
    """Get or create a session for today (Chile TZ). Returns sesion_id."""
    hoy = datetime.now(timezone.utc).astimezone(CHILE_TZ).date()
    # Prefer an open session for today
    sesion = SesionVenta.query.filter_by(stand_id=stand_id, fecha=hoy, estado='abierta').first()
    if sesion:
        return sesion.id
    # Fall back to any session for today (e.g. programada)
    sesion = SesionVenta.query.filter_by(stand_id=stand_id, fecha=hoy).first()
    if sesion:
        if sesion.estado == 'programada':
            sesion.estado = 'abierta'
            db.session.flush()
        return sesion.id
    sesion = SesionVenta(stand_id=stand_id, fecha=hoy, estado='abierta')
    db.session.add(sesion)
    db.session.flush()
    return sesion.id


@ventas_bp.route('/<codigo>/panel')
def panel(codigo):
    stand = get_stand_or_404(codigo)
    tab = request.args.get('tab', 'ventas')

    # Load ventas for the initial render
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
        local_dt = v.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ)
        dia = local_dt.strftime('%Y-%m-%d')
        if dia not in ventas_por_dia:
            ventas_por_dia[dia] = {'ventas': [], 'total': 0, 'count': 0}
        ventas_por_dia[dia]['ventas'].append(v)
        ventas_por_dia[dia]['total'] += v.total_final
        ventas_por_dia[dia]['count'] += 1

    return render_template('ventas/panel.html', stand=stand, tab=tab,
                           ventas_por_dia=ventas_por_dia,
                           filtro_estado=filtro_estado, filtro_pago=filtro_pago)


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
        local_dt = v.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ)
        dia = local_dt.strftime('%Y-%m-%d')
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        cliente = request.form.get('cliente_nombre', '').strip()
        metodo_pago = request.form.get('metodo_pago', 'efectivo')
        notas = request.form.get('notas', '').strip()
        total_final_str = request.form.get('total_final', '0')
        items_json = request.form.get('items', '[]')

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            if is_ajax:
                return jsonify({'success': False, 'error': 'Error en los datos de productos.'}), 400
            flash('Error en los datos de productos.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        if not items:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Debe agregar al menos un producto.'}), 400
            flash('Debe agregar al menos un producto.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        promos_activas = get_promos_activas_dict(stand.id)
        detalles = []
        total_original = 0

        for item in items:
            producto = Producto.query.get(item.get('producto_id'))
            if not producto or producto.stand_id != stand.id:
                continue

            try:
                cantidad = max(1, int(item.get('cantidad', 1)))
            except (ValueError, TypeError):
                cantidad = 1
            try:
                precio_unitario = int(item.get('precio', producto.precio))
            except (ValueError, TypeError):
                precio_unitario = producto.precio

            subtotal, promo_id, promo_texto = calcular_subtotal_con_promo(
                producto.id, cantidad, precio_unitario, promos_activas)
            total_original += subtotal

            detalles.append(DetalleVenta(
                producto_id=producto.id,
                nombre_producto=producto.nombre,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
                promocion_id=promo_id,
                promocion_texto=promo_texto
            ))

        if not detalles:
            if is_ajax:
                return jsonify({'success': False, 'error': 'No se encontraron productos válidos.'}), 400
            flash('No se encontraron productos válidos.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        try:
            total_final = int(total_final_str)
        except (ValueError, TypeError):
            total_final = total_original

        sesion_id = request.form.get('sesion_id', type=int)
        if not sesion_id:
            sesion_id = get_or_create_session(stand.id)

        try:
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
        except Exception:
            db.session.rollback()
            if is_ajax:
                return jsonify({'success': False, 'error': 'Error al guardar la venta.'}), 500
            flash('Error al guardar la venta.', 'danger')
            return redirect(url_for('ventas.nueva', codigo=codigo))

        if is_ajax:
            return jsonify({'success': True, 'venta_id': venta.id, 'numero_orden': venta.numero_orden})

        flash(f'Venta #{venta.numero_orden} creada.|{venta.id}', 'venta_creada')
        redirect_args = {'codigo': codigo}
        if sesion_id:
            redirect_args['sesion_id'] = sesion_id
        return redirect(url_for('ventas.nueva', **redirect_args))

    productos = stand.productos.filter_by(activo=True).order_by(Producto.nombre).all()
    promociones = stand.promociones.filter_by(activa=True).all()
    promos_json = {p.producto_id: {'cantidad': p.cantidad, 'precio_promocion': p.precio_promocion, 'nombre': p.nombre}
                   for p in promociones if p.producto_id and p.cantidad and p.precio_promocion}
    sesion_id = request.args.get('sesion_id', type=int)
    return render_template('ventas/nueva.html', stand=stand, productos=productos, promociones=promociones,
                           promos_json=promos_json, sesion_id=sesion_id)


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
    if nuevo_estado in ('pendiente', 'listo', 'entregado'):
        venta.estado_entrega = nuevo_estado
        db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'estado_entrega': venta.estado_entrega})

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

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'estado_pago': venta.estado_pago, 'monto_pagado': venta.monto_pagado})

    flash('Venta marcada como pagada.', 'success')
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/marcar-entregado', methods=['POST'])
def marcar_entregado(codigo, venta_id):
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()
    venta.estado_entrega = 'entregado'
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'estado_entrega': venta.estado_entrega})

    flash('Venta marcada como entregada.', 'success')
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))


@ventas_bp.route('/<codigo>/ventas/partial')
def lista_partial(codigo):
    stand = get_stand_or_404(codigo)
    filtro_estado = request.args.get('estado_entrega', '')
    filtro_pago = request.args.get('estado_pago', '')
    sesion_id = request.args.get('sesion_id', type=int)

    query = stand.ventas
    if sesion_id:
        query = query.filter_by(sesion_id=sesion_id)
    if filtro_estado:
        query = query.filter_by(estado_entrega=filtro_estado)
    if filtro_pago:
        query = query.filter_by(estado_pago=filtro_pago)

    ventas = query.order_by(Venta.created_at.desc()).all()

    ventas_por_dia = OrderedDict()
    for v in ventas:
        local_dt = v.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ)
        dia = local_dt.strftime('%Y-%m-%d')
        if dia not in ventas_por_dia:
            ventas_por_dia[dia] = {'ventas': [], 'total': 0, 'count': 0}
        ventas_por_dia[dia]['ventas'].append(v)
        ventas_por_dia[dia]['total'] += v.total_final
        ventas_por_dia[dia]['count'] += 1

    tpl = 'ventas/_ventas_cards.html' if request.args.get('cards') else 'ventas/_ventas_partial.html'
    return render_template(tpl, stand=stand, ventas_por_dia=ventas_por_dia,
                           filtro_estado=filtro_estado, filtro_pago=filtro_pago)


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/editar', methods=['GET', 'POST'])
def editar_venta(codigo, venta_id):
    """Edit an existing order - add/remove products."""
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        cliente = request.form.get('cliente_nombre', '').strip()
        notas = request.form.get('notas', '').strip()
        total_final_str = request.form.get('total_final', '0')
        items_json = request.form.get('items', '[]')

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            if is_ajax:
                return jsonify({'success': False, 'error': 'Error en los datos de productos.'}), 400
            flash('Error en los datos de productos.', 'danger')
            return redirect(url_for('ventas.editar_venta', codigo=codigo, venta_id=venta_id))

        if not items:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Debe tener al menos un producto.'}), 400
            flash('Debe tener al menos un producto.', 'danger')
            return redirect(url_for('ventas.editar_venta', codigo=codigo, venta_id=venta_id))

        # Validate new items BEFORE deleting old ones
        promos_activas = get_promos_activas_dict(stand.id)
        detalles = []
        total_original = 0
        for item in items:
            producto = Producto.query.get(item.get('producto_id'))
            if not producto or producto.stand_id != stand.id:
                continue
            try:
                cantidad = max(1, int(item.get('cantidad', 1)))
            except (ValueError, TypeError):
                cantidad = 1
            try:
                precio_unitario = int(item.get('precio', producto.precio))
            except (ValueError, TypeError):
                precio_unitario = producto.precio

            subtotal, promo_id, promo_texto = calcular_subtotal_con_promo(
                producto.id, cantidad, precio_unitario, promos_activas)
            total_original += subtotal
            detalles.append(DetalleVenta(
                venta_id=venta.id,
                producto_id=producto.id,
                nombre_producto=producto.nombre,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
                promocion_id=promo_id,
                promocion_texto=promo_texto
            ))

        if not detalles:
            if is_ajax:
                return jsonify({'success': False, 'error': 'No se encontraron productos válidos.'}), 400
            flash('No se encontraron productos válidos.', 'danger')
            return redirect(url_for('ventas.editar_venta', codigo=codigo, venta_id=venta_id))

        try:
            # Remove old detalles only after validation passes
            DetalleVenta.query.filter_by(venta_id=venta.id).delete()

            for d in detalles:
                db.session.add(d)

            venta.cliente_nombre = cliente
            venta.notas = notas
            venta.total_original = total_original
            try:
                venta.total_final = int(total_final_str)
            except (ValueError, TypeError):
                venta.total_final = total_original

            db.session.commit()
        except Exception:
            db.session.rollback()
            if is_ajax:
                return jsonify({'success': False, 'error': 'Error al actualizar la venta.'}), 500
            flash('Error al actualizar la venta.', 'danger')
            return redirect(url_for('ventas.editar_venta', codigo=codigo, venta_id=venta_id))

        if is_ajax:
            return jsonify({'success': True, 'total_final': venta.total_final})

        flash(f'Venta #{venta.numero_orden} actualizada.', 'success')
        return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))

    productos = stand.productos.filter_by(activo=True).order_by(Producto.nombre).all()
    promociones = stand.promociones.filter_by(activa=True).all()
    promos_json = {p.producto_id: {'cantidad': p.cantidad, 'precio_promocion': p.precio_promocion, 'nombre': p.nombre}
                   for p in promociones if p.producto_id and p.cantidad and p.precio_promocion}
    return render_template('ventas/editar.html', stand=stand, venta=venta, productos=productos, promos_json=promos_json)


@ventas_bp.route('/<codigo>/stock')
def stock_api(codigo):
    """API: returns current stock for all products with stock limits."""
    stand = get_stand_or_404(codigo)
    productos = stand.productos.filter(Producto.stock.isnot(None), Producto.activo == True).all()
    return jsonify([{
        'id': p.id,
        'nombre': p.nombre,
        'stock': p.stock,
        'vendido': p.stock_vendido,
        'disponible': p.stock_disponible,
    } for p in productos])


@ventas_bp.route('/<codigo>/ventas/buscar')
def buscar(codigo):
    """Search sales by customer name or order number."""
    stand = get_stand_or_404(codigo)
    q = request.args.get('q', '').strip()
    sesion_id = request.args.get('sesion_id', type=int)

    if not q:
        return jsonify([])

    filters = [
        Venta.stand_id == stand.id,
        db.or_(
            Venta.cliente_nombre.ilike(f'%{q}%'),
            Venta.numero_orden == (int(q) if q.isdigit() else -1)
        )
    ]
    if sesion_id:
        filters.append(Venta.sesion_id == sesion_id)

    ventas = Venta.query.filter(*filters).order_by(Venta.created_at.desc()).limit(20).all()

    results = [{
        'id': v.id,
        'numero_orden': v.numero_orden,
        'cliente_nombre': v.cliente_nombre or '',
        'total_final': v.total_final,
        'estado_entrega': v.estado_entrega,
        'estado_pago': v.estado_pago,
        'created_at': v.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ).strftime('%d/%m %H:%M'),
        'detalles': [{'nombre': d.nombre_producto, 'cantidad': d.cantidad, 'precio_unitario': d.precio_unitario, 'subtotal': d.subtotal, 'promocion_texto': d.promocion_texto} for d in v.detalles]
    } for v in ventas]

    return jsonify(results)


@ventas_bp.route('/<codigo>/ventas/clientes')
def clientes(codigo):
    """Autocomplete: return unique client names matching query."""
    stand = get_stand_or_404(codigo)
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    nombres = db.session.query(Venta.cliente_nombre).filter(
        Venta.stand_id == stand.id,
        Venta.cliente_nombre.isnot(None),
        Venta.cliente_nombre != '',
        Venta.cliente_nombre.ilike(f'%{q}%')
    ).distinct().limit(6).all()
    return jsonify([n[0] for n in nombres if n[0]])


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/pago', methods=['POST'])
def actualizar_pago(codigo, venta_id):
    """API endpoint for inline payment updates."""
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()

    metodo_pago = request.form.get('metodo_pago', venta.metodo_pago)
    monto_efectivo = request.form.get('monto_efectivo', '0')
    monto_transferencia = request.form.get('monto_transferencia', '0')

    try:
        monto_ef = int(monto_efectivo)
    except (ValueError, TypeError):
        monto_ef = 0
    try:
        monto_tr = int(monto_transferencia)
    except (ValueError, TypeError):
        monto_tr = 0

    total_pagado = monto_ef + monto_tr
    venta.monto_pagado = total_pagado
    venta.metodo_pago = metodo_pago

    if total_pagado >= venta.total_final:
        venta.estado_pago = 'pagado'
    elif total_pagado > 0:
        venta.estado_pago = 'parcial'
    else:
        venta.estado_pago = 'pendiente'

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'estado_pago': venta.estado_pago, 'monto_pagado': venta.monto_pagado})

    flash('Pago actualizado.', 'success')
    return redirect(url_for('ventas.detalle', codigo=codigo, venta_id=venta.id))


@ventas_bp.route('/<codigo>/control')
def control(codigo):
    """Unified control panel with all tabs."""
    stand = get_stand_or_404(codigo)
    productos = stand.productos.order_by(Producto.activo.desc(), Producto.created_at.desc()).all()
    productos_activos = [p for p in productos if p.activo]
    promociones = stand.promociones.order_by(Promocion.activa.desc(), Promocion.created_at.desc()).all()
    promociones_activas = [p for p in promociones if p.activa]

    # Session filtering
    sesion_id = request.args.get('sesion_id', type=int)
    sesion = None
    if sesion_id:
        sesion = SesionVenta.query.filter_by(id=sesion_id, stand_id=stand.id).first()

    # Ventas
    query = stand.ventas
    if sesion:
        query = query.filter_by(sesion_id=sesion.id)
    ventas = query.order_by(Venta.created_at.desc()).all()

    ventas_por_dia = OrderedDict()
    for v in ventas:
        local_dt = v.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ)
        dia = local_dt.strftime('%Y-%m-%d')
        if dia not in ventas_por_dia:
            ventas_por_dia[dia] = {'ventas': [], 'total': 0, 'count': 0}
        ventas_por_dia[dia]['ventas'].append(v)
        ventas_por_dia[dia]['total'] += v.total_final
        ventas_por_dia[dia]['count'] += 1

    promos_json = {p.producto_id: {'cantidad': p.cantidad, 'precio_promocion': p.precio_promocion, 'nombre': p.nombre}
                   for p in promociones_activas if p.producto_id and p.cantidad and p.precio_promocion}

    return render_template('ventas/control.html', stand=stand,
                           productos=productos, productos_activos=productos_activos,
                           promociones=promociones, promociones_activas=promociones_activas,
                           promos_json=promos_json, ventas_por_dia=ventas_por_dia,
                           sesion=sesion, sesion_id=sesion_id)


@ventas_bp.route('/<codigo>/ventas/<int:venta_id>/json')
def venta_json(codigo, venta_id):
    """Return full sale detail as JSON for inline expand."""
    stand = get_stand_or_404(codigo)
    venta = Venta.query.filter_by(id=venta_id, stand_id=stand.id).first_or_404()

    return jsonify({
        'id': venta.id,
        'numero_orden': venta.numero_orden,
        'cliente_nombre': venta.cliente_nombre or '',
        'metodo_pago': venta.metodo_pago,
        'estado_pago': venta.estado_pago,
        'monto_pagado': venta.monto_pagado,
        'total_original': venta.total_original,
        'total_final': venta.total_final,
        'estado_entrega': venta.estado_entrega,
        'notas': venta.notas or '',
        'created_at': venta.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ).strftime('%d/%m/%Y %H:%M'),
        'detalles': [{
            'nombre_producto': d.nombre_producto,
            'cantidad': d.cantidad,
            'precio_unitario': d.precio_unitario,
            'subtotal': d.subtotal,
            'promocion_texto': d.promocion_texto
        } for d in venta.detalles]
    })
