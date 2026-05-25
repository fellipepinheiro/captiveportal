from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.models import PortalSession
from app.services.portal_service import (
    create_or_update_pending_session,
    find_visitor,
    upsert_visitor,
    authorize_session,
    UnifiAuthError,
)

bp = Blueprint('portal', __name__)


@bp.get('/guest/s/default/')
def entry():
    portal_session = create_or_update_pending_session(
        ap_mac=request.args.get('ap'),
        client_mac=request.args.get('id'),
        ssid=request.args.get('ssid'),
        redirect_url=request.args.get('url'),
        token=request.args.get('t'),
    )
    session['portal_session_id'] = portal_session.id
    return render_template('portal/start.html', ssid=portal_session.ssid)


@bp.post('/guest/identify')
def identify():
    ps_id = session.get('portal_session_id')
    if not ps_id:
        flash('Sessao expirada. Por favor, reconecte-se ao Wi-Fi.', 'error')
        return redirect(url_for('portal.entry'))

    portal_session = PortalSession.query.get_or_404(ps_id)

    email = (request.form.get('email') or '').strip()
    mobile = (request.form.get('mobile') or '').strip()

    if not email or not mobile:
        flash('Preencha o e-mail e o telefone celular.', 'error')
        return render_template('portal/start.html', ssid=portal_session.ssid)

    visitor = find_visitor(email, mobile)
    if visitor:
        try:
            authorize_session(portal_session, visitor)
            return redirect(url_for('portal.success'))
        except UnifiAuthError as exc:
            flash(str(exc), 'error')
            return render_template('portal/start.html', ssid=portal_session.ssid)

    session['pending_email'] = email
    session['pending_mobile'] = mobile
    return render_template('portal/register.html', email=email, mobile=mobile)


@bp.post('/guest/register')
def register():
    ps_id = session.get('portal_session_id')
    if not ps_id:
        flash('Sessao expirada. Por favor, reconecte-se ao Wi-Fi.', 'error')
        return redirect(url_for('portal.entry'))

    portal_session = PortalSession.query.get_or_404(ps_id)

    full_name = (request.form.get('full_name') or '').strip()
    cpf = (request.form.get('cpf') or '').strip()

    if not full_name or not cpf:
        flash('Preencha o nome completo e o CPF.', 'error')
        return render_template('portal/register.html',
                               email=session.get('pending_email'),
                               mobile=session.get('pending_mobile'))

    visitor, _created = upsert_visitor(
        email=session.get('pending_email'),
        mobile=session.get('pending_mobile'),
        full_name=full_name,
        cpf=cpf,
    )

    try:
        authorize_session(portal_session, visitor)
        return redirect(url_for('portal.success'))
    except UnifiAuthError as exc:
        flash(str(exc), 'error')
        return render_template('portal/register.html',
                               email=session.get('pending_email'),
                               mobile=session.get('pending_mobile'))


@bp.get('/guest/success')
def success():
    return render_template('portal/success.html')
