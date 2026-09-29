# -*- coding: utf-8 -*-
"""
teste_cruzado.py - AUDITORIA CRUZADA dos dados de votacoes e do Perfil. Diferente de teste_dados.py (que confere a
coerencia interna dos arquivos), aqui cada dado e conferido contra uma SEGUNDA fonte independente:

  1. ALE-RO nominais  x  API do SAPL de novo (voto a voto, amostra), placar registrado, periodo de MANDATO de cada
                        deputado (parlamentares/mandato) e historico eleitoral do TSE (ligacao e completude)
  2. Leis sem voto    x  API do SAPL: materia, tramitacao, norma juridica publicada, autoria e ausencia de voto nominal
  3. Camara           x  API da Camara (votos por votacao, data/resultado, cadastro do deputado com nascimento)
                        e historico do TSE (completude)
  4. Senado           x  API do Senado (votos por senador/ano, cadastro com nascimento) e historico do TSE
  5. Entre as Casas   - ninguem vota em duas Casas no mesmo dia; votos dentro do periodo de mandato
  6. Perfil (JS)      x  reimplementacao independente em Python: emendas por municipio (52 municipios de RO) e
                        concordancia com posicoes sorteadas; municipios do Perfil x bases

Precisa de internet (amostras sorteadas com semente fixa: rodar de novo confere as mesmas votacoes) e do Edge
(parte 6, via Playwright). ~5 min.

Uso:  python scripts/testes/teste_cruzado.py            -> relatorio em scripts/testes/saida/auditoria_cruzada.md
      python scripts/testes/teste_cruzado.py --amostra 80   (padrao 40 por verificacao)
Sai com codigo 1 se houver FALHA (erro nosso). ALERTA = divergencia da propria fonte ou caso para olhar.
"""
import collections
import concurrent.futures
import datetime
import json
import os
import pathlib
import random
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = ROOT / "raw"
SAIDA = pathlib.Path(__file__).resolve().parent / "saida"
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_alero import nome_quase_igual, norm  # noqa: E402
import re  # noqa: E402


def norm_mun(s):
    """igual ao normMun do navegador: pontuacao vira espaco e d'Oeste = do Oeste"""
    return re.sub(r"\s+", " ", re.sub(r"\bd oeste\b", "do oeste", re.sub(r"[^a-z0-9]+", " ", norm(s)))).strip()

N = int(sys.argv[sys.argv.index("--amostra") + 1]) if "--amostra" in sys.argv else 40
rnd = random.Random(2026)
achados = []   # (secao, nivel, mensagem, exemplos)
contagem = collections.Counter()


def reg(secao, nivel, msg, exemplos=None):
    """nivel: OK | FALHA (erro nosso) | ALERTA (divergencia da fonte / caso para revisar) | INFO"""
    achados.append((secao, nivel, msg, exemplos or []))
    contagem[nivel] += 1
    print("  %-6s %s" % (nivel, msg))
    for e in (exemplos or [])[:5]:
        print("           - %s" % e)


def ler(p):
    t = open(p, encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))


def get(url, accept="application/json", tentativas=5):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "MeuVoto2026-auditoria/1.0"})
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            if i == tentativas - 1:
                raise
            time.sleep(2 ** (i + 1))


def paralelo(fn, itens, n=4):
    with concurrent.futures.ThreadPoolExecutor(n) as ex:
        return list(ex.map(fn, itens))


def data_tse(s):
    try:
        return datetime.datetime.strptime(s or "", "%d/%m/%Y").date()
    except ValueError:
        return None


SAPL = "https://sapl.al.ro.leg.br/api/"
CAMARA = "https://dadosabertos.camara.leg.br/api/v2/"
SENADO = "https://legis.senado.leg.br/dadosabertos/"
VOTO_ALERO = {"Sim": "S", "Não": "N", "Abstenção": "A", "Ausente": "U", "Não Votou": "X", "-1": "?"}

print("Carregando arquivos gerados")
cands = {c["sq"]: c for c in ler(DATA / "cand_RO.js")}
AL = ler(DATA / "alero.js")
BRUTO = json.load(open(RAW / "alero_sapl.json", encoding="utf-8"))
VF = ler(DATA / "votacoes_federais.js")
CAM = ler(DATA / "camara.js")
EM = ler(DATA / "emendas.js")
MUNS = ler(DATA / "municipios.js")
eleito = lambda h: (h.get("resultado") or "").lower().startswith("eleito")
t0 = time.time()

