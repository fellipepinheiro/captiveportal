from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect,
    session, url_for, flash, current_app, jsonify
)
from sqlalchemy.exc import IntegrityError
from app.extensions import db, limiter, csrf
from app.models import Visitor, PortalSession, Store
from app.models.site_config import SiteConfig
from app.services.portal_service import (
    create_pending_session, authorize_visitor, record_consent, refresh_consent,
    log_acesso
)
from app.services.validator import format_cpf, format_phone
from app.services import form_service

bp = Blueprint("portal", __name__)
PORTAL_SESSION_KEY = "portal_session_id"

_DEFAULT_CFG = {
    "portal_title":    "Wi-Fi Visitantes",
    "portal_welcome":  "Identifique-se para acessar a internet.",
    "portal_btn_color": "#0f766e",
    "portal_accent":   "#14b8a6",
    "portal_bg_from":  "#0f172a",
    "portal_bg_via":   "#1e1b4b",
    "portal_bg_to":    "#0f172a",
}


def _portal_cfg() -> dict:
    """Carrega configurações de aparência + logo do banco."""
    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        val = SiteConfig.get(key)
        if val is not None:
            cfg[key] = val
    cfg["custom_logo_url"] = SiteConfig.get("custom_logo_url") or ""
    cfg["logo_title"]      = SiteConfig.get("logo_title") or ""
    return cfg


def _get_portal_session():
    sid = session.get(PORTAL_SESSION_KEY)
    if not sid:
        return None
    return PortalSession.query.get(sid)


def _get_session_store(portal_session):
    if not portal_session or not portal_session.store_id:
        return None
    return Store.query.get(portal_session.store_id)


def _resolve_store(slug: str):
    """Resolve a loja pelo slug da URL configurada no Hotspot Manager do UDM Pro.

    Cai para a loja 'default' se o slug nao existir/estiver inativo, para nao
    quebrar acessos com URL desatualizada.
    """
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if store:
        return store
    if slug != "default":
        return Store.query.filter_by(slug="default", is_active=True).first()
    return None


def _destino(store, portal_session) -> str:
    """Para onde mandar o visitante depois do acesso liberado.

    A loja pode fixar um destino (site, promocao); sem isso ele volta para
    a pagina que tentava abrir, que e o que a pessoa espera.
    """
    if store:
        return store.destino(portal_session.redirect_url)
    return portal_session.redirect_url or "http://google.com"


def _tela_login(erros=None, aviso=None, ssid=None):
    """Reexibe a identificacao mantendo o que o visitante ja digitou.

    Antes cada erro fazia redirect, o que limpava o formulario e obrigava a
    redigitar tudo — em teclado de celular, motivo suficiente para desistir
    do acesso.
    """
    return render_template(
        "portal/start.html",
        ssid=ssid or request.form.get("ssid") or "WiFi",
        campos=form_service.campos("login"),
        erros=erros or {},
        aviso=aviso,
        valores=request.form,
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        **_portal_cfg(),
    )


def _tela_cadastro(erros=None, aviso=None):
    """Reexibe o cadastro mantendo o que ja foi preenchido."""
    informados = []
    for campo in form_service.campos("login"):
        valor = (session.get("reg_login") or {}).get(campo.key)
        if not valor:
            continue
        if campo.field_type == "cpf":
            valor = format_cpf(valor)
        elif campo.field_type == "phone":
            valor = format_phone(valor)
        informados.append({"label": campo.label, "valor": valor})

    return render_template(
        "portal/register.html",
        campos=form_service.campos("signup"),
        informados=informados,
        erros=erros or {},
        aviso=aviso,
        valores=request.form,
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        terms_version=current_app.config.get("TERMS_VERSION", "1.0"),
        **_portal_cfg(),
    )


@bp.get("/guest/s/<slug>/")
@bp.get("/guest/")
@csrf.exempt
def entry(slug="default"):
    client_mac   = request.args.get("id") or request.args.get("mac")
    ap_mac       = request.args.get("ap")
    ssid         = request.args.get("ssid", "WiFi")
    redirect_url = request.args.get("url", "http://google.com")
    store        = _resolve_store(slug)

    if client_mac:
        portal_session = create_pending_session(client_mac, ap_mac, ssid, redirect_url, store)
        session[PORTAL_SESSION_KEY] = portal_session.id
    else:
        session[PORTAL_SESSION_KEY] = None
        session.modified = True

    return render_template(
        "portal/start.html",
        ssid=ssid,
        campos=form_service.campos("login"),
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        **_portal_cfg(),
    )


