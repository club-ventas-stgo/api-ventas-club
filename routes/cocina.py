from flask import Blueprint, render_template, jsonify
from models import Venta
from routes.stand import get_stand_or_404

cocina_bp = Blueprint('cocina', __name__, url_prefix='/s')


@cocina_bp.route('/<codigo>/cocina')
def panel(codigo):
    stand = get_stand_or_404(codigo)
    pedidos = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega.in_(['pendiente', 'en_preparacion'])
    ).order_by(Venta.created_at.asc()).all()
    return render_template('cocina/panel.html', stand=stand, pedidos=pedidos)


@cocina_bp.route('/<codigo>/cocina/api')
def api_pedidos(codigo):
    stand = get_stand_or_404(codigo)
    pedidos = Venta.query.filter(
        Venta.stand_id == stand.id,
        Venta.estado_entrega.in_(['pendiente', 'en_preparacion'])
    ).order_by(Venta.created_at.asc()).all()

    data = []
    for p in pedidos:
        data.append({
            'id': p.id,
            'numero_orden': p.numero_orden,
            'cliente_nombre': p.cliente_nombre or '',
            'estado_entrega': p.estado_entrega,
            'notas': p.notas or '',
            'created_at': p.created_at.strftime('%H:%M'),
            'detalles': [{
                'nombre_producto': d.nombre_producto,
                'cantidad': d.cantidad,
                'precio_unitario': d.precio_unitario,
                'subtotal': d.subtotal
            } for d in p.detalles]
        })

    return jsonify(data)
