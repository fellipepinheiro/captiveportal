import os
from datetime import datetime
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app, jsonify
)
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import AdminUser, SiteConfig, Visitor, PortalSession, AuditLog
from app.services.unifi_api import UnifiAPI

bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'webp'}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@bp.get('/login')
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html')


@bp.post('/login')
def login_post():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if user and user.check_password(password):
        session['admin_logged_in'] = True
        session['admin_username'] = username
        user.last_login = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('admin.dashboard'))

    flash('Usuário ou senha incorretos.', 'error')
    return render_template('admin/login.html')


@bp.get('/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin.login'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bp.get('/')
@login_required
def dashboard():
    total_visitors = Visitor.query.count()
    total_sessions = PortalSession.query.filter_by(authorized=True).count()
    today = datetime.utcnow().date()
    today_sessions = PortalSession.query.filter(
        PortalSession.authorized == True,
        db.func.date(PortalSession.authorized_at) == today
    ).count()
    errors_today = AuditLog.query.filter(
        AuditLog.status == 'error',
        db.func.date(AuditLog.created_at) == today
    ).count()
    recent_logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
        total_visitors=total_visitors,
        total_sessions=total_sessions,
        today_sessions=today_sessions,
        errors_today=errors_today,
        recent_logs=recent_logs,
    )


# ---------------------------------------------------------------------------
# Aparência
# ---------------------------------------------------------------------------

@bp.get('/appearance')
@login_required
def appearance():
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    return render_template('admin/appearance.html',
        has_logo=os.path.exists(logo_path),
        title=SiteConfig.get('portal_title', 'Portal Wi-Fi UniFi'),
        welcome=SiteConfig.get('portal_welcome', 'Preencha seus dados para liberar o acesso à internet.'),
        btn_color=SiteConfig.get('portal_btn_color', '#0f766e'),
    )


@bp.post('/appearance/save')
@login_required
def appearance_save():
    SiteConfig.set('portal_title', request.form.get('portal_title', '').strip())
    SiteConfig.set('portal_welcome', request.form.get('portal_welcome', '').strip())
    SiteConfig.set('portal_btn_color', request.form.get('portal_btn_color', '#0f766e').strip())
    db.session.commit()
    flash('Aparência salva com sucesso!', 'success')
    return redirect(url_for('admin.appearance'))


@bp.post('/logo/upload')
@login_required
def upload_logo():
    file = request.files.get('logo')
    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin.appearance'))
    if not _allowed(file.filename):
        flash('Formato não permitido. Use PNG, JPG, SVG ou WEBP.', 'error')
        return redirect(url_for('admin.appearance'))
    file.seek(0, 2)
    if file.tell() > 2 * 1024 * 1024:
        flash('Arquivo muito grande. Máximo 2 MB.', 'error')
        return redirect(url_for('admin.appearance'))
    file.seek(0)
    uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    file.save(os.path.join(uploads_dir, 'logo.png'))
    flash('Logo atualizada!', 'success')
    return redirect(url_for('admin.appearance'))


@bp.post('/logo/remove')
@login_required
def remove_logo():
    logo_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logo.png')
    if os.path.exists(logo_path):
        os.remove(logo_path)
        flash('Logo removida.', 'success')
    return redirect(url_for('admin.appearance'))


# ---------------------------------------------------------------------------
# Configurações UniFi
# ---------------------------------------------------------------------------

@bp.get('/unifi')
@login_required
def unifi():
    return render_template('admin/unifi.html',
        base_url=SiteConfig.get('unifi_base_url') or current_app.config.get('UNIFI_BASE_URL', ''),
        api_key=SiteConfig.get('unifi_api_key') or current_app.config.get('UNIFI_API_KEY', ''),
        site_id=SiteConfig.get('unifi_site_id') or current_app.config.get('UNIFI_SITE_ID', 'default'),
        auth_minutes=SiteConfig.get('guest_auth_minutes') or current_app.config.get('GUEST_AUTH_MINUTES', 480),
        allow_revisit=SiteConfig.get('allow_revisit', 'true'),
    )


@bp.post('/unifi/save')
@login_required
def unifi_save():
    SiteConfig.set('unifi_base_url', request.form.get('base_url', '').strip())
    SiteConfig.set('unifi_api_key', request.form.get('api_key', '').strip())
    SiteConfig.set('unifi_site_id', request.form.get('site_id', '').strip())
    SiteConfig.set('guest_auth_minutes', request.form.get('auth_minutes', '480').strip())
    SiteConfig.set('allow_revisit', 'true' if request.form.get('allow_revisit') else 'false')
    db.session.commit()
    flash('Configurações UniFi salvas!', 'success')
    return redirect(url_for('admin.unifi'))


@bp.post('/unifi/test')
@login_required
def unifi_test():
    base_url = request.json.get('base_url', '')
    api_key = request.json.get('api_key', '')
    try:
        api = UnifiAPI(base_url, api_key)
        sites = api.get_sites()
        return jsonify({'ok': True, 'sites': sites})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200


# ---------------------------------------------------------------------------
# Visitantes
# ---------------------------------------------------------------------------

@bp.get('/visitors')
@login_required
def visitors():
    q = request.args.get('q', '').strip()
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
    pagination = query.order_by(Visitor.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/visitors.html', pagination=pagination, q=q)


@bp.get('/visitors/<int:visitor_id>')
@login_required
def visitor_detail(visitor_id):
    visitor = Visitor.query.get_or_404(visitor_id)
    sessions = PortalSession.query.filter_by(visitor_id=visitor_id).order_by(PortalSession.id.desc()).limit(20).all()
    return render_template('admin/visitor_detail.html', visitor=visitor, sessions=sessions)


@bp.post('/visitors/<int:visitor_id>/toggle')
@login_required
def visitor_toggle(visitor_id):
    visitor = Visitor.query.get_or_404(visitor_id)
    visitor.is_active = not visitor.is_active
    db.session.commit()
    status = 'ativado' if visitor.is_active else 'bloqueado'
    flash(f'Visitante {status} com sucesso.', 'success')
    return redirect(url_for('admin.visitors'))


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@bp.get('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    query = AuditLog.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if date_filter:
        try:
            d = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(AuditLog.created_at) == d)
        except ValueError:
            pass
    pagination = query.order_by(AuditLog.id.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template('admin/logs.html', pagination=pagination,
                           status_filter=status_filter, date_filter=date_filter)


# ---------------------------------------------------------------------------
# Segurança — trocar senha
# ---------------------------------------------------------------------------

@bp.get('/security')
@login_required
def security():
    user = AdminUser.query.filter_by(username=session['admin_username']).first()
    return render_template('admin/security.html', user=user)


@bp.post('/security/password')
@login_required
def security_password():
    user = AdminUser.query.filter_by(username=session['admin_username']).first()
    current = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    if not user.check_password(current):
        flash('Senha atual incorreta.', 'error')
        return redirect(url_for('admin.security'))
    if len(new_pw) < 8:
        flash('A nova senha deve ter ao menos 8 caracteres.', 'error')
        return redirect(url_for('admin.security'))
    if new_pw != confirm:
        flash('As senhas não coincidem.', 'error')
        return redirect(url_for('admin.security'))

    user.set_password(new_pw)
    db.session.commit()
    flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('admin.security'))