# =====================================================================================================
print("\n1. ALE-RO: votacoes nominais")
S1 = "1. ALE-RO nominais"
# ids originais do SAPL -> id unificado no arquivo (cadastros duplicados da mesma pessoa), reconstruido aqui de
# forma independente: o proprio id se ficou no arquivo; senao o unico cadastro do arquivo com o mesmo nome civil
# (ou nome civil quase igual, para quem esta ligado a candidato)
vot_arq = {x["id"]: x for x in AL["vot"]}
vot_bruto = {x["id"]: x for x in BRUTO["vot"]}
orig_para_canon = {}
for pid, p in BRUTO["parl"].items():
    if pid in AL["parl"]:
        orig_para_canon[pid] = pid
        continue
    alvo = [q for q, pa in AL["parl"].items() if norm(pa["c"]) == norm(p["c"])] or \
           [q for q, pa in AL["parl"].items() if pa.get("sq") and nome_quase_igual(pa["c"], p["c"])]
    orig_para_canon[pid] = alvo[0] if len(alvo) == 1 else None
sem_canon = [pid for pid, c in orig_para_canon.items() if c is None]
reg(S1, "FALHA" if sem_canon else "OK", "todo cadastro original do SAPL tem destino no arquivo (unificacao de duplicados) - %d cadastros" % len(BRUTO["parl"]), sem_canon)

# 1.1 placar registrado pela ALE-RO x contagem dos votos individuais
dif = []
for x in AL["vot"]:
    c = collections.Counter(x["v"].values())
    if x.get("sim") is not None and (c["S"], c["N"]) != (x["sim"], x["nao"]):
        dif.append("%s %s/%s (%s): placar ALE-RO Sim %s Nao %s x votos individuais Sim %d Nao %d" % (x["t"], x["n"], x["a"], x["d"], x["sim"], x["nao"], c["S"], c["N"]))
pct = 100.0 * len(dif) / max(1, len(AL["vot"]))
reg(S1, "ALERTA" if dif else "OK", "placar registrado pela ALE-RO = soma dos votos individuais em %d de %d votacoes (%.1f%% divergem - divergencia da propria fonte)" % (len(AL["vot"]) - len(dif), len(AL["vot"]), pct), dif)

# 1.2 amostra: voto a voto contra a API
amostra = rnd.sample(AL["vot"], min(N, len(AL["vot"])))
def votos_api(vid):
    out, url = {}, SAPL + "sessao/votoparlamentar/?votacao=%d&page_size=100" % vid
    while url:
        j = get(url)
        for v in j["results"]:
            out[str(v["parlamentar"])] = v["voto"]
        url = j["pagination"]["links"].get("next")
    r = get(SAPL + "sessao/registrovotacao/%d/" % vid)
    item = get(SAPL + ("sessao/ordemdia/%d/" % r["ordem"] if r.get("ordem") else "sessao/expedientemateria/%d/" % r["expediente"]))
    return vid, out, item.get("data_ordem") or item.get("data_sessao")
diverg, conferidos, datas = [], 0, []
for vid, api, data_fonte in paralelo(votos_api, [x["id"] for x in amostra]):
    xb = vot_bruto[vid]
    if data_fonte and vot_arq[vid]["d"] != data_fonte:
        datas.append("votacao %d (%s %s/%s): data na ordem do dia %s x arquivo %s" % (vid, vot_arq[vid]["t"], vot_arq[vid]["n"], vot_arq[vid]["a"], data_fonte, vot_arq[vid]["d"]))
    for pid, voto in api.items():
        conferidos += 1
        esperado = VOTO_ALERO.get(voto.strip(), "?")
        if xb["v"].get(pid) != esperado:
            diverg.append("votacao %d, parlamentar %s: API '%s' x bruto '%s'" % (vid, pid, voto, xb["v"].get(pid)))
        canon = orig_para_canon.get(pid)
        if canon and vot_arq[vid]["v"].get(canon) not in (esperado, "S", "N", "A") and esperado in ("S", "N", "A"):
            diverg.append("votacao %d, parlamentar %s -> %s: API '%s' x arquivo '%s'" % (vid, pid, canon, voto, vot_arq[vid]["v"].get(canon)))
    extras = set(xb["v"]) - set(api)
    if extras:
        diverg.append("votacao %d: parlamentares no arquivo que a API nao tem: %s" % (vid, sorted(extras)))
reg(S1, "FALHA" if diverg else "OK", "amostra de %d votacoes: %d votos individuais conferidos de novo na API do SAPL, iguais" % (len(amostra), conferidos), diverg)
reg(S1, "FALHA" if datas else "OK", "amostra de %d votacoes: data igual a da ordem do dia/expediente na API (nao a data de cadastro)" % len(amostra), datas)
mig = collections.Counter(x["d"] for x in AL["vot"]).most_common(1)[0]
reg(S1, "FALHA" if mig[1] > 60 else "OK", "nenhuma data concentra votacoes demais (sinal de data de cadastro/migracao no lugar da sessao): maior = %s com %d" % mig)

