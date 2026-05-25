from flask import Blueprint, render_template, request, session, redirect, url_for
from app.models import PortalSession
from app.services.portal_service import (
    create_or_update_pending_session,
    find_visitor,
    upsert_visitor,
    authorize_session,
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
    portal_session = PortalSession.query.get_or_404(session.get('portal_session_id'))

    email = request.form.get('email')
    mobile = request.form.get('mobile')

    visitor = find_visitor(email, mobile)
    if visitor:
        authorize_session(portal_session, visitor)
        return redirect(url_for('portal.success'))

    session['pending_email'] = email
    session['pending_mobile'] = mobile
    return render_template('portal/register.html', email=email, mobile=mobile)


@bp.post('/guest/register')
def register():
    portal_session = PortalSession.query.get_or_404(session.get('portal_session_id'))

    visitor, _created = upsert_visitor(
        email=session.get('pending_email'),
        mobile=session.get('pending_mobile'),
        full_name=request.form.get('full_name'),
        cpf=request.form.get('cpf'),
    )

    authorize_session(portal_session, visitor)
    return redirect(url_for('portal.success'))


@bp.get('/guest/success')
def success():
    return render_template('portal/success.html')
