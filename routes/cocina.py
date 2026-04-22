from datetime import timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, jsonify
from models import Venta, Producto
from routes.stand import get_stand_or_404

CHILE_TZ = ZoneInfo('America/Santiago')

cocina_bp = Blueprint('cocina', __name__, url_prefix='/s')


@cocina_bp.route('/<codigo>/cocina')
def panel(codigo):
    stand = get_stand_or_404(codigo)
    pendientes = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega == 'pendiente'
    ).order_by(Venta.created_at.asc()).all()
    listos = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega == 'listo'
    ).order_by(Venta.created_at.asc()).all()
    productos = Producto.query.filter_by(stand_id=stand.id).all()
    return render_template('cocina/panel.html', stand=stand, pendientes=pendientes, listos=listos, productos=productos)


@cocina_bp.route('/<codigo>/proyectar')
def proyectar(codigo):
    stand = get_stand_or_404(codigo)
    pendientes = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega == 'pendiente'
    ).order_by(Venta.created_at.asc()).all()
    listos = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega == 'listo'
    ).order_by(Venta.created_at.asc()).all()
    return render_template('cocina/proyectar.html', stand=stand, pendientes=pendientes, listos=listos)


@cocina_bp.route('/<codigo>/cocina/api')
def api_pedidos(codigo):
    stand = get_stand_or_404(codigo)
    pedidos = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega.in_(['pendiente', 'listo'])
    ).order_by(Venta.created_at.asc()).all()

    data = []
    for p in pedidos:
        data.append({
            'id': p.id,
            'numero_orden': p.numero_orden,
            'cliente_nombre': p.cliente_nombre or '',
            'estado_entrega': p.estado_entrega,
            'notas': p.notas or '',
            'created_at': p.created_at.replace(tzinfo=timezone.utc).astimezone(CHILE_TZ).strftime('%H:%M'),
            'detalles': [{
                'nombre_producto': d.nombre_producto,
                'cantidad': d.cantidad,
                'precio_unitario': d.precio_unitario,
                'subtotal': d.subtotal
            } for d in p.detalles]
        })

    return jsonify(data)