# 1.3 ligacao deputado -> candidato: historico do TSE, nome civil e periodo de mandato
ligados = {sq: pid for sq, pid in AL["porCand"].items()}
sem_hist = [cands[sq]["urna"] for sq in ligados if not any(h.get("cargo") == "Deputado Estadual" and h.get("uf") == "RO" for h in cands[sq].get("hist") or [])]
reg(S1, "FALHA" if sem_hist else "OK", "todo candidato ligado a deputado estadual ja disputou Deputado Estadual em RO no historico do TSE (%d)" % len(ligados), sem_hist)
nomes = [(cands[sq]["urna"], AL["parl"][pid]["c"], cands[sq]["nome"]) for sq, pid in ligados.items() if norm(AL["parl"][pid]["c"]) != norm(cands[sq]["nome"])]
ruins = [n for n in nomes if not nome_quase_igual(n[1], n[2])]
reg(S1, "FALHA" if ruins else "OK", "nome civil ALE-RO x TSE: %d identicos, %d quase iguais (erro de digitacao na fonte), 0 diferentes" % (len(ligados) - len(nomes), len(nomes)), ["%s: ALE-RO '%s' x TSE '%s'" % n for n in (ruins or nomes)])

origs_por_canon = collections.defaultdict(list)
for o, c in orig_para_canon.items():
    if c:
        origs_por_canon[c].append(o)
def mandatos(pid):
    return pid, get(SAPL + "parlamentares/mandato/?parlamentar=%s&page_size=100" % pid)["results"]
ids_mand = sorted({o for pid in ligados.values() for o in origs_por_canon[pid]})
mand = dict(paralelo(mandatos, ids_mand))
fora, sem_mandato = [], []
for sq, pid in ligados.items():
    periodos = [(m["data_inicio_mandato"], m["data_fim_mandato"] or "2099-12-31") for o in origs_por_canon[pid] for m in mand.get(o, []) if m.get("data_inicio_mandato")]
    if not periodos:
        sem_mandato.append(cands[sq]["urna"])
        continue
    for x in AL["vot"]:
        if pid in x["v"] and x["v"][pid] in ("S", "N", "A") and not any(a <= x["d"] <= b for a, b in periodos):
            fora.append("%s votou %s em %s (%s %s/%s); mandatos no SAPL: %s" % (cands[sq]["urna"], x["v"][pid], x["d"], x["t"], x["n"], x["a"], ", ".join("%s a %s" % p for p in periodos)))
reg(S1, "INFO" if sem_mandato else "OK", "deputados ligados sem mandato cadastrado no SAPL (cadastro da fonte incompleto)", sem_mandato)
reg(S1, "INFO" if fora else "OK", "votos fora de um mandato cadastrado no SAPL: %d (o cadastro de mandatos da ALE-RO e incompleto; ver o teste seguinte)" % len(fora), fora)
# voto de fato depois de assumir outro cargo eleito (posse em 1/1 do ano seguinte a eleicao municipal/estadual)
depois = []
for sq, pid in ligados.items():
    hist = cands[sq].get("hist") or []
    dep_anos = [h["ano"] for h in hist if h.get("cargo") == "Deputado Estadual" and h.get("ano")]
    for h in hist:
        if not eleito(h) or h.get("cargo") in ("Deputado Estadual", None) or not h.get("ano"):
            continue
        posse ="%d-01-01" % (h["ano"] + 1) if h.get("abrang") == "M" or h.get("cargo") in ("Governador", "Vice-Governador") else "%d-02-01" % (h["ano"] + 1)
        fim = "%d-12-31" % (h["ano"] + 4)
        for x in AL["vot"]:
            # so conta cargo eleito DEPOIS da eleicao a deputado estadual que deu o mandato daquele voto (quem era
            # vereador e virou deputado deixou a Camara Municipal: Alex Redano, vereador em 2012, deputado em 2014)
            ultima_dep = max([a for a in dep_anos if a < int(x["d"][:4])] or [0])
            if pid in x["v"] and x["v"][pid] in ("S", "N", "A") and posse <= x["d"] <= fim and h["ano"] > ultima_dep:
                depois.append("%s votou %s em %s (%s %s/%s), mas assumiu %s (%s) em %s" % (cands[sq]["urna"], x["v"][pid], x["d"], x["t"], x["n"], x["a"], h["cargo"], h.get("ue"), posse))
reg(S1, "ALERTA" if depois else "OK", "nenhum deputado ligado aparece votando na ALE-RO depois de assumir outro cargo eleito (TSE)", depois)

