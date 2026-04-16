from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from sqlalchemy import or_, and_, func, case
from app import db
from models import Stand, Post, Comentario, Like, Mensaje
from routes.main import comprimir_imagen

comunidad_bp = Blueprint('comunidad', __name__, url_prefix='/s')

POSTS_PER_PAGE = 10


def get_stand_or_404(codigo):
    stand = Stand.query.filter_by(codigo_acceso=codigo, activo=True).first()
    if not stand:
        abort(404)
    return stand


@comunidad_bp.route('/<codigo>/comunidad')
def feed(codigo):
    stand = get_stand_or_404(codigo)
    page = request.args.get('page', 1, type=int)

    posts = Post.query.filter_by(activo=True)\
        .order_by(Post.created_at.desc())\
        .paginate(page=page, per_page=POSTS_PER_PAGE, error_out=False)

    # Precompute likes for current stand
    liked_ids = set()
    if posts.items:
        post_ids = [p.id for p in posts.items]
        liked = Like.query.filter(Like.post_id.in_(post_ids), Like.stand_id == stand.id).all()
        liked_ids = {l.post_id for l in liked}

    return render_template('comunidad/feed.html', stand=stand, posts=posts,
                           liked_ids=liked_ids)


@comunidad_bp.route('/<codigo>/comunidad/nuevo', methods=['POST'])
def nuevo_post(codigo):
    stand = get_stand_or_404(codigo)
    contenido = request.form.get('contenido', '').strip()

    if not contenido:
        flash('Escribe algo para publicar.', 'danger')
        return redirect(url_for('comunidad.feed', codigo=codigo))

    foto = None
    if 'foto' in request.files and request.files['foto'].filename:
        try:
            foto = comprimir_imagen(request.files['foto'])
        except Exception:
            flash('Error al procesar la imagen.', 'danger')
            return redirect(url_for('comunidad.feed', codigo=codigo))

    post = Post(stand_id=stand.id, contenido=contenido, foto=foto)
    db.session.add(post)
    db.session.commit()
    flash('Publicacion creada.', 'success')
    return redirect(url_for('comunidad.feed', codigo=codigo))


@comunidad_bp.route('/<codigo>/comunidad/post/<int:post_id>')
def detalle_post(codigo, post_id):
    stand = get_stand_or_404(codigo)
    post = Post.query.filter_by(id=post_id, activo=True).first_or_404()
    comentarios = post.comentarios.order_by(Comentario.created_at.asc()).all()
    ya_like = Like.query.filter_by(post_id=post.id, stand_id=stand.id).first() is not None
    return render_template('comunidad/detalle_post.html', stand=stand, post=post,
                           comentarios=comentarios, ya_like=ya_like)


@comunidad_bp.route('/<codigo>/comunidad/post/<int:post_id>/comentar', methods=['POST'])
def comentar(codigo, post_id):
    stand = get_stand_or_404(codigo)
    post = Post.query.filter_by(id=post_id, activo=True).first_or_404()
    contenido = request.form.get('contenido', '').strip()

    if not contenido:
        flash('El comentario no puede estar vacio.', 'danger')
        return redirect(url_for('comunidad.detalle_post', codigo=codigo, post_id=post.id))

    comentario = Comentario(post_id=post.id, stand_id=stand.id, contenido=contenido)
    db.session.add(comentario)
    db.session.commit()
    return redirect(url_for('comunidad.detalle_post', codigo=codigo, post_id=post.id))


@comunidad_bp.route('/<codigo>/comunidad/post/<int:post_id>/like', methods=['POST'])
def toggle_like(codigo, post_id):
    stand = get_stand_or_404(codigo)
    post = Post.query.filter_by(id=post_id, activo=True).first_or_404()

    existing = Like.query.filter_by(post_id=post.id, stand_id=stand.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Like(post_id=post.id, stand_id=stand.id))
    db.session.commit()

    # AJAX response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        count = post.likes.count()
        liked = existing is None  # toggled: if existed before, now removed
        return jsonify(liked=liked, count=count)

    return redirect(request.referrer or url_for('comunidad.feed', codigo=codigo))


@comunidad_bp.route('/<codigo>/comunidad/post/<int:post_id>/eliminar', methods=['POST'])
def eliminar_post(codigo, post_id):
    stand = get_stand_or_404(codigo)
    post = Post.query.filter_by(id=post_id, stand_id=stand.id, activo=True).first_or_404()
    post.activo = False
    db.session.commit()
    flash('Publicacion eliminada.', 'info')
    return redirect(url_for('comunidad.feed', codigo=codigo))


