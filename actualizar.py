# Monitor del Congreso: baja votaciones de la Camara y el Senado desde el 11-03-2026 y arma datos/congreso.json y datos/proyectos.json
# Uso: python actualizar.py [--forzar]. Sin --forzar corre desde las 6 (hora de Chile) si hoy no se ha actualizado.
import json, re, sys, os, time, urllib.request, datetime as dt
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import numpy as np

DIR = os.path.dirname(os.path.abspath(__file__))
CACHE, OUT = os.path.join(DIR, 'cache'), os.path.join(DIR, 'datos')
DESDE = dt.date(2026, 3, 11)
CL = ZoneInfo('America/Santiago')
WSC = 'https://opendata.camara.cl/camaradiputados/WServices/'
NS = '{http://opendata.camara.cl/camaradiputados/v1}'
SEN = 'https://web-back.senado.cl/api/'
TRAM = 'https://tramitacion.senado.cl/wspublico/tramitacion.php?boletin='
PARTIDOS_SEN = {'R.N.': 'RN', 'P.S.': 'PS', 'U.D.I.': 'UDI', 'P.P.D.': 'PPD', 'P.D.C.': 'DC', 'P.C': 'PC', 'P.C.': 'PC', 'Republicano': 'PREP', 'Evópoli': 'EVOP', 'Frente Amplio': 'FA', 'F.R.E.V.S.': 'FRVS', 'Demócratas': 'DEM', 'Nacional Libertario': 'PNL', 'Liberal': 'PL', 'Independiente': 'IND', 'P.R.': 'PR', 'Social Cristiano': 'PSC', 'De la Gente': 'PDG'}

TIPOS_SEN = (('Acusación constitucional', r'acusaci[oó]n constitucional'), ('Designación', r'designaci|nombramiento|proposici[oó]n .*para (designar|nombrar)'), ('Proyecto de Acuerdo', r'proyecto de acuerdo'), ('Oficio presidencial', r'(oficio|solicitud).*(presidente|vicepresidente) de la rep'))
PROMPT_ALIAS = ('Eres editor de un sitio que muestra las votaciones del Congreso de Chile. Para cada texto oficial (nombre de un proyecto de ley o descripción de una votación) '
                'escribe un alias en español de Chile que diga de qué trata, para un lector general: de 2 a 7 palabras, sin punto final, sin siglas que no sean de uso común, '
                'sin números de ley ni de boletín, sin verbos como "modifica" o "establece". Ejemplos: "Presupuesto 2027", "Prohibición de las carreras de perros", '
                '"Acusación constitucional contra Nicolás Grau". Si el texto no dice de qué trata (por ejemplo, "Artículo 39, aprobado"), devuelve el alias vacío. Devuelve un alias por cada clave recibida.')

def get(url, intentos=4):
    for i in range(intentos):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'monitor-congreso/1.0'}), timeout=120)
            return r.read()
        except Exception as e:
            if i == intentos - 1: raise
            time.sleep(3 * (i + 1))

def leer(nombre, defecto):
    p = os.path.join(CACHE, nombre)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else defecto

def guardar(ruta, obj, compacto=True):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':') if compacto else None)

def t(e, tag):
    x = e.find(NS + tag)
    return (x.text or '').strip() if x is not None else ''

def nombre_propio(s):
    return ' '.join(w if w in ('de', 'del', 'la', 'las', 'los', 'y') else w[:1].upper() + w[1:] for w in s.lower().split())

def bol_norm(b):
    m = re.search(r'(\d[\d.]*)\s*-\s*(\d+)', b or '')
    return f"{m.group(1).replace('.', '')}-{m.group(2).zfill(2)}" if m else None

