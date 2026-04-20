from datetime import datetime, timezone
from app import db


class Stand(db.Model):
    __tablename__ = 'stands'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    foto = db.Column(db.Text)
    codigo_acceso = db.Column(db.String(10), unique=True, nullable=False)
    inversion = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    productos = db.relationship('Producto', backref='stand', lazy='dynamic')
    promociones = db.relationship('Promocion', backref='stand', lazy='dynamic')
    ventas = db.relationship('Venta', backref='stand', lazy='dynamic')
    integrantes = db.relationship('Integrante', backref='stand', lazy='dynamic')
    sesiones = db.relationship('SesionVenta', backref='stand', lazy='dynamic')


class Producto(db.Model):
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, nullable=True)  # NULL = sin limite de stock
    foto = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def stock_vendido(self):
        """Cantidad total vendida de este producto."""
        from sqlalchemy import func
        result = db.session.query(func.coalesce(func.sum(DetalleVenta.cantidad), 0)).filter_by(producto_id=self.id).scalar()
        return result

    @property
    def stock_disponible(self):
        """Stock restante. None si no tiene limite."""
        if self.stock is None:
            return None
        return max(0, self.stock - self.stock_vendido)


class Promocion(db.Model):
    __tablename__ = 'promociones'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Venta(db.Model):
    __tablename__ = 'ventas'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    sesion_id = db.Column(db.Integer, db.ForeignKey('sesiones_venta.id'), nullable=True)
    numero_orden = db.Column(db.Integer, nullable=False)
    cliente_nombre = db.Column(db.String(100))
    metodo_pago = db.Column(db.String(20), default='efectivo')
    estado_pago = db.Column(db.String(20), default='pendiente')
    monto_pagado = db.Column(db.Integer, default=0)
    total_original = db.Column(db.Integer, nullable=False)
    total_final = db.Column(db.Integer, nullable=False)
    estado_entrega = db.Column(db.String(20), default='pendiente')
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    detalles = db.relationship('DetalleVenta', backref='venta', lazy='select')


class DetalleVenta(db.Model):
    __tablename__ = 'detalle_venta'

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id', ondelete='SET NULL'), nullable=True)
    nombre_producto = db.Column(db.String(100), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)


class Integrante(db.Model):
    __tablename__ = 'integrantes'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class SesionVenta(db.Model):
    __tablename__ = 'sesiones_venta'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    nombre = db.Column(db.String(100))
    estado = db.Column(db.String(20), default='programada')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    integrantes = db.relationship('SesionIntegrante', backref='sesion', lazy='select')
    ventas = db.relationship('Venta', backref='sesion', lazy='dynamic')


class SesionIntegrante(db.Model):
    __tablename__ = 'sesion_integrantes'

    id = db.Column(db.Integer, primary_key=True)
    sesion_id = db.Column(db.Integer, db.ForeignKey('sesiones_venta.id'), nullable=False)
    integrante_id = db.Column(db.Integer, db.ForeignKey('integrantes.id'), nullable=False)
    rol = db.Column(db.String(30), nullable=False)

    integrante = db.relationship('Integrante', lazy='select')