@comunidad_bp.route('/<codigo>/comunidad/comentario/<int:comentario_id>/eliminar', methods=['POST'])
def eliminar_comentario(codigo, comentario_id):
    stand = get_stand_or_404(codigo)
    comentario = Comentario.query.filter_by(id=comentario_id, stand_id=stand.id).first_or_404()
    post_id = comentario.post_id
    db.session.delete(comentario)
    db.session.commit()
    flash('Comentario eliminado.', 'info')
    return redirect(url_for('comunidad.detalle_post', codigo=codigo, post_id=post_id))


@comunidad_bp.route('/<codigo>/comunidad/perfil/<int:stand_id>')
def perfil(codigo, stand_id):
    stand = get_stand_or_404(codigo)
    perfil_stand = Stand.query.filter_by(id=stand_id, activo=True).first_or_404()
    posts = Post.query.filter_by(stand_id=perfil_stand.id, activo=True)\
        .order_by(Post.created_at.desc()).all()

    liked_ids = set()
    if posts:
        post_ids = [p.id for p in posts]
        liked = Like.query.filter(Like.post_id.in_(post_ids), Like.stand_id == stand.id).all()
        liked_ids = {l.post_id for l in liked}

    return render_template('comunidad/perfil.html', stand=stand, perfil_stand=perfil_stand,
                           posts=posts, liked_ids=liked_ids)


@comunidad_bp.route('/<codigo>/comunidad/perfil/bio', methods=['POST'])
def editar_bio(codigo):
    stand = get_stand_or_404(codigo)
    bio = request.form.get('bio', '').strip()[:200]
    stand.bio = bio
    db.session.commit()
    flash('Bio actualizada.', 'success')
    return redirect(url_for('comunidad.perfil', codigo=codigo, stand_id=stand.id))


@comunidad_bp.route('/<codigo>/comunidad/mensajes')
def mensajes(codigo):
    stand = get_stand_or_404(codigo)

    # Get all stands that have exchanged messages with this stand
    # Subquery: latest message per conversation
    sent_or_recv = Mensaje.query.filter(
        or_(Mensaje.remitente_id == stand.id, Mensaje.destinatario_id == stand.id)
    ).subquery()

    # Get unique conversation partners
    partner_ids_sent = db.session.query(Mensaje.destinatario_id).filter(Mensaje.remitente_id == stand.id)
    partner_ids_recv = db.session.query(Mensaje.remitente_id).filter(Mensaje.destinatario_id == stand.id)
    partner_ids = set(r[0] for r in partner_ids_sent.union(partner_ids_recv).all())

    conversaciones = []
    for pid in partner_ids:
        partner = Stand.query.get(pid)
        if not partner or not partner.activo:
            continue
        # Last message between them
        ultimo = Mensaje.query.filter(
            or_(
                and_(Mensaje.remitente_id == stand.id, Mensaje.destinatario_id == pid),
                and_(Mensaje.remitente_id == pid, Mensaje.destinatario_id == stand.id)
            )
        ).order_by(Mensaje.created_at.desc()).first()
        # Unread count
        no_leidos = Mensaje.query.filter_by(
            remitente_id=pid, destinatario_id=stand.id, leido=False
        ).count()
        conversaciones.append({
            'partner': partner,
            'ultimo': ultimo,
            'no_leidos': no_leidos
        })

    # Sort by last message date
    conversaciones.sort(key=lambda c: c['ultimo'].created_at if c['ultimo'] else 0, reverse=True)

    return render_template('comunidad/mensajes.html', stand=stand, conversaciones=conversaciones)


@comunidad_bp.route('/<codigo>/comunidad/mensajes/<int:dest_id>', methods=['GET', 'POST'])
def conversacion(codigo, dest_id):
    stand = get_stand_or_404(codigo)
    otro = Stand.query.filter_by(id=dest_id, activo=True).first_or_404()

    if stand.id == otro.id:
        flash('No puedes enviarte mensajes a ti mismo.', 'danger')
        return redirect(url_for('comunidad.mensajes', codigo=codigo))

    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        if contenido:
            msg = Mensaje(remitente_id=stand.id, destinatario_id=otro.id, contenido=contenido)
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('comunidad.conversacion', codigo=codigo, dest_id=dest_id))

    # Mark received messages as read
    Mensaje.query.filter_by(
        remitente_id=otro.id, destinatario_id=stand.id, leido=False
    ).update({'leido': True})
    db.session.commit()

    mensajes = Mensaje.query.filter(
        or_(
            and_(Mensaje.remitente_id == stand.id, Mensaje.destinatario_id == otro.id),
            and_(Mensaje.remitente_id == otro.id, Mensaje.destinatario_id == stand.id)
        )
    ).order_by(Mensaje.created_at.asc()).all()

    return render_template('comunidad/conversacion.html', stand=stand, otro=otro, mensajes=mensajes)