# 1.4 completude: candidato 2026 eleito deputado estadual em RO (2014-2022) sem ligacao
esperados = [c for c in cands.values() if any(h.get("cargo") == "Deputado Estadual" and h.get("uf") == "RO" and eleito(h) and (h.get("ano") or 0) >= 2014 for h in c.get("hist") or [])]
faltando = []
for c in esperados:
    if c["sq"] in ligados:
        continue
    parecidos = [p["n"] + " (" + p["c"] + ")" for p in BRUTO["parl"].values() if set(norm(p["c"]).split()) & set(norm(c["nome"]).split()) - {"de", "da", "do", "dos", "das", "silva", "santos", "souza", "oliveira", "pereira"}]
    faltando.append("%s (%s, %s) eleito dep. estadual %s; parecidos no SAPL: %s" % (c["urna"], c["nome"], c["cargo"], [h["ano"] for h in c["hist"] if h.get("cargo") == "Deputado Estadual" and eleito(h)], parecidos[:3] or "nenhum"))
reg(S1, "ALERTA" if faltando else "OK", "candidatos eleitos deputado estadual em RO desde 2014: %d, ligados a votos da ALE-RO: %d" % (len(esperados), len(esperados) - len(faltando)), faltando)

# =====================================================================================================
print("\n2. ALE-RO: leis sem voto individual")
S2 = "2. Leis sem voto individual"
LE = AL["leis"]
am = rnd.sample(LE, min(N, len(LE)))
def conf_lei(l):
    m = get(SAPL + "materia/materialegislativa/%d/" % l["m"])
    t = get(SAPL + "materia/tramitacao/?materia=%d&page_size=100" % l["m"])["results"]
    n = get(SAPL + "norma/normajuridica/?materia=%d" % l["m"])["results"]
    a = get(SAPL + "materia/autoria/?materia=%d&page_size=100" % l["m"])["results"]
    rv = get(SAPL + "sessao/registrovotacao/?materia=%d&page_size=100" % l["m"])["results"]
    com_voto = [r["id"] for r in rv if get(SAPL + "sessao/votoparlamentar/?votacao=%d&page_size=1" % r["id"])["pagination"]["total_entries"]]
    return l, m, t, n, a, com_voto
probs, lei_dif, sem_lei, nominal_perdido, autoria = [], [], [], [], []
TIPOS = {1: "PL", 5: "PLC", 12: "PEC"}
for l, m, t, n, a, com_voto in paralelo(conf_lei, am):
    rot = "%s %s/%s" % (l["t"], l["n"], l["a"])
    if (TIPOS.get(m["tipo"]), m["numero"], m["ano"]) != (l["t"], l["n"], l["a"]) or " ".join((m.get("ementa") or "").split()) != l["e"]:
        probs.append("%s: materia na API = %s %s/%s" % (rot, TIPOS.get(m["tipo"]), m["numero"], m["ano"]))
    if not any(x["data_tramitacao"] == l["d"] and x["status"] in (9, 10, 33, 52) for x in t):
        probs.append("%s: a API nao tem decisao em plenario em %s" % (rot, l["d"]))
    nums = sorted(x["numero"] for x in n)
    if l.get("lei") and not any(str(int(x)).lstrip("0") in l["lei"].replace(".", "") for x in nums if str(x).isdigit()):
        lei_dif.append("%s: arquivo '%s' x normas na API %s" % (rot, l["lei"], nums))
    if not l.get("lei") and nums:
        sem_lei.append("%s (%s): virou norma %s, mas a tramitacao ainda nao registra 'transformada em lei'" % (rot, l["d"], nums))
    if com_voto and not l.get("nominal"):
        nominal_perdido.append("%s: a API tem voto individual nas votacoes %s" % (rot, com_voto))
    ids_aut = sorted(x["autor"] for x in a)
    if len(ids_aut) != len(l["aut"]):
        autoria.append("%s: %d autores na API x %d no arquivo" % (rot, len(ids_aut), len(l["aut"])))
reg(S2, "FALHA" if probs else "OK", "amostra de %d leis: tipo, numero, ano, ementa e data da decisao iguais a API" % len(am), probs)
reg(S2, "FALHA" if lei_dif else "OK", "numero da lei gerada = norma juridica publicada no SAPL", lei_dif)
reg(S2, "ALERTA" if sem_lei else "OK", "leis ja publicadas como norma que o arquivo ainda mostra sem numero de lei (atraso da tramitacao)", sem_lei)
reg(S2, "FALHA" if nominal_perdido else "OK", "'sem voto individual registrado' confirmado: a API nao tem voto individual para essas materias", nominal_perdido)
reg(S2, "FALHA" if autoria else "OK", "quantidade de autores igual a API", autoria)
# completude pelo caminho inverso: normas publicadas desde DESDE, de projeto de lei/LC/PEC -> tem que estar na lista
ids_leis = {l["m"] for l in LE}
normas = []
for ano in range(int(AL["leisDesde"][:4]), datetime.date.today().year + 1):
    j = get(SAPL + "norma/normajuridica/?ano=%d&page_size=100&o=id" % ano)
    normas += [n for n in j["results"] if n.get("materia")]