@bp.post("/guest/identify")
@csrf.exempt
@limiter.limit("10 per minute")
def identify():
    portal_session = _get_portal_session()
    if not portal_session:
        log_acesso("ACESSO_NEGADO", "SESSAO_EXPIRADA")
        flash("A tela ficou aberta tempo demais. Desligue e ligue o Wi-Fi "
              "do aparelho para recomeçar.", "error")
        return redirect(url_for("portal.entry"))

    valores, erros = form_service.coletar("login", request.form)
    if not request.form.get("terms_accepted"):
        erros["terms_accepted"] = "Aceite os Termos de Uso para continuar."
    if erros:
        log_acesso("ACESSO_NEGADO", "VALIDACAO", portal_session,
                   detalhe="; ".join(f"{k}: {v}" for k, v in erros.items()))
        return _tela_login(erros=erros)

    # A chave define quem e o visitante recorrente; o admin escolhe qual e.
    chave = form_service.campo_chave()
    valor_chave = valores.get(chave.key)
    if not valor_chave:
        log_acesso("ACESSO_NEGADO", "VALIDACAO", portal_session,
                   detalhe=f"campo-chave {chave.key} ausente")
        return _tela_login(erros={chave.key: f"{chave.label} é obrigatório."})

    visitor = Visitor.query.filter(
        getattr(Visitor, chave.coluna) == valor_chave
    ).first() if chave.coluna else None

    if visitor:
        if visitor.is_blocked:
            log_acesso("ACESSO_NEGADO", "VISITANTE_BLOQUEADO", portal_session, visitor,
                       detalhe=visitor.block_reason)
            motivo = visitor.block_reason or "não informado"
            return _tela_login(aviso=(
                "Seu acesso está bloqueado neste local. "
                f"Motivo: {motivo}. Procure um atendente para liberar."))

        # Os demais campos do login sao complementares: atualizam o cadastro
        # quando mudam, mas nunca sobrescrevem valor que ja e de outra pessoa.
        for campo in form_service.campos("login"):
            if campo.key == chave.key or campo.key not in valores:
                continue
            coluna = campo.coluna
            novo = valores[campo.key]
            if coluna and getattr(visitor, coluna) != novo:
                em_uso = Visitor.query.filter(
                    getattr(Visitor, coluna) == novo, Visitor.id != visitor.id
                ).first()
                if not em_uso:
                    setattr(visitor, coluna, novo)
            elif not coluna:
                extras = visitor.extras
                extras[campo.key] = novo
                visitor.set_extras(extras)
        db.session.commit()

        # Ele marcou o aceite agora; se os termos mudaram desde o cadastro,
        # o registro precisa refletir a versao que ele de fato aceitou.
        refresh_consent(visitor, current_app.config.get("TERMS_VERSION", "1.0"))

        store = _get_session_store(portal_session)
        ok = authorize_visitor(portal_session, visitor, store)
        if ok:
            log_acesso("ACESSO_LIBERADO", portal_session=portal_session, visitor=visitor)
            return render_template(
                "portal/success.html",
                redirect_url=_destino(store, portal_session),
                name=visitor.full_name,
                **_portal_cfg(),
            )
        log_acesso("ACESSO_NEGADO", "UNIFI_FALHOU", portal_session, visitor)
        return _tela_login(aviso=(
            "Seus dados foram reconhecidos, mas a rede não liberou o acesso. "
            "Desligue e ligue o Wi-Fi do aparelho e tente de novo; "
            "se persistir, avise um atendente."))

    session["reg_login"] = valores
    return redirect(url_for("portal.register"))


@bp.get("/guest/cadastro")
@csrf.exempt
def register():
    if not session.get("reg_login"):
        return redirect(url_for("portal.entry"))
    portal_session = _get_portal_session()
    if not portal_session:
        return redirect(url_for("portal.entry"))

    return _tela_cadastro()


