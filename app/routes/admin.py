import os
from datetime import datetime
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app
)
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import AdminUser, Visitor, PortalSession, AuditLog
from app.models.site_config import SiteConfig

bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'webp'}
MAX_SIZE_MB = 2


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def _get_admin():
    return AdminUser.query.get(session['admin_id'])


def _ensure_default_admin():
    """Cria admin padrao se nao existir nenhum usuario."""
    if AdminUser.query.count() == 0:
        u = AdminUser(
            username=current_app.config.get('ADMIN_USERNAME', 'admin')
        )
        u.set_password(current_app.config.get('ADMIN_PASSWORD', 'admin123'))
        db.session.add(u)
        db.session.commit()


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@bp.get('/login')
def login():
    if session.get('admin_id'):
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html')


@bp.post('/login')
def login_post():
    _ensure_default_admin()
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''

    user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not user or not user.check_password(password):
        flash('Usuário ou senha inválidos.', 'error')
        return render_template('admin/login.html', username=username)

    user.last_login = datetime.utcnow()
    db.session.commit()
    session.permanent = True
    session['admin_id'] = user.id
    session['admin_username'] = user.username
    return redirect(url_for('admin.dashboard'))


@bp.get('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada.', 'success')
    return redirect(url_for('admin.login'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bp.get('/')
@login_required
def dashboard():
    total_visitors = Visitor.query.count()
    total_sessions = PortalSession.query.count()
    authorized_sessions = PortalSession.query.filter_by(authorized=True).count()
    error_logs = AuditLog.query.filter_by(status='error').count()
    recent_logs = (
        AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    )
    return render_template(
        'admin/dashboard.html',
        total_visitors=total_visitors,
        total_sessions=total_sessions,
        authorized_sessions=authorized_sessions,
        error_logs=error_logs,
        recent_logs=recent_logs,
        admin=_get_admin(),
    )


# ---------------------------------------------------------------------------
# Visitantes
# ---------------------------------------------------------------------------

@bp.get('/visitors')
@login_required
def visitors():
    q = (request.args.get('q') or '').strip()
    page = request.args.get('page', 1, type=int)
    query = Visitor.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Visitor.full_name.ilike(like),
                Visitor.email.ilike(like),
                Visitor.cpf.ilike(like),
                Visitor.mobile.ilike(like),
            )
        )
    pagination = query.order_by(Visitor.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template(
        'admin/visitors.html',
        pagination=pagination,
        q=q,
        admin=_get_admin(),
    )


@bp.post('/visitors/<int:vid>/toggle')
@login_required
def visitor_toggle(vid):
    v = Visitor.query.get_or_404(vid)
    v.is_active = not v.is_active
    db.session.commit()
    flash(f'Visitante {"ativado" if v.is_active else "desativado"}.', 'success')
    return redirect(request.referrer or url_for('admin.visitors'))


# ---------------------------------------------------------------------------
# Logs de auditoria
# ---------------------------------------------------------------------------

@bp.get('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    query = AuditLog.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template(
        'admin/logs.html',
        pagination=pagination,
        status_filter=status_filter,
        admin=_get_admin(),
    )


# ---------------------------------------------------------------------------
# Configuracoes — Aparencia
# ---------------------------------------------------------------------------

@bp.get('/settings/appearance')
@login_required
def settings_appearance():
    cfg = {
        'portal_title': SiteConfig.get('portal_title', 'Portal Wi-Fi UniFi'),
        'portal_welcome': SiteConfig.get('portal_welcome', 'Preencha seus dados para liberar o acesso à internet.'),
        'portal_btn_color': SiteConfig.get('portal_btn_color', '#0f766e'),
        'portal_bg_from': SiteConfig.get('portal_bg_from', '#020617'),
        'portal_bg_via': SiteConfig.get('portal_bg_via', '#0f172a'),
        'portal_bg_to': SiteConfig.get('portal_bg_to', '#1e293b'),
        'portal_accent': SiteConfig.get('portal_accent', '#2dd4bf'),
    }
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    has_logo = os.path.exists(logo_path)
    return render_template(
        'admin/settings_appearance.html',
        cfg=cfg,
        has_logo=has_logo,
        admin=_get_admin(),
    )


@bp.post('/settings/appearance')
@login_required
def settings_appearance_save():
    keys = [
        'portal_title', 'portal_welcome', 'portal_btn_color',
        'portal_bg_from', 'portal_bg_via', 'portal_bg_to', 'portal_accent',
    ]
    for k in keys:
        val = request.form.get(k)
        if val is not None:
            SiteConfig.set(k, val.strip())
    db.session.commit()
    flash('Aparência atualizada com sucesso!', 'success')
    return redirect(url_for('admin.settings_appearance'))


@bp.post('/settings/appearance/logo/upload')
@login_required
def upload_logo():
    file = request.files.get('logo')
    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.settings_appearance'))
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        flash('Formato não permitido. Use PNG, JPG, SVG ou WEBP.', 'error')
        return redirect(url_for('admin.settings_appearance'))
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_SIZE_MB * 1024 * 1024:
        flash(f'Arquivo muito grande. Máximo {MAX_SIZE_MB} MB.', 'error')
        return redirect(url_for('admin.settings_appearance'))
    uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    file.save(os.path.join(uploads_dir, 'logo.png'))
    flash('Logo atualizada com sucesso!', 'success')
    return redirect(url_for('admin.settings_appearance'))


@bp.post('/settings/appearance/logo/remove')
@login_required
def remove_logo():
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    if os.path.exists(logo_path):
        os.remove(logo_path)
        flash('Logo removida com sucesso.', 'success')
    else:
        flash('Nenhuma logo encontrada.', 'error')
    return redirect(url_for('admin.settings_appearance'))


# ---------------------------------------------------------------------------
# Configuracoes — UniFi
# ---------------------------------------------------------------------------

@bp.get('/settings/unifi')
@login_required
def settings_unifi():
    cfg = {
        'unifi_base_url': SiteConfig.get('unifi_base_url', current_app.config.get('UNIFI_BASE_URL', '')),
        'unifi_api_key': SiteConfig.get('unifi_api_key', current_app.config.get('UNIFI_API_KEY', '')),
        'unifi_site_id': SiteConfig.get('unifi_site_id', current_app.config.get('UNIFI_SITE_ID', 'default')),
        'guest_auth_minutes': SiteConfig.get('guest_auth_minutes', str(current_app.config.get('GUEST_AUTH_MINUTES', 480))),
    }
    return render_template('admin/settings_unifi.html', cfg=cfg, admin=_get_admin())


@bp.post('/settings/unifi')
@login_required
def settings_unifi_save():
    for k in ['unifi_base_url', 'unifi_api_key', 'unifi_site_id', 'guest_auth_minutes']:
        val = request.form.get(k)
        if val is not None:
            SiteConfig.set(k, val.strip())
    db.session.commit()
    flash('Configurações UniFi salvas!', 'success')
    return redirect(url_for('admin.settings_unifi'))


@bp.post('/settings/unifi/test')
@login_required
def settings_unifi_test():
    from app.services.unifi_api import UnifiAPI
    url = SiteConfig.get('unifi_base_url', current_app.config.get('UNIFI_BASE_URL', ''))
    key = SiteConfig.get('unifi_api_key', current_app.config.get('UNIFI_API_KEY', ''))
    try:
        api = UnifiAPI(url, key)
        sites = api.get_sites()
        flash(f'Conexão OK — {len(sites)} site(s) encontrado(s).', 'success')
    except Exception as exc:
        flash(f'Falha na conexão: {exc}', 'error')
    return redirect(url_for('admin.settings_unifi'))


# ---------------------------------------------------------------------------
# Usuarios admin
# ---------------------------------------------------------------------------

@bp.get('/users')
@login_required
def users():
    users_list = AdminUser.query.order_by(AdminUser.created_at.desc()).all()
    return render_template('admin/users.html', users=users_list, admin=_get_admin())


@bp.post('/users/create')
@login_required
def user_create():
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        flash('Usuário e senha são obrigatórios.', 'error')
        return redirect(url_for('admin.users'))
    if len(password) < 8:
        flash('A senha deve ter no mínimo 8 caracteres.', 'error')
        return redirect(url_for('admin.users'))
    if AdminUser.query.filter_by(username=username).first():
        flash('Nome de usuário já existe.', 'error')
        return redirect(url_for('admin.users'))
    u = AdminUser(username=username)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    flash(f'Usuário "{username}" criado com sucesso!', 'success')
    return redirect(url_for('admin.users'))


@bp.post('/users/<int:uid>/toggle')
@login_required
def user_toggle(uid):
    u = AdminUser.query.get_or_404(uid)
    if u.id == session['admin_id']:
        flash('Você não pode desativar sua própria conta.', 'error')
        return redirect(url_for('admin.users'))
    u.is_active = not u.is_active
    db.session.commit()
    flash(f'Usuário {"ativado" if u.is_active else "desativado"}.', 'success')
    return redirect(url_for('admin.users'))


@bp.post('/users/<int:uid>/password')
@login_required
def user_password(uid):
    u = AdminUser.query.get_or_404(uid)
    new_pw = request.form.get('new_password') or ''
    if len(new_pw) < 8:
        flash('A nova senha deve ter no mínimo 8 caracteres.', 'error')
        return redirect(url_for('admin.users'))
    u.set_password(new_pw)
    db.session.commit()
    flash(f'Senha de "{u.username}" alterada com sucesso!', 'success')
    return redirect(url_for('admin.users'))


@bp.post('/users/<int:uid>/delete')
@login_required
def user_delete(uid):
    u = AdminUser.query.get_or_404(uid)
    if u.id == session['admin_id']:
        flash('Você não pode excluir sua própria conta.', 'error')
        return redirect(url_for('admin.users'))
    if AdminUser.query.filter_by(is_active=True).count() <= 1 and u.is_active:
        flash('Não é possível excluir o único administrador ativo.', 'error')
        return redirect(url_for('admin.users'))
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuário "{u.username}" excluído.', 'success')
    return redirect(url_for('admin.users'))