amn = rnd.sample(normas, min(N, len(normas)))
def mat(n):
    return n, get(SAPL + "materia/materialegislativa/%d/" % n["materia"]), get(SAPL + "materia/tramitacao/?materia=%d&page_size=100" % n["materia"])["results"]
faltam, n_leis = [], 0
for n, m, t in paralelo(mat, amn):
    if m.get("tipo") not in TIPOS:
        continue
    decidida = [x for x in t if x["status"] in (9, 10, 33, 52) and x["data_tramitacao"] >= AL["leisDesde"]]
    if not decidida:
        continue
    n_leis += 1
    if n["materia"] not in ids_leis:
        faltam.append("norma %s de %s <- %s %s/%s (decidida em %s) nao esta na lista" % (n["numero"], n["ano"], TIPOS[m["tipo"]], m["numero"], m["ano"], decidida[-1]["data_tramitacao"]))
reg(S2, "FALHA" if faltam else "OK", "completude: de %d normas sorteadas desde %s, as %d que vieram de PL/PLC/PEC decidido em plenario estao todas na lista" % (len(amn), AL["leisDesde"][:4], n_leis), faltam)
d = get(SAPL + "parlamentares/parlamentar/290/")
dl = next(l for l in LE if l["m"] == 52292)["decl"][0]
ok_decl = d["nome_parlamentar"] == "DELEGADO LUCAS" and AL["parl"][dl["parlamentar"]]["sq"] and cands[AL["parl"][dl["parlamentar"]]["sq"]]["urna"] == "DELEGADO LUCAS TORRES"
reg(S2, "OK" if ok_decl else "FALHA", "declaracao da ata 252: id 290 no SAPL = Delegado Lucas = candidato DELEGADO LUCAS TORRES")
n6328 = get(SAPL + "norma/normajuridica/?materia=52292")["results"]
reg(S2, "INFO", "PL 1243/2025 -> norma no SAPL: %s (a tramitacao diz '04 de janeiro'; o sistema mostra so o numero)" % [(x["numero"], x["data"]) for x in n6328])

# =====================================================================================================
print("\n3. Camara dos Deputados")
S3 = "3. Camara"
C = VF["camara"]
dep_sq = {d: p["sq"] for d, p in C["parl"].items()}
am = rnd.sample(C["vot"], min(N, len(C["vot"])))
def conf_cam(x):
    return x, get(CAMARA + "votacoes/%s/votos" % x["id"])["dados"], get(CAMARA + "votacoes/%s" % x["id"])["dados"]
probs, faltou, conferidos = [], [], 0
for x, votos, det in paralelo(conf_cam, am):
    api = {str(v["deputado_"]["id"]): v["tipoVoto"] for v in votos}
    for d, sq in dep_sq.items():
        if d in api:
            conferidos += 1
            if x["v"].get(d) != api[d]:
                probs.append("%s (%s) %s: API '%s' x arquivo '%s'" % (x["id"], x["d"], C["parl"][d]["n"], api[d], x["v"].get(d)))
        elif d in x["v"] and x["v"][d] != "Sem registro":
            faltou.append("%s: arquivo tem voto de %s que a API nao lista" % (x["id"], C["parl"][d]["n"]))
    if det.get("data") != x["d"]:
        probs.append("%s: data API %s x arquivo %s" % (x["id"], det.get("data"), x["d"]))
    ap = det.get("aprovacao")
    if ap in (0, 1) and x["r"] != ("Aprovada" if ap == 1 else "Rejeitada"):
        probs.append("%s: aprovacao API %s x arquivo '%s'" % (x["id"], ap, x["r"]))
reg(S3, "FALHA" if probs else "OK", "amostra de %d votacoes: %d votos de candidatos de RO iguais a API, e data/resultado iguais" % (len(am), conferidos), probs)
reg(S3, "FALHA" if faltou else "OK", "nenhum voto no arquivo que a API nao tenha", faltou)
def dep_api(d):
    return d, get(CAMARA + "deputados/%s" % d)["dados"]
probs = []
for d, det in paralelo(dep_api, list(dep_sq)):
    c = cands[dep_sq[d]]
    try:
        dias = abs((datetime.date.fromisoformat(det["dataNascimento"]) - data_tse(c["nasc"])).days)
    except (TypeError, ValueError):
        dias = 999
    if dias > 1 or not nome_quase_igual(det.get("nomeCivil") or "", c["nome"]):
        probs.append("%s -> %s: API nasc %s nome '%s' x TSE nasc %s nome '%s'" % (d, c["urna"], det.get("dataNascimento"), det.get("nomeCivil"), c["nasc"], c["nome"]))