@bp.post("/guest/localizacao")
@csrf.exempt
@limiter.limit("20 per minute")
def registrar_localizacao():
    """Recebe a posicao informada pelo navegador do visitante.

    Chamado da tela de sucesso, depois que o acesso ja foi liberado: a
    coleta nao pode atrasar nem condicionar a entrada na internet. Quem
    recusa a permissao simplesmente nao envia nada.
    """
    portal_session = _get_portal_session()
    if not portal_session:
        return jsonify({"ok": False}), 204

    dados = request.get_json(silent=True) or {}
    try:
        lat = float(dados.get("lat"))
        lon = float(dados.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "erro": "coordenadas invalidas"}), 400

    # Fora destas faixas nao e coordenada valida — descarta em vez de gravar
    # sujeira que depois apareceria como ponto perdido no mapa.
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"ok": False, "erro": "coordenadas fora de faixa"}), 400

    try:
        precisao = int(float(dados.get("precisao") or 0))
    except (TypeError, ValueError):
        precisao = 0

    portal_session.latitude = lat
    portal_session.longitude = lon
    portal_session.location_accuracy = precisao or None
    portal_session.location_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/guest/cadastro")
@csrf.exempt
@limiter.limit("5 per minute")
def register_submit():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("A tela ficou aberta tempo demais. Desligue e ligue o Wi-Fi "
              "do aparelho para recomeçar.", "error")
        return redirect(url_for("portal.entry"))

    dados_login = session.get("reg_login") or {}
    marketing_optin = bool(request.form.get("marketing_optin"))
    terms_version   = current_app.config.get("TERMS_VERSION", "1.0")

    valores, erros = form_service.coletar("signup", request.form)
    if erros:
        log_acesso("CADASTRO_NEGADO", "VALIDACAO", portal_session,
                   detalhe="; ".join(f"{k}: {v}" for k, v in erros.items()))
        return _tela_cadastro(erros=erros)

    chave = form_service.campo_chave()
    valor_chave = dados_login.get(chave.key)
    if not valor_chave or not chave.coluna:
        log_acesso("CADASTRO_NEGADO", "SESSAO_EXPIRADA", portal_session)
        flash("A tela ficou aberta tempo demais e seus dados se perderam. "
              "Informe novamente para continuar.", "error")
        return redirect(url_for("portal.entry"))

    def busca():
        return Visitor.query.filter(getattr(Visitor, chave.coluna) == valor_chave).first()

    visitor = busca()
    created = False
    if visitor is None:
        visitor = Visitor(terms_version=terms_version, marketing_optin=marketing_optin,
                          visit_count=1)
        # Os campos da identificacao e do cadastro sao gravados pela mesma
        # regra: coluna propria quando existe, extra_data quando nao.
        form_service.aplicar(visitor, dados_login, "login")
        form_service.aplicar(visitor, valores, "signup")
        db.session.add(visitor)
        try:
            db.session.flush()
            created = True
        except IntegrityError:
            db.session.rollback()
            visitor = busca()
            if visitor is None:
                log_acesso("CADASTRO_NEGADO", "ERRO_CADASTRO", portal_session)
                return _tela_cadastro(aviso=(
                    f"Não foi possível concluir o cadastro. Verifique se o "
                    f"{chave.label.lower()} informado já não está em uso por outra pessoa."))
    else:
        form_service.aplicar(visitor, valores, "signup")

    if created:
        record_consent(visitor, marketing_optin=marketing_optin, version=terms_version)

    db.session.commit()

    store = _get_session_store(portal_session)
    ok = authorize_visitor(portal_session, visitor, store)
    session.pop("reg_login", None)

    if ok:
        log_acesso("ACESSO_LIBERADO", portal_session=portal_session, visitor=visitor)
        return render_template(
            "portal/success.html",
            redirect_url=_destino(store, portal_session),
            name=visitor.full_name,
            **_portal_cfg(),
        )
    log_acesso("ACESSO_NEGADO", "UNIFI_FALHOU", portal_session, visitor)
    flash("Cadastro concluído, mas a rede não liberou o acesso. Seus dados já "
          "estão salvos: desligue e ligue o Wi-Fi e informe-se novamente. "
          "Se persistir, avise um atendente.", "error")
    return redirect(url_for("portal.entry"))
