"""Agregacoes de comportamento de uso do hotspot.

Todas as consultas partem do mesmo filtro (loja + periodo + cliente), para
que os KPIs e os graficos da tela contem sempre a mesma historia.

Nota sobre fuso: os timestamps sao gravados em UTC. O periodo escolhido na
tela chega em hora local e e convertido antes da consulta; ja os cortes por
dia e por hora (tendencia, heatmap) precisam agrupar em hora local, senao
um acesso das 22h aparece no dia seguinte. Por isso o agrupamento e feito
em Python sobre as linhas do periodo, e nao com CAST(... AS DATE) no SQL.
"""
from collections import Counter, defaultdict
from datetime import timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import PortalSession, Visitor, Store
from app.services.datetime_fmt import get_tz

DIAS_SEMANA = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']


def _base_query(inicio, fim, store_id=None, visitor_id=None):
    q = (
        PortalSession.query
        .filter(PortalSession.created_at >= inicio, PortalSession.created_at < fim)
    )
    if store_id:
        q = q.filter(PortalSession.store_id == store_id)
    if visitor_id:
        q = q.filter(PortalSession.visitor_id == visitor_id)
    return q


def _local(dt):
    """UTC -> fuso local, tolerando datetimes naive vindos do MySQL."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_tz())


def coletar(inicio, fim, de, ate, store_id=None, visitor_id=None) -> dict:
    """Monta todos os indicadores do periodo em uma unica passada.

    `inicio`/`fim` sao os limites em UTC; `de`/`ate` sao as datas locais,
    usadas para montar o eixo do grafico de tendencia.
    """
    sessoes = _base_query(inicio, fim, store_id, visitor_id).all()

    # Conexao efetiva = acesso que chegou a ser autorizado. O resto e
    # gente que abriu o portal e desistiu — util para medir conversao,
    # mas nao entra nas metricas de consumo.
    conexoes = [s for s in sessoes if s.authorized_at]
    duracoes = [s.duration for s in conexoes if s.duration is not None]
    bytes_down = sum(s.bytes_down or 0 for s in conexoes)
    bytes_up = sum(s.bytes_up or 0 for s in conexoes)

    visitantes = {s.visitor_id for s in conexoes if s.visitor_id}

    # Novo x recorrente: o visitante e "novo" se o cadastro dele nasceu
    # dentro do periodo analisado.
    novos = 0
    if visitantes:
        novos = (
            Visitor.query
            .filter(Visitor.id.in_(visitantes))
            .filter(Visitor.created_at >= inicio, Visitor.created_at < fim)
            .count()
        )

    # ── Tendencia diaria (em hora local) ──────────────────────────────
    por_dia = defaultdict(lambda: {'acessos': 0, 'conexoes': 0, 'visitantes': set()})
    for s in sessoes:
        d = _local(s.created_at).date()
        por_dia[d]['acessos'] += 1
        if s.authorized_at:
            por_dia[d]['conexoes'] += 1
            if s.visitor_id:
                por_dia[d]['visitantes'].add(s.visitor_id)

    eixo = []
    dia = de
    while dia <= ate:
        eixo.append(dia)
        dia += timedelta(days=1)

    tendencia = {
        'labels':     [d.strftime('%d/%m') for d in eixo],
        'acessos':    [por_dia[d]['acessos'] for d in eixo],
        'conexoes':   [por_dia[d]['conexoes'] for d in eixo],
        'visitantes': [len(por_dia[d]['visitantes']) for d in eixo],
    }

    # ── Horarios de pico: dia da semana x hora ────────────────────────
    # Mostra quando a loja recebe movimento — a leitura mais acionavel
    # do relatorio para quem escala equipe ou programa promocoes.
    heat = Counter()
    for s in conexoes:
        L = _local(s.authorized_at or s.created_at)
        heat[(L.weekday(), L.hour)] += 1
    heatmap = [[h, d, heat.get((d, h), 0)] for d in range(7) for h in range(24)]

    por_hora = [0] * 24
    for (_, h), n in heat.items():
        por_hora[h] += n

    # ── Distribuicao de permanencia ───────────────────────────────────
    faixas = [
        ('até 5 min',   lambda m: m < 5),
        ('5–15 min',    lambda m: 5 <= m < 15),
        ('15–30 min',   lambda m: 15 <= m < 30),
        ('30–60 min',   lambda m: 30 <= m < 60),
        ('1–2 h',       lambda m: 60 <= m < 120),
        ('mais de 2 h', lambda m: m >= 120),
    ]
    permanencia = [
        {'name': rotulo, 'value': sum(1 for m in duracoes if teste(m))}
        for rotulo, teste in faixas
    ]

    # ── Rankings ──────────────────────────────────────────────────────
    por_loja = defaultdict(lambda: {'conexoes': 0, 'visitantes': set(), 'bytes': 0, 'minutos': 0})
    for s in conexoes:
        nome = s.store.name if s.store else 'Sem loja'
        r = por_loja[nome]
        r['conexoes'] += 1
        if s.visitor_id:
            r['visitantes'].add(s.visitor_id)
        r['bytes'] += (s.bytes_down or 0) + (s.bytes_up or 0)
        r['minutos'] += s.duration or 0
    lojas = sorted(
        ({'loja': k,
          'conexoes': v['conexoes'],
          'visitantes': len(v['visitantes']),
          'bytes': v['bytes'],
          'minutos': v['minutos']} for k, v in por_loja.items()),
        key=lambda x: -x['conexoes'],
    )

    por_visitante = defaultdict(lambda: {'conexoes': 0, 'bytes': 0, 'minutos': 0, 'ultima': None})
    for s in conexoes:
        if not s.visitor_id:
            continue
        r = por_visitante[s.visitor_id]
        r['conexoes'] += 1
        r['bytes'] += (s.bytes_down or 0) + (s.bytes_up or 0)
        r['minutos'] += s.duration or 0
        quando = s.authorized_at or s.created_at
        if r['ultima'] is None or quando > r['ultima']:
            r['ultima'] = quando

    nomes = {}
    if por_visitante:
        for v in Visitor.query.filter(Visitor.id.in_(por_visitante.keys())).all():
            nomes[v.id] = v.full_name
    clientes = [
        {'id': vid, 'nome': nomes.get(vid, '—'), **{k: v for k, v in r.items() if k != 'ultima'},
         'ultima': r['ultima']}
        for vid, r in por_visitante.items()
    ]
    top_consumo = sorted(clientes, key=lambda c: -c['bytes'])[:10]
    top_frequencia = sorted(clientes, key=lambda c: -c['conexoes'])[:10]

    # ── Frequencia de visita ──────────────────────────────────────────
    # Quantos vieram uma vez so e quantos voltaram: mede fidelizacao.
    freq = Counter(c['conexoes'] for c in clientes)
    frequencia = [
        {'name': '1 visita',     'value': freq.get(1, 0)},
        {'name': '2 visitas',    'value': freq.get(2, 0)},
        {'name': '3–5 visitas',  'value': sum(n for k, n in freq.items() if 3 <= k <= 5)},
        {'name': '6+ visitas',   'value': sum(n for k, n in freq.items() if k >= 6)},
    ]

    # ── Origem dos visitantes ─────────────────────────────────────────
    # Amostra parcial por natureza: so entra quem autorizou a localizacao
    # no navegador. A taxa de captura vai junto para nao ler os numeros
    # como se representassem todo o publico.
    com_local = [s for s in conexoes if s.latitude is not None and s.longitude is not None]
    pontos = [
        {'lat': float(s.latitude), 'lon': float(s.longitude),
         'precisao': s.location_accuracy, 'km': s.distancia_da_loja}
        for s in com_local
    ]
    distancias = sorted(p['km'] for p in pontos if p['km'] is not None)
    faixas_km = [
        ('até 1 km',    lambda d: d < 1),
        ('1–5 km',      lambda d: 1 <= d < 5),
        ('5–20 km',     lambda d: 5 <= d < 20),
        ('20–50 km',    lambda d: 20 <= d < 50),
        ('mais de 50 km', lambda d: d >= 50),
    ]
    origem = {
        'pontos':        pontos,
        'capturadas':    len(com_local),
        'taxa_captura':  round(len(com_local) / len(conexoes) * 100, 1) if conexoes else 0,
        'com_distancia': len(distancias),
        'km_medio':      round(sum(distancias) / len(distancias), 1) if distancias else 0,
        'km_mediana':    distancias[len(distancias) // 2] if distancias else 0,
        'faixas': [
            {'name': rotulo, 'value': sum(1 for d in distancias if teste(d))}
            for rotulo, teste in faixas_km
        ],
    }

    dispositivos = Counter((s.device_type or 'Desconhecido') for s in conexoes)
    sistemas = Counter((s.os_hint or 'Desconhecido') for s in conexoes)

    total_acessos = len(sessoes)
    total_conexoes = len(conexoes)
    return {
        'kpis': {
            'acessos':        total_acessos,
            'conexoes':       total_conexoes,
            'conversao':      round(total_conexoes / total_acessos * 100, 1) if total_acessos else 0,
            'visitantes':     len(visitantes),
            'novos':          novos,
            'recorrentes':    len(visitantes) - novos,
            'taxa_retorno':   round((len(visitantes) - novos) / len(visitantes) * 100, 1) if visitantes else 0,
            'minutos_total':  sum(duracoes),
            'minutos_medio':  round(sum(duracoes) / len(duracoes)) if duracoes else 0,
            'minutos_mediana': sorted(duracoes)[len(duracoes) // 2] if duracoes else 0,
            'bytes_down':     bytes_down,
            'bytes_up':       bytes_up,
            'bytes_total':    bytes_down + bytes_up,
            'bytes_medio':    round((bytes_down + bytes_up) / total_conexoes) if total_conexoes else 0,
        },
        'origem':        origem,
        'tendencia':     tendencia,
        'heatmap':       heatmap,
        'por_hora':      por_hora,
        'permanencia':   permanencia,
        'frequencia':    frequencia,
        'lojas':         lojas,
        'top_consumo':   top_consumo,
        'top_frequencia': top_frequencia,
        'dispositivos':  [{'name': k, 'value': v} for k, v in dispositivos.most_common()],
        'sistemas':      [{'name': k, 'value': v} for k, v in sistemas.most_common()],
    }