reg(S3, "FALHA" if probs else "OK", "cadastro na API da Camara (nascimento e nome civil) = TSE para os %d deputados ligados" % len(dep_sq), probs)
fora = []
for d, sq in dep_sq.items():
    anos = []
    for m in CAM[sq].get("mandatos", []):
        a, b = m.split("–")
        anos.append(("%s-02-01" % a, "%s-01-31" % b))
    for x in C["vot"]:
        if d in x["v"] and not any(a <= x["d"] <= b for a, b in anos):
            fora.append("%s votou em %s; legislaturas %s" % (C["parl"][d]["n"], x["d"], CAM[sq].get("mandatos")))
            break
reg(S3, "FALHA" if fora else "OK", "votos dos deputados dentro das legislaturas em que estiveram na Camara", fora)
esperados = [c for c in cands.values() if any(h.get("cargo") == "Deputado Federal" and eleito(h) and (h.get("ano") or 0) >= 2014 for h in c.get("hist") or [])]
faltando = [c["urna"] + " (" + c["cargo"] + ")" for c in esperados if c["sq"] not in C["porCand"]]
reg(S3, "ALERTA" if faltando else "OK", "candidatos eleitos deputado federal desde 2014: %d, com votos da Camara: %d" % (len(esperados), len(esperados) - len(faltando)), faltando)

# =====================================================================================================
print("\n4. Senado Federal")
S4 = "4. Senado"
SE = VF["senado"]
probs, conferidos = [], 0
ROT = {"P-NRV": "Presente, não registrou voto", "AP": "Ausente em atividade parlamentar", "MIS": "Ausente em missão", "LS": "Licença saúde",
       "LP": "Licença particular", "NCom": "Não compareceu", "Votou": "Votou (voto secreto)"}
for cod, p in SE["parl"].items():
    anos = sorted({x["d"][:4] for x in SE["vot"] if cod in x["v"]})
    for ano in rnd.sample(anos, min(3, len(anos))):
        api = get(SENADO + "votacao?codigoParlamentar=%s&dataInicio=%s-01-01&dataFim=%s-12-31" % (cod, ano, ano))
        api_v = {x["codigoSessaoVotacao"]: (x["votos"][0].get("siglaVotoParlamentar") if x.get("votos") else None) for x in api}
        arq = {x["id"]: x["v"][cod] for x in SE["vot"] if cod in x["v"] and x["d"][:4] == ano}
        if set(api_v) != set(arq):
            probs.append("%s %s: %d votacoes na API x %d no arquivo" % (p["n"], ano, len(api_v), len(arq)))
        for k, v in arq.items():
            conferidos += 1
            if k in api_v and ROT.get(api_v[k], api_v[k]) != v:
                probs.append("%s votacao %s: API '%s' x arquivo '%s'" % (p["n"], k, api_v[k], v))
reg(S4, "FALHA" if probs else "OK", "%d votos de senadores (3 anos sorteados por senador) iguais a API por senador" % conferidos, probs)
probs = []
for cod, p in SE["parl"].items():
    det = get(SENADO + "senador/%s.json" % cod)["DetalheParlamentar"]["Parlamentar"]
    nome = det["IdentificacaoParlamentar"].get("NomeCompletoParlamentar")
    nasc = (det.get("DadosBasicosParlamentar") or {}).get("DataNascimento")
    c = cands[p["sq"]]
    if nasc != data_tse(c["nasc"]).isoformat() or not nome_quase_igual(nome, c["nome"]):
        probs.append("%s: API %s %s x TSE %s %s" % (cod, nome, nasc, c["nome"], c["nasc"]))
reg(S4, "FALHA" if probs else "OK", "cadastro na API do Senado (nascimento e nome completo) = TSE para os %d senadores ligados" % len(SE["parl"]), probs)
esperados = [c for c in cands.values() if any(h.get("cargo") == "Senador" and eleito(h) and (h.get("ano") or 0) >= 2010 for h in c.get("hist") or [])]
faltando = [c["urna"] for c in esperados if c["sq"] not in SE["porCand"]]
reg(S4, "ALERTA" if faltando else "OK", "candidatos eleitos senador desde 2010: %d, com votos do Senado: %d" % (len(esperados), len(esperados) - len(faltando)), faltando)

# =====================================================================================================
print("\n5. Cruzamento entre as Casas")
S5 = "5. Entre as Casas"
dias = collections.defaultdict(lambda: collections.defaultdict(set))   # sq -> casa -> dias com voto de fato
for x in AL["vot"]:
    for pid, v in x["v"].items():
        sq = AL["parl"][pid].get("sq")
        if sq and v in ("S", "N", "A"):
            dias[sq]["ALE-RO"].add(x["d"])
