from datetime import datetime, timezone
from app import db


class Stand(db.Model):
    __tablename__ = 'stands'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    foto = db.Column(db.Text)
    codigo_acceso = db.Column(db.String(10), unique=True, nullable=False)
    inversion = db.Column(db.Integer, default=0)
    bio = db.Column(db.String(200), default='')
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    productos = db.relationship('Producto', backref='stand', lazy='dynamic')
    promociones = db.relationship('Promocion', backref='stand', lazy='dynamic')
    ventas = db.relationship('Venta', backref='stand', lazy='dynamic')
    posts = db.relationship('Post', backref='stand', lazy='dynamic')
    comentarios = db.relationship('Comentario', backref='stand', lazy='dynamic')
    likes = db.relationship('Like', backref='stand', lazy='dynamic')


class Producto(db.Model):
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Integer, nullable=False)
    foto = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


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


class Post(db.Model):
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    foto = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    comentarios = db.relationship('Comentario', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy='dynamic', cascade='all, delete-orphan')


class Comentario(db.Model):
    __tablename__ = 'comentarios'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Like(db.Model):
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    stand_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('post_id', 'stand_id', name='uq_like_post_stand'),)


class Mensaje(db.Model):
    __tablename__ = 'mensajes'

    id = db.Column(db.Integer, primary_key=True)
    remitente_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey('stands.id'), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    leido = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    remitente = db.relationship('Stand', foreign_keys=[remitente_id], backref='mensajes_enviados')
    destinatario = db.relationship('Stand', foreign_keys=[destinatario_id], backref='mensajes_recibidos')