# ---------- Camara ----------
def camara():
    x = ET.fromstring(get(WSC + 'WSDiputado.asmx/retornarDiputadosPeriodoActual'))
    parl = {}
    for dp in x.iter(NS + 'DiputadoPeriodo'):
        d = dp.find(NS + 'Diputado'); i = t(d, 'Id')
        mil = sorted([(t(m, 'FechaInicio'), m) for m in d.iter(NS + 'Militancia')], key=lambda z: z[0])
        p = mil[-1][1].find(NS + 'Partido') if mil else None
        parl[i] = {'n': nombre_propio(f"{t(d, 'Nombre')} {t(d, 'ApellidoPaterno')} {t(d, 'ApellidoMaterno')}"),
                   'p': t(p, 'Alias') if p is not None else 'S/I', 'pn': t(p, 'Nombre') if p is not None else '',
                   's': 'M' if t(d, 'Sexo').startswith('Fem') else 'H', 'r': 1}
    cache = leer('camara.json', {})
    lista = []
    for anno in range(2026, dt.datetime.now(CL).year + 1):
        for v in ET.fromstring(get(f'{WSC}WSLegislativo.asmx/retornarVotacionesXAnno?prmAnno={anno}')).iter(NS + 'Votacion'):
            if t(v, 'Fecha')[:10] >= DESDE.isoformat(): lista.append(v)
    nuevos = [t(v, 'Id') for v in lista if t(v, 'Id') not in cache]
    print('Camara:', len(lista), 'votaciones,', len(nuevos), 'nuevas')
    def detalle(i):
        d = ET.fromstring(get(f'{WSC}WSLegislativo.asmx/retornarVotacionDetalle?prmVotacionId={i}'))
        votos = {}
        for vo in d.iter(NS + 'Voto'):
            di = vo.find(NS + 'Diputado'); o = t(vo, 'OpcionVoto').lower()
            votos[t(di, 'Id')] = 's' if o.startswith('afirm') else 'n' if 'contra' in o else 'a' if o.startswith('abst') else 'p' if ('dispens' in o or 'pareo' in o) else '-'
            if t(di, 'Id') not in parl: parl[t(di, 'Id')] = {'n': nombre_propio(f"{t(di, 'Nombre')} {t(di, 'ApellidoPaterno')} {t(di, 'ApellidoMaterno')}"), 'p': 'S/I', 'pn': '', 's': '', 'r': 0}
        return i, votos
    with ThreadPoolExecutor(4) as ex:
        for k, (i, votos) in enumerate(ex.map(detalle, nuevos)):
            cache[i] = {'v': votos}
            if k % 200 == 199: print('  detalle', k + 1); guardar(os.path.join(CACHE, 'camara.json'), cache)
    # diputados que votaron y no estan en la nomina actual
    for c in cache.values():
        for i in c['v']:
            if i not in parl: parl[i] = {'n': f'Diputado {i}', 'p': 'S/I', 'pn': '', 's': '', 'r': 0}
    # articulo votado y tramite, desde la ficha del proyecto (solo boletines con votaciones nuevas)
    nuevos_set = set(nuevos)
    bols = {bol_norm(t(v, 'Descripcion')) for v in lista if t(v, 'Id') in nuevos_set and t(v, 'Descripcion').startswith('Bolet')} - {None}
    fichas = leer('camara_proyectos.json', {})
    def ficha(b):
        try: return b, ET.fromstring(get(f'{WSC}WSLegislativo.asmx/retornarProyectoLey?prmNumeroBoletin={b}'))
        except Exception as e: print('  sin ficha', b, e); return b, None
    with ThreadPoolExecutor(4) as ex:
        for b, x in ex.map(ficha, sorted(bols)):
            if x is None: continue
            fichas[b] = {'nombre': t(x, 'Nombre'), 'ministerio': ', '.join(t(m, 'Nombre') for m in x.iter(NS + 'Ministerio'))}
            for vp in x.iter(NS + 'VotacionProyectoLey'):
                i = t(vp, 'Id')
                if i in cache: cache[i].update({'art': t(vp, 'Articulo'), 'tr': t(vp, 'TramiteConstitucional'), 'tv': t(vp, 'TipoVotacionProyectoLey')})
    guardar(os.path.join(CACHE, 'camara.json'), cache); guardar(os.path.join(CACHE, 'camara_proyectos.json'), fichas)
    votos = []
    for v in lista:
        i = t(v, 'Id'); c = cache.get(i, {}); desc = t(v, 'Descripcion'); b = bol_norm(desc) if desc.startswith('Bolet') else None
        votos.append({'id': i, 'f': t(v, 'Fecha')[:16], 'b': b, 'tipo': t(v, 'Tipo'),
                      'd': desc if not b else (fichas.get(b, {}).get('nombre') or desc),
                      'art': c.get('art', ''), 'tr': c.get('tr', ''), 'tv': c.get('tv', ''),
                      'q': t(v, 'Quorum'), 'r': t(v, 'Resultado'), 'si': int(t(v, 'TotalSi') or 0), 'no': int(t(v, 'TotalNo') or 0),
                      'ab': int(t(v, 'TotalAbstencion') or 0), 'v': c.get('v', {})})
    return parl, votos, fichas