for casa, Cx in (("Camara", VF["camara"]), ("Senado", VF["senado"])):
    for x in Cx["vot"]:
        for pid, v in x["v"].items():
            if v in ("Sim", "Não", "Abstenção", "Obstrução", "Votou (voto secreto)"):
                dias[Cx["parl"][pid]["sq"]][casa].add(x["d"])
conflitos = []
for sq, casas in dias.items():
    ks = sorted(casas)
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            comum = casas[ks[i]] & casas[ks[j]]
            if comum:
                conflitos.append("%s votou na %s e na %s no mesmo dia: %s" % (cands[sq]["urna"], ks[i], ks[j], sorted(comum)[:3]))
multi = [cands[sq]["urna"] + ": " + ", ".join("%s %s a %s" % (k, min(v), max(v)) for k, v in sorted(casas.items())) for sq, casas in dias.items() if len(casas) > 1]
reg(S5, "FALHA" if conflitos else "OK", "ninguem vota em duas Casas no mesmo dia (%d candidatos passaram por mais de uma Casa)" % len(multi), conflitos or multi)

# =====================================================================================================
print("\n6. Perfil: calculos do navegador x reimplementacao independente em Python")
S6 = "6. Perfil (JS x Python)"
chaves_em = {k.split("|")[1] for k in EM["porMun"] if k.startswith("RO|") and k.split("|")[1]}
nomes_ro = {norm_mun(m) for m in MUNS["RO"]}
reg(S6, "OK" if {norm_mun(k) for k in chaves_em} == nomes_ro else "FALHA", "os %d municipios de RO do Perfil = os municipios com emendas (%d), com d'Oeste = do Oeste" % (len(nomes_ro), len(chaves_em)),
    sorted({norm_mun(k) for k in chaves_em} ^ nomes_ro))
ro_mun = {norm_mun(m) for m in MUNS["RO"]}
sem = sorted({m for c in cands.values() for h in (c.get("hist") or []) if h.get("abrang") == "M" and h.get("uf") == "RO" for m in [h.get("ue")] if m and norm_mun(m) not in ro_mun})
reg(S6, "INFO" if sem else "OK", "municipios de RO do historico do TSE fora da lista atual (nomes antigos)", sem)
for fonte, nomes in (("votacao de 2022", {t["mun"] for c in cands.values() for v in c.get("votosAnt") or [] for t in v["top"] if t["uf"] == "RO"}),
                     ("nascimento", {c["munNasc"] for c in cands.values() if c.get("ufNasc") == "RO" and c.get("munNasc")})):
    fora_l = sorted(m for m in nomes if norm_mun(m) not in ro_mun)
    reg(S6, "FALHA" if fora_l else "OK", "municipios de RO da base de %s acham o municipio do Perfil (%d nomes)" % (fonte, len(nomes)), fora_l)

def emendas_py(uf, mun):
    """reimplementacao independente da soma por municipio (mesma regra da tela Emendas)"""
    chave = next((k for k in EM["porMun"] if k.split("|")[0] == uf and norm_mun(k.split("|")[1]) == norm_mun(mun)), None)
    if not chave:
        return None
    ag = collections.defaultdict(lambda: collections.Counter())
    for x in EM["porMun"][chave]:
        if not x.get("sq"):
            continue
        a = ag[x["sq"]]
        if x["nv"] == "fed":
            a["empFed"] += x.get("e") or 0; a["pagoFed"] += x.get("p") or 0
        elif x["nv"] == "fav":
            a["rec"] += x.get("r") or 0
        else:
            a["destEst"] += max(x.get("pv") or 0, x.get("e") or 0); a["pagoEst"] += x.get("p") or 0
    out = {}
    for sq, a in ag.items():
        dest = max(a["empFed"], a["rec"]) + a["destEst"]
        pago = max(a["pagoFed"], a["rec"]) + a["pagoEst"]
        if dest > 0 or pago > 0:
            out[sq] = (round(dest, 2), round(pago, 2))
    return out

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge", headless=True)
        pg = b.new_page()
        pg.goto((ROOT / "meu-voto.html").as_uri()); pg.evaluate("localStorage.clear()")
        pg.goto((ROOT / "meu-voto.html").as_uri()); pg.wait_for_timeout(2500)
        dif, n_mun, n_val, sem_chave = [], 0, 0, []
        for mun in MUNS["RO"]:
            if emendas_py("RO", mun) is None:
                sem_chave.append(mun)
            js = pg.evaluate("""(mun) => { App.setPerfil({ uf: 'RO', mun }); const out = {};
              for (const c of App.Dados.cache.RO.concat(App.Dados.cache.BR || [])) { const e = App.emendasFoco(c.sq); if (e) out[c.sq] = [Math.round(e.destinado * 100) / 100, Math.round(e.pago * 100) / 100]; }
              return out; }""", mun)
            py = emendas_py("RO", mun) or {}
            py = {sq: v for sq, v in py.items() if sq in js or sq in cands}
            n_mun += 1
            for sq in set(js) | set(py):
                n_val += 1
                a, bb = js.get(sq), py.get(sq)
                if not a or not bb or abs(a[0] - bb[0]) > 0.02 or abs(a[1] - bb[1]) > 0.02:
                    dif.append("%s / %s: JS %s x Python %s" % (mun, cands.get(sq, {}).get("urna", sq), a, bb))
        reg(S6, "FALHA" if sem_chave else "OK", "todo municipio de RO escolhido no Perfil acha a sua lista de emendas", sem_chave)
        nulos = pg.evaluate("""(muns) => muns.filter((mun) => { App.setPerfil({ uf: 'RO', mun }); return !App.temEmendasMun(); })""", MUNS["RO"])
        reg(S6, "FALHA" if nulos else "OK", "no navegador, todo municipio de RO do Perfil tem emendas por municipio disponiveis", nulos)
        reg(S6, "FALHA" if dif else "OK", "emendas por municipio: navegador = Python nos %d municipios de RO (%d pares candidato x municipio)" % (n_mun, n_val), dif)

        # concordancia: posicoes sorteadas nas 3 Casas; navegador x Python
        pos = {}
        for casa, lista, sim, nao in (("alero", AL["vot"], "S", "N"), ("camara", VF["camara"]["vot"], "S", "N"), ("senado", VF["senado"]["vot"], "S", "N")):
            for x in rnd.sample(lista, 15):
                pos["%s:%s" % (casa, x["id"])] = rnd.choice([sim, nao])
        js = pg.evaluate("""(pos) => { const d = App.Store.ler(); d.posicoes = pos; App.Store.salvar(); const out = {};
          for (const c of App.Dados.cache.RO) { const r = App.concordancia(c); if (r.total) out[c.sq] = [r.iguais, r.total]; } return out; }""", pos)
        idx = {"alero": {str(x["id"]): x for x in AL["vot"]}, "camara": {str(x["id"]): x for x in VF["camara"]["vot"]}, "senado": {str(x["id"]): x for x in VF["senado"]["vot"]}}
        porcand = {"alero": AL["porCand"], "camara": VF["camara"]["porCand"], "senado": VF["senado"]["porCand"]}
        simnao = {"S": "S", "N": "N", "Sim": "S", "Não": "N"}
        py = {}
        for sq in cands:
            ig = tot = 0
            for k, minha in pos.items():
                casa, vid = k.split(":", 1)
                pid = porcand[casa].get(sq)
                x = idx[casa].get(vid)
                if not pid or not x or simnao.get(x["v"].get(pid)) is None:
                    continue
                tot += 1; ig += simnao[x["v"][pid]] == minha
            if tot:
                py[sq] = [ig, tot]
        dif = ["%s: JS %s x Python %s" % (cands[sq]["urna"], js.get(sq), py.get(sq)) for sq in set(js) | set(py) if js.get(sq) != py.get(sq)]
        reg(S6, "FALHA" if dif else "OK", "concordancia com 45 posicoes sorteadas (15 por Casa): navegador = Python para os %d candidatos comparaveis" % len(py), dif)
        pg.evaluate("localStorage.clear()")
        b.close()
except ImportError:
    reg(S6, "ALERTA", "Playwright nao instalado: parte 6 (JS) nao rodou")

# =====================================================================================================
SAIDA.mkdir(parents=True, exist_ok=True)
rel = SAIDA / "auditoria_cruzada.md"
with open(rel, "w", encoding="utf-8") as f:
    f.write("# Auditoria cruzada dos dados - %s\n\n" % datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    f.write("Amostras sorteadas com semente fixa (2026), %d itens por verificacao. OK %d · FALHA %d · ALERTA %d · INFO %d. Tempo: %.0f s.\n\n"
            % (N, contagem["OK"], contagem["FALHA"], contagem["ALERTA"], contagem["INFO"], time.time() - t0))
    f.write("FALHA = erro nosso (dado diferente da fonte). ALERTA = divergencia da propria fonte ou caso para revisar.\n")
    sec = None
    for s, nivel, msg, ex in achados:
        if s != sec:
            f.write("\n## %s\n\n" % s); sec = s
        f.write("- **%s** %s\n" % (nivel, msg))
        for e in ex[:15]:
            f.write("  - %s\n" % e)
        if len(ex) > 15:
            f.write("  - ... e mais %d\n" % (len(ex) - 15))
print("\nRESULTADO: %d OK, %d FALHA, %d ALERTA, %d INFO (%.0f s) -> %s" % (contagem["OK"], contagem["FALHA"], contagem["ALERTA"], contagem["INFO"], time.time() - t0, rel))
sys.exit(1 if contagem["FALHA"] else 0)