# ---------- Senado ----------
def resultado_sen(q, si, no, en_ejercicio=50):
    # cuando el texto no trae el resultado, se calcula con el quorum (calificados sobre senadores en ejercicio)
    q = q.lower()
    for clave, frac in (('cuatro s', 4 / 7), ('tres q', 3 / 5), ('dos t', 2 / 3), ('q.c', 0.5)):
        if clave in q:
            minimo = int(en_ejercicio * frac) + 1 if frac == 0.5 else -(-en_ejercicio * frac // 1)
            return 'Aprobado' if si >= minimo else 'Rechazado'
    return 'Aprobado' if si > no else 'Rechazado'

def senado():
    h = json.loads(get(SEN + 'hemicycle?vigentes=1&camara=S&limit=100'))['data']['parlamentarios']['data']
    parl = {str(p['ID_PARLAMENTARIO']): {'n': ' '.join(f"{p['NOMBRE']} {p['APELLIDO_PATERNO']} {p['APELLIDO_MATERNO']}".split()),
            'p': PARTIDOS_SEN.get(p['PARTIDO'], p['PARTIDO']), 'pn': p['PARTIDO'], 's': 'M' if p.get('SEXO') == 1 else 'H', 'r': 1} for p in h}
    legs = [l['ID_LEGISLATURA'] for l in json.loads(get(SEN + 'legislatures'))['data'] if dt.datetime.strptime(l['TERMINO'], '%d/%m/%Y').date() > DESDE]
    votos = []
    for l in legs:
        off = 0
        while True:
            d = json.loads(get(f'{SEN}votes?id_legislatura={l}&limit=300&offset={off}'))['data']
            for v in d['data']:
                f = dt.datetime.strptime(v['FECHA_VOTACION'], '%d-%m-%Y %H:%M:%S')
                if f.date() < DESDE: continue
                vv = {}
                for k, c in (('SI', 's'), ('NO', 'n'), ('ABSTENCION', 'a'), ('PAREO', 'p')):
                    for p in v['VOTACIONES'].get(k) or []:
                        i = str(p['PARLID']); vv[i] = c
                        if i not in parl: parl[i] = {'n': ' '.join(f"{p['NOMBRE']} {p['APELLIDO_PATERNO']} {p['APELLIDO_MATERNO']}".split()), 'p': 'S/I', 'pn': '', 's': '', 'r': 0}
                tema = ' '.join((v['TEMA'] or '').split())
                m = re.search(r'\b(aprobad[oa]|rechazad[oa])\b', tema, re.I)
                b = bol_norm(v['BOLETIN'])
                if b and int(b.split('-')[0]) < 10000: b = None  # boletines S: designaciones, acusaciones, acuerdos y oficios
                tipo = 'Proyecto de Ley' if b else next((k for k, r in TIPOS_SEN if re.search(r, tema, re.I)), 'Otros')
                votos.append({'id': str(v['ID_VOTACION']), 'f': f.strftime('%Y-%m-%dT%H:%M'), 'b': b, 'tipo': tipo,
                              'd': '', 'art': tema[:400] if b else tema[:1500], 'tr': '', 'tv': '', 'q': v['QUORUM'] or '',
                              'r': (m.group(1).capitalize()[:-1] + 'o') if m else resultado_sen(v['QUORUM'] or '', v['SI'] or 0, v['NO'] or 0), 'si': v['SI'] or 0, 'no': v['NO'] or 0, 'ab': v['ABS'] or 0, 'v': vv})
            off += len(d['data'])
            if not d['data'] or off >= d['total']: break
    votos.sort(key=lambda z: z['f'], reverse=True)
    print('Senado:', len(votos), 'votaciones')
    return parl, votos

# ---------- Proyectos (ficha de tramitacion del Senado, cubre ambas camaras) ----------
def proyectos(bols_recientes, todos):
    prev = leer('proyectos.json', {})
    pedir = sorted(b for b in todos if b not in prev or b in bols_recientes)
    print('Proyectos:', len(todos), 'boletines,', len(pedir), 'por consultar')
    def uno(b):
        try:
            x = ET.fromstring(get(TRAM + b.split('-')[0]).decode('utf-8', 'replace').encode('utf-8'))
        except Exception as e:
            return b, None
        g = lambda tag: ' '.join((x.findtext('.//descripcion/' + tag) or '').split())
        tr = [[(e.findtext('FECHA') or ''), 'S' if 'Senado' in (e.findtext('CAMARATRAMITE') or '') else 'C', ' '.join((e.findtext('DESCRIPCIONTRAMITE') or '').split())[:180], (e.findtext('ETAPDESCRIPCION') or '').strip()] for e in x.iter('tramite')]
        return b, {'t': g('titulo'), 'fi': g('fecha_ingreso'), 'ini': g('iniciativa'), 'ori': g('camara_origen'), 'et': g('etapa'), 'se': g('subetapa'),
                   'es': g('estado'), 'ley': g('leynro'), 'urg': g('urgencia_actual'), 'tram': tr}
    with ThreadPoolExecutor(4) as ex:
        for b, d in ex.map(uno, pedir):
            if d: prev[b] = d
    guardar(os.path.join(CACHE, 'proyectos.json'), prev)
    return prev

# ---------- Alias (resumen breve del tema, generado con IA; solo si hay ANTHROPIC_API_KEY) ----------
def alias(textos):
    prev = leer('alias.json', {})
    faltan = {k: t for k, t in textos.items() if t and k not in prev}
    print('Alias:', len(textos), 'textos,', len(faltan), 'sin alias')
    if faltan and os.environ.get('ANTHROPIC_API_KEY'):
        import anthropic
        cli = anthropic.Anthropic()
        claves = sorted(faltan)
        for i in range(0, len(claves), 40):
            lote = {k: faltan[k][:600] for k in claves[i:i + 40]}
            try:
                r = cli.beta.messages.create(model='claude-opus-5-5', max_tokens=8000, betas=['server-side-fallback-2026-07-01'], fallbacks='default',
                    output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': {'type': 'object', 'properties': {'alias': {'type': 'array', 'items': {'type': 'object', 'properties': {'k': {'type': 'string'}, 'a': {'type': 'string'}}, 'required': ['k', 'a'], 'additionalProperties': False}}}, 'required': ['alias'], 'additionalProperties': False}}},
                    system=PROMPT_ALIAS, messages=[{'role': 'user', 'content': json.dumps(lote, ensure_ascii=False)}])
            except anthropic.APIConnectionError as e: print('  alias sin conexion', e); break
            except anthropic.APIStatusError as e: print('  alias error', e.status_code, e.message); break
            if r.stop_reason in ('refusal', 'max_tokens'): print('  alias detenido:', r.stop_reason); continue
            txt = next((b.text for b in r.content if b.type == 'text'), '{}')
            for o in json.loads(txt).get('alias', []):
                if o['k'] in lote and o['a'].strip(): prev[o['k']] = o['a'].strip().rstrip('.')
        guardar(os.path.join(CACHE, 'alias.json'), prev, compacto=False)
    return {k: prev[k] for k in textos if k in prev}

# ---------- Analisis ----------
def analizar(parl, votos, cam):
    ids = sorted(parl, key=lambda i: (-parl[i]['r'], parl[i]['n']))
    pos = {i: k for k, i in enumerate(ids)}
    M = np.zeros((len(ids), len(votos)), dtype=np.int8)  # 1 si, -1 no, 0 otro
    for j, v in enumerate(votos):
        for i, c in v['v'].items():
            if c in 'sn': M[pos[i], j] = 1 if c == 's' else -1
    si, no = (M == 1).sum(0), (M == -1).sum(0)
    disputada = np.minimum(si, no) >= 0.1 * (si + no)  # minoria de al menos 10%
    P = np.array([parl[i]['p'] for i in ids])
    out = {'n_disputadas': int(disputada.sum())}
    # lealtad: voto igual a la mayoria de su partido (sin independientes)
    leal = np.full(len(ids), np.nan)
    rice = {}
    for p in sorted(set(P)):
        idx = np.where(P == p)[0]
        s, n = (M[idx] == 1).sum(0), (M[idx] == -1).sum(0)
        ok = (s + n) >= 2
        if p not in ('IND', 'S/I') and len(idx) >= 2 and ok.any():
            rice[p] = {'rice': round(float((np.abs(s - n)[ok] / (s + n)[ok]).mean()), 3), 'rice_disp': round(float((np.abs(s - n)[ok & disputada] / (s + n)[ok & disputada]).mean()), 3) if (ok & disputada).any() else None, 'miembros': int(sum(parl[ids[k]]['r'] for k in idx))}
            may = np.sign(s - n)
            for k in idx:
                m = (M[k] != 0) & (may != 0)
                if m.sum() >= 20: leal[k] = (M[k][m] == may[m]).mean()
    out['partidos'] = rice
    # acuerdo entre partidos: % de votaciones disputadas en que coinciden sus mayorias
    ps = [p for p in rice]
    may = {p: np.sign((M[P == p] == 1).sum(0) - (M[P == p] == -1).sum(0)) for p in ps}
    out['acuerdo'] = {'p': ps, 'm': [[round(float(((may[a] == may[b]) & (may[a] != 0) & disputada).sum() / max(1, ((may[a] != 0) & (may[b] != 0) & disputada).sum())), 3) for b in ps] for a in ps]}
    # espacio politico: MDS clasico sobre el desacuerdo en votaciones disputadas
    D = M[:, disputada].astype(float)
    part = (D != 0).sum(1)
    ok = part >= max(20, 0.3 * disputada.sum())
    X = np.full((len(ids), 2), np.nan); var = [0, 0]
    if ok.sum() > 5:
        A = D[ok]; C = np.abs(A) @ np.abs(A).T
        agree = (C + A @ A.T) / (2 * np.maximum(C, 1))
        d2 = (1 - agree) ** 2
        J = np.eye(len(A)) - 1 / len(A)
        B = -0.5 * J @ d2 @ J
        w, V = np.linalg.eigh(B); o = np.argsort(w)[::-1]
        Y = V[:, o[:2]] * np.sqrt(np.maximum(w[o[:2]], 0))
        var = [round(float(w[o[k]] / w[w > 0].sum()), 3) for k in range(2)]
        Pk = P[ok]
        for k, ref in ((0, ['PREP', 'UDI', 'RN', 'PNL']),):
            der = np.isin(Pk, ref)
            if der.any() and Y[der, k].mean() < 0: Y[:, k] *= -1
        prev = leer(f'ejes_{cam}.json', {})
        ant = [(ids[k], c) for k, c in zip(np.where(ok)[0], Y[:, 1])]
        comunes = [(c, prev[i]) for i, c in ant if i in prev]
        if len(comunes) > 5 and np.corrcoef([a for a, _ in comunes], [b for _, b in comunes])[0, 1] < 0: Y[:, 1] *= -1
        X[ok] = Y
        guardar(os.path.join(CACHE, f'ejes_{cam}.json'), {ids[k]: float(Y[n, 1]) for n, k in enumerate(np.where(ok)[0])} | {i: v for i, v in prev.items() if i not in ids})
    out['var'] = var
    lista = []
    for k, i in enumerate(ids):
        q = parl[i]
        lista.append({'id': i, 'n': q['n'], 'p': q['p'], 's': q['s'], 'r': q['r'],
                      'x': None if np.isnan(X[k, 0]) else round(float(X[k, 0]), 4), 'y': None if np.isnan(X[k, 1]) else round(float(X[k, 1]), 4),
                      'part': round(float((M[k] != 0).mean()), 3) if len(votos) else 0, 'leal': None if np.isnan(leal[k]) else round(float(leal[k]), 3)})
    vs = [{kk: vv for kk, vv in v.items() if kk != 'v'} | {'v': ''.join(v['v'].get(i, '.') for i in ids)} for v in votos]
    out.update({'parl': lista, 'votos': vs})
    return out

def main():
    ahora = dt.datetime.now(CL)
    if '--forzar' not in sys.argv:
        prev = os.path.join(OUT, 'congreso.json')
        ult = json.load(open(prev, encoding='utf-8'))['actualizado'][:10] if os.path.exists(prev) else ''
        if ahora.hour < 6 or ult == ahora.date().isoformat():
            print('Fuera de horario o ya actualizado hoy:', ahora.isoformat(timespec='minutes')); return
    pc, vc, fichas = camara()
    ruta = os.path.join(OUT, 'congreso.json'); previo = json.load(open(ruta, encoding='utf-8')) if os.path.exists(ruta) else {}
    try: ps, vs = senado(); sen_ok = True
    except Exception as e:
        h = getattr(e, 'headers', None) or {}
        print('Senado sin respuesta:', e, '| server:', h.get('Server'), '| cf-ray:', h.get('cf-ray'))
        if 'S' not in previo: raise
        ps, vs, sen_ok = None, previo['S']['votos'], False
    limite = (ahora - dt.timedelta(days=30)).strftime('%Y-%m-%d')
    todos = {v['b'] for v in vc + vs if v['b']}
    recientes = {v['b'] for v in vc + vs if v['b'] and v['f'] >= limite}
    pr = proyectos(recientes, todos)
    for v in vs:
        if sen_ok and v['b'] and v['b'] in pr: v['d'] = pr[v['b']]['t']
    for v in vc:
        if v['b'] and v['b'] in pr and v['d'].startswith('Bolet'): v['d'] = pr[v['b']]['t']
    datos = {'actualizado': ahora.isoformat(timespec='minutes'), 'desde': DESDE.isoformat(), 'C': analizar(pc, vc, 'C'), 'S': analizar(ps, vs, 'S') if sen_ok else previo['S']}
    datos['act'] = {'C': datos['actualizado'], 'S': datos['actualizado'] if sen_ok else previo.get('act', {}).get('S', previo['actualizado'])}
    for b, f in fichas.items():
        if b in pr and f.get('ministerio'): pr[b]['min'] = f['ministerio']
    textos = {'b:' + b: pr[b]['t'] for b in todos if b in pr and pr[b].get('t')} | {'S:' + v['id']: v['art'] for v in vs if not v['b'] and v['art']}
    try: datos['alias'] = alias(textos)
    except Exception as e: print('Alias con error:', e); datos['alias'] = {k: a for k, a in leer('alias.json', {}).items() if k in textos}
    guardar(os.path.join(OUT, 'congreso.json'), datos)
    guardar(os.path.join(OUT, 'proyectos.json'), {'actualizado': datos['actualizado'], 'p': {b: pr[b] for b in sorted(todos) if b in pr}})
    print('Listo', datos['actualizado'], {k: os.path.getsize(os.path.join(OUT, k)) // 1024 for k in os.listdir(OUT)}, 'KB')

if __name__ == '__main__':
    main()
