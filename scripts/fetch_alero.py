# -*- coding: utf-8 -*-
"""
fetch_alero.py - votacoes NOMINAIS da Assembleia Legislativa de Rondonia (ALE-RO), com o voto de cada deputado
estadual, a partir da API publica do SAPL (https://sapl.al.ro.leg.br/api/). Grava data/alero.js.

Precisa de internet. Nao precisa de chave. Somente stdlib. ~15 min (cerca de 800 paginas da API, 4 de cada vez).

Uso:
    python scripts/fetch_alero.py                # baixa tudo (guarda o bruto em raw/alero_sapl.json) e gera data/alero.js
    python scripts/fetch_alero.py --sem-baixar   # so reprocessa raw/alero_sapl.json (casamento, alias) - segundos
    python scripts/fetch_alero.py --so-simbolicas  # baixa de novo so as leis (fase 2) e reprocessa - ~5 min

Fase 2 - leis sem voto individual (votacao simbolica): todo projeto de lei, lei complementar e PEC aprovado ou
rejeitado em plenario desde 01/02/2023 (legislatura atual), pela tramitacao do SAPL - criterio objetivo, sem escolha
editorial de "votacoes importantes". Traz autoria, texto da tramitacao, lei gerada e se houve votacao nominal.
Posicoes individuais so entram por data/alero_declaracoes.json, com documento OFICIAL (ata etc.) e link.
Lista de presenca NAO e usada: presenca nao e voto (a ALE-RO registrou isso na ata n. 252, de 09/02/2026).

O que existe na fonte (e o que NAO existe):
    * So ha voto individual nas votacoes nominais: vetos, leis complementares, PECs e algumas outras.
      Projeto de lei ordinaria costuma ser votacao SIMBOLICA - o presidente declara o resultado e nao ha registro
      de quem votou como (ex.: PL 1243/2025, Lei 6.328/2026). Esses casos nao entram aqui.
    * A ALE-RO lanca os votos no SAPL com atraso: veja "ultimaVotacao" no arquivo gerado.
    * Voto registrado: Sim, Nao, Abstencao, Ausente, Nao votou (e "-1" = sem registro).
    * A mesma pessoa pode ter dois cadastros no SAPL (ex.: um ate 2019 e outro depois). Cadastros com o mesmo
      nome civil, ou casados com o mesmo candidato, viram um so (fica o id do cadastro com voto mais recente).

Casamento deputado (SAPL) -> candidato 2026 (qualquer cargo em RO):
    1) nome civil completo igual (sem acentos/maiusculas) ao nome do candidato no TSE;
    2) senao, nome civil QUASE igual: mesmo primeiro nome e todas as palavras do nome mais curto presentes no outro,
       com no maximo uma letra de diferenca por palavra (erros de digitacao reais: Sheffer/Scheffer,
       Rosangela/Rozangela, Izequiel/Isequiel; "Alexandro Barroso Duarte [Santana]"). Junior/Filho/Neto em so um dos
       nomes = outra pessoa (Jair Figueiredo Monte x Jair Montes Jr.). E o candidato precisa ter disputado Deputado
       Estadual em RO (historico TSE). Vai para o log ("obs.").
       Nome de urna parecido NAO basta: "Kaka Mendonca" (Joao Ricardo) nao e "Jean Mendonca" (Jean Henrique),
       e "Zequinha Araujo" (Jose Francisco) nao e "Dr. Ribamar Araujo" (Jose Ribamar).
    3) correcoes manuais em data/alero_alias.json: {"<id do parlamentar no SAPL>": "<sq do candidato>" ou null}.
    Neutralidade: o arquivo so guarda o que a fonte oficial registra. Nenhum voto e classificado como bom ou ruim.
"""
import collections
import concurrent.futures
import datetime
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(ROOT, "raw")
BRUTO = os.path.join(RAW, "alero_sapl.json")
SAPL = "https://sapl.al.ro.leg.br"
API = SAPL + "/api/"

# voto na fonte -> codigo curto no arquivo
VOTO = {"sim": "S", "nao": "N", "abstencao": "A", "ausente": "U", "nao votou": "X", "-1": "?"}


def sem_acento(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sem_acento(s).lower()).split())


PARTICULAS = {"da", "de", "do", "das", "dos", "e"}
GERACAO = {"junior", "jr", "filho", "filha", "neto", "neta", "sobrinho", "segundo", "terceiro"}


def tokens(nome):
    return [t for t in norm(nome).split() if t not in PARTICULAS]


def uma_letra(a, b):
    """True se a e b sao iguais ou diferem em no maximo uma letra (troca, insercao ou remocao)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))


def nome_quase_igual(n1, n2):
    """Mesmo primeiro nome e todas as palavras do nome mais curto no outro (uma letra de tolerancia por palavra)."""
    t1, t2 = tokens(n1), tokens(n2)
    if len(t1) < 2 or len(t2) < 2 or not uma_letra(t1[0], t2[0]):
        return False
    # pai x filho: "Jair Figueiredo Monte" nao e "Jair de Figueiredo Monte Junior"
    if set(t1) & GERACAO != set(t2) & GERACAO:
        return False
    curto, longo = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    return all(any(uma_letra(a, b) for b in longo) for a in curto)


def get_json(url, tentativas=5):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "MeuVoto2026/1.0"})
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                raise SystemExit("A API do SAPL falhou em %s: %s - rode de novo mais tarde." % (url, e))
            time.sleep(2 ** (i + 1))


def paginar(caminho, rotulo, paralelo=4):
    """Todas as paginas de um endpoint (100 por pagina, o maximo da API), 4 de cada vez (a API leva ~2 s por pagina).
    SEMPRE ordenado por id (o=id): sem ordem explicita o SAPL devolve paginas instaveis - as paginas 1 e 2 da ordem do
    dia repetiam 84 de 100 registros, e registros sumiam (auditoria de 23/09/2026). No fim confere o total."""
    sep = "&" if "?" in caminho else "?"
    url = lambda n: "%s%s%so=id&page_size=100&page=%d" % (API, caminho, sep, n)
    primeira = get_json(url(1))
    total = primeira["pagination"]["total_pages"]
    paginas = {1: primeira["results"]}
    feitas = [1]

    def baixar(n):
        r = get_json(url(n))["results"]
        feitas[0] += 1
        if feitas[0] % 50 == 0:
            print("  %s: %d de %d paginas" % (rotulo, feitas[0], total))
        return n, r

    with concurrent.futures.ThreadPoolExecutor(paralelo) as ex:
        for n, r in ex.map(baixar, range(2, total + 1)):
            paginas[n] = r
    print("  %s: %d paginas" % (rotulo, total))
    out = [x for n in sorted(paginas) for x in paginas[n]]
    esperado = primeira["pagination"]["total_entries"]
    unicos = len({x["id"] for x in out})
    if unicos != esperado or len(out) != esperado:
        raise SystemExit("%s: a API informa %d registros e vieram %d (%d unicos) - download inconsistente, rode de novo."
                         % (rotulo, esperado, len(out), unicos))
    return out


def carregar_candidatos(uf):
    p = os.path.join(DATA, "cand_%s.js" % uf)
    if not os.path.exists(p):
        return []
    txt = open(p, encoding="utf-8").read()
    return json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))


# "Ordem: ... - Projeto de Lei Complementar nº 112 de 2013 em 8ª Sessão Ordinária da ... - Votação: Aprovada"
RE_MATERIA = re.compile(r"- (.+?) n\S* (\d+) de (\d{4}) em (.+?) - Vota\S+: (.*)$")
SIGLA = {"projeto de lei complementar": "PLC", "projeto de lei ordinaria": "PL", "proposta de emenda constitucional": "PEC",
         "veto total": "Veto total", "veto parcial": "Veto parcial", "projeto de decreto legislativo": "PDL",
         "projeto de resolucao": "PR", "requerimento": "REQ", "indicacao": "IND", "substitutivo a projeto de lei": "Substitutivo",
         "redacao final": "Redação final", "emenda em deliberada em destaque": "Emenda (destaque)",
         "eleicao cargo da mesa diretora": "Eleição da Mesa Diretora", "conselho de etica e decoro parlamentar": "Conselho de Ética",
         "comissao especial lei n 1079 10 04 1950": "Comissão especial (Lei 1.079/1950)"}


def baixar():
    """Baixa da API so o necessario e devolve {"vot": [...], "parl": {pid: {n, c}}} com os ids originais do SAPL."""
    print("ALE-RO (SAPL): baixando dados")
    votos = paginar("sessao/votoparlamentar/", "votos individuais")
    registros = {r["id"]: r for r in paginar("sessao/registrovotacao/", "registros de votacao")}
    ordens = {o["id"]: o for o in paginar("sessao/ordemdia/", "ordem do dia")}
    expedientes = {o["id"]: o for o in paginar("sessao/expedientemateria/", "materias do expediente")}
    sessoes = {s["id"]: s for s in paginar("sessao/sessaoplenaria/", "sessoes")}
    parl_todos = {p["id"]: p for p in paginar("parlamentares/parlamentar/", "parlamentares")}

    por_votacao = collections.defaultdict(dict)
    sem_codigo = collections.Counter()
    for v in votos:
        bruto = (v.get("voto") or "").strip()
        cod = VOTO.get(bruto) or VOTO.get(norm(bruto))
        if cod is None:
            sem_codigo[bruto] += 1
            cod = "?"
        por_votacao[v["votacao"]][v["parlamentar"]] = cod
    if sem_codigo:
        print("  AVISO: valores de voto desconhecidos (gravados como 'Sem registro'):", dict(sem_codigo))

    vot, sem_registro, ementa_faltando = [], 0, []
    for rid, vs in por_votacao.items():
        r = registros.get(rid)
        if not r:
            sem_registro += 1
            continue
        item = ordens.get(r.get("ordem")) or expedientes.get(r.get("expediente")) or {}
        sessao = sessoes.get(item.get("sessao_plenaria")) or {}
        m = RE_MATERIA.search(r.get("__str__") or "")
        tipo = numero = ano = sessao_nome = None
        resultado = ""
        if m:
            tipo_longo = m.group(1).strip()
            tipo = SIGLA.get(norm(tipo_longo), tipo_longo)
            numero, ano = int(m.group(2)), int(m.group(3))
            sessao_nome, resultado = m.group(4).strip(), m.group(5).strip()
        data = item.get("data_ordem") or item.get("data_sessao") or sessao.get("data_inicio") or (r.get("data_hora") or "")[:10]
        ementa = (item.get("observacao") or "").strip()
        if not ementa and r.get("materia"):
            ementa_faltando.append(r["materia"])
        vot.append({
            "id": rid, "d": data, "t": tipo, "n": numero, "a": ano, "m": r.get("materia"), "e": ementa,
            "r": resultado, "s": item.get("sessao_plenaria"), "sn": sessao_nome or sessao.get("__str__"),
            "sim": r.get("numero_votos_sim"), "nao": r.get("numero_votos_nao"), "abs": r.get("numero_abstencoes"),
            "v": {str(pid): cod for pid, cod in vs.items()},
        })
    if sem_registro:
        print("  AVISO: %d grupos de votos sem registro de votacao correspondente (ignorados)" % sem_registro)

    # ementa: quando a ordem do dia nao traz, busca na propria materia
    faltam = sorted(set(ementa_faltando))
    if faltam:
        print("  buscando ementa de %d materias" % len(faltam))
        ementas = {}
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            for mid, j in zip(faltam, ex.map(lambda mid: get_json("%smateria/materialegislativa/%d/" % (API, mid)), faltam)):
                ementas[mid] = (j.get("ementa") or "").strip()
        for x in vot:
            if not x["e"] and x["m"] in ementas:
                x["e"] = ementas[x["m"]]
    for x in vot:
        x["e"] = " ".join(x["e"].split())

    com_voto = {pid for x in vot for pid in x["v"]}
    parl = {str(pid): {"n": p["nome_parlamentar"], "c": p["nome_completo"]} for pid, p in parl_todos.items() if str(pid) in com_voto}
    return {"baixado": datetime.date.today().isoformat(), "vot": vot, "parl": parl}


# ---------- fase 2: leis aprovadas/rejeitadas sem voto individual registrado (votacao simbolica) ----------
DESDE = "2023-02-01"                        # inicio da legislatura atual (11a, 2023-2027)
TIPOS_LEI = {1: "PL", 5: "PLC", 12: "PEC"}  # projeto de lei, lei complementar, emenda a Constituicao do Estado
ST_PLENARIO = {9: "Aprovada", 33: "Aprovada em 1º turno", 52: "Aprovada em 2º turno", 10: "Rejeitada"}
ST_LEI = (18, 35, 34)                       # transformada em lei / por promulgacao / com veto parcial
RE_LEI = re.compile(r"(Lei(?: Complementar| Ordin\S+)? n\S*\s*[\d.]+,? de \d{1,2}\S* de \w+ de \d{4})", re.I)


def baixar_leis():
    """Projetos de lei, leis complementares e PECs decididos em plenario desde DESDE, com autor e lei gerada."""
    print("ALE-RO (SAPL): leis decididas em plenario desde %s" % DESDE)
    tram = []
    for st in list(ST_PLENARIO) + list(ST_LEI):
        tram += paginar("materia/tramitacao/?status=%d&data_tramitacao__gte=%s" % (st, DESDE), "tramitacao status %d" % st)
    ids = {t["materia"] for t in tram}
    # projetos de lei, LCs e PECs apresentados desde 2011 (por tipo e ano: poucas paginas em vez de uma chamada por materia)
    materias = {}
    for tipo in TIPOS_LEI:
        for ano in range(2011, datetime.date.today().year + 1):
            for m in paginar("materia/materialegislativa/?tipo=%d&ano=%d" % (tipo, ano), "%s %d" % (TIPOS_LEI[tipo], ano)):
                if m["id"] in ids:
                    materias[m["id"]] = m
    print("  %d projetos de lei, leis complementares ou PECs com decisao em plenario ou lei" % len(materias))
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        autorias = dict(zip(materias, ex.map(lambda mid: get_json("%smateria/autoria/?materia=%d&page_size=100" % (API, mid))["results"], materias)))
    autores = {a["id"]: a for a in paginar("base/autor/", "autores")}
    # lei gerada: a fonte certa e a norma juridica publicada (ligada a materia); o texto da tramitacao atrasa
    # ou tem data errada (PL 1243/2025: "de 04 de janeiro" x norma de 04/02/2026)
    tipos_norma = {t["id"]: t["descricao"] for t in paginar("norma/tiponormajuridica/", "tipos de norma")}
    norma_de = {}
    for ano in range(int(DESDE[:4]), datetime.date.today().year + 1):
        for n in paginar("norma/normajuridica/?ano=%d" % ano, "normas %d" % ano):
            if n.get("materia"):
                norma_de[n["materia"]] = n

    por_materia = collections.defaultdict(list)
    for t in tram:
        por_materia[t["materia"]].append(t)
    leis = []
    for mid, m in materias.items():
        ts = sorted(por_materia[mid], key=lambda t: (t["data_tramitacao"], t["id"]))
        dec = [t for t in ts if t["status"] in ST_PLENARIO]
        if not dec:
            continue   # virou lei, mas a decisao em plenario foi antes de DESDE
        ult = dec[-1]
        nj = norma_de.get(mid)
        if nj and str(nj.get("numero") or "").isdigit():
            lei = "%s nº %s" % (tipos_norma.get(nj.get("tipo"), "Lei"), "{:,}".format(int(nj["numero"])).replace(",", "."))
        else:
            lei = next((RE_LEI.search(t["texto"] or "").group(1) for t in reversed(ts) if t["status"] in ST_LEI and RE_LEI.search(t["texto"] or "")), None)
        aut = []
        for x in sorted(autorias.get(mid, []), key=lambda x: not x.get("primeiro_autor")):
            a = autores.get(x["autor"]) or {}
            aut.append({"nome": a.get("nome") or "", "parl": str(a["object_id"]) if a.get("content_type") and a.get("tipo") == 1 and a.get("object_id") else None})
        leis.append({
            "m": mid, "t": TIPOS_LEI[m["tipo"]], "n": m["numero"], "a": m["ano"], "e": " ".join((m.get("ementa") or "").split()),
            "d": ult["data_tramitacao"], "res": ST_PLENARIO[ult["status"]], "txt": " ".join((ult["texto"] or "").split()),
            "lei": lei, "aut": aut,
        })
    return leis


def casar(parl, cands, alias):
    """parl: {pid: {n, c}} -> {pid: sq}"""
    por_nome = collections.defaultdict(list)
    for c in cands:
        por_nome[norm(c["nome"])].append(c)
    ativo = lambda c: not re.search(r"RENUN|INDEFER|CANCEL|CASSA|FALEC", sem_acento(c.get("sit") or "").upper())
    ja_dep_est = lambda c: any(h.get("cargo") == "Deputado Estadual" and h.get("uf") == "RO" for h in c.get("hist") or [])
    out = {}
    for pid, p in parl.items():
        if pid in alias:
            if alias[pid]:
                out[pid] = alias[pid]
                print("  alias: %s -> %s" % (p["n"], alias[pid]))
            continue
        lista = por_nome.get(norm(p["c"]), [])
        if len(lista) > 1:   # mesma pessoa com duas candidaturas: fica a ativa
            lista = [c for c in lista if ativo(c)] or lista
        if len(lista) == 1:
            out[pid] = lista[0]["sq"]
            continue
        if len(lista) > 1:
            print("  AVISO: %s (%s) bate com %d candidatos - nao casado" % (p["n"], p["c"], len(lista)))
            continue
        achados = [c for c in cands if ja_dep_est(c) and nome_quase_igual(p["c"], c["nome"])]
        if len(achados) > 1:
            achados = [c for c in achados if ativo(c)] or achados
        if len(achados) == 1:
            c = achados[0]
            out[pid] = c["sq"]
            print("  obs.: %s (%s) -> %s (%s): nome civil quase igual + historico de deputado estadual"
                  % (p["n"], p["c"], c["urna"], c["nome"]))
        elif len(achados) > 1:
            print("  AVISO: %s empatado entre %s - nao casado" % (p["n"], ", ".join(c["urna"] for c in achados)))
    return out


def processar(bruto):
    vot = sorted(bruto["vot"], key=lambda x: (x["d"] or "", x["id"]), reverse=True)
    parl = bruto["parl"]
    alias_p = os.path.join(DATA, "alero_alias.json")
    alias = json.load(open(alias_p, encoding="utf-8")) if os.path.exists(alias_p) else {}
    alias = {k: v for k, v in alias.items() if not k.startswith("_")}
    cands = carregar_candidatos("RO")
    print("Casando deputados estaduais com candidatos 2026")
    pid_sq = casar(parl, cands, alias)

    # une cadastros da mesma pessoa (mesmo nome civil ou mesmo candidato); fica o id com voto mais recente
    ultimo = {}
    for x in vot:
        for pid in x["v"]:
            ultimo.setdefault(pid, x["d"] or "")
    chave = lambda pid: "sq:" + pid_sq[pid] if pid in pid_sq else "nome:" + norm(parl[pid]["c"])
    grupos = collections.defaultdict(list)
    for pid in parl:
        grupos[chave(pid)].append(pid)
    canon = {}
    for pids in grupos.values():
        pids.sort(key=lambda p: ultimo.get(p, ""), reverse=True)
        for p in pids:
            canon[p] = pids[0]
        if len(pids) > 1:
            print("  mesmo deputado com %d cadastros no SAPL: %s -> fica o id %s"
                  % (len(pids), ", ".join("%s (id %s)" % (parl[p]["n"], p) for p in pids), pids[0]))
    for x in vot:
        novo = {}
        for pid, cod in x["v"].items():
            c = canon[pid]
            # a mesma pessoa nao deveria votar duas vezes; se os cadastros divergirem, vale o voto de fato (nao ausencia)
            if c not in novo or novo[c] in ("U", "X", "?"):
                novo[c] = cod
        x["v"] = novo

    # vetos: nos placares da ALE-RO, Sim = manter o veto e Nao = derrubar (derrubar exige maioria absoluta, 13 de 24).
    # Vale para 710 de 712 vetos; quando o placar registrado nao confere com o resultado, marca para conferir na fonte.
    for x in vot:
        if not (x["t"] or "").startswith("Veto"):
            continue
        r = norm(x["r"])
        nao = sum(1 for v in x["v"].values() if v == "N")
        sim = sum(1 for v in x["v"].values() if v == "S")
        if ("mantid" in r and nao >= 13) or ("rejeit" in r and (nao < 13 or sim > nao)):
            x["confere"] = False
            print("  AVISO: %s %s/%s (%s): placar registrado (Sim %d, Nao %d) nao confere com o resultado '%s'"
                  % (x["t"], x["n"], x["a"], x["d"], sim, nao, x["r"]))

    ids = sorted(set(canon.values()), key=lambda p: parl[p]["n"])

    # fase 2: leis decididas em plenario sem voto individual + declaracoes oficiais
    decl_p = os.path.join(DATA, "alero_declaracoes.json")
    decls = json.load(open(decl_p, encoding="utf-8")).get("declaracoes", []) if os.path.exists(decl_p) else []
    nominal_por_materia = collections.defaultdict(list)
    for x in vot:
        if x.get("m"):
            nominal_por_materia[x["m"]].append(x["id"])
    leis = []
    for l in sorted(bruto.get("leis", []), key=lambda l: (l["d"], l["m"]), reverse=True):
        l = dict(l)
        # so o numero da lei: a data escrita na tramitacao as vezes esta errada na fonte
        # (PL 1243/2025: "Lei 6.328, de 04 de janeiro de 2026", aprovada em 26/01 e publicada em 04/02)
        if l.get("lei"):
            l["lei"] = re.sub(r",?\s+de \d{1,2}\S* de \w+ de \d{4}$", "", l["lei"])
        l["aut"] =[{"nome": a["nome"], "parl": canon.get(a["parl"], a["parl"]) if a.get("parl") else None} for a in l["aut"]]
        if nominal_por_materia.get(l["m"]):
            l["nominal"] = nominal_por_materia[l["m"]]
        ds = [{k: d[k] for k in ("parlamentar", "data", "texto", "fonte", "url")} for d in decls if d.get("materia") == l["m"]]
        for d in ds:
            d["parlamentar"] = canon.get(str(d["parlamentar"]), str(d["parlamentar"]))
        if ds:
            l["decl"] = ds
        leis.append(l)
    sem_lei = [d for d in decls if d.get("materia") not in {l["m"] for l in leis}]
    for d in sem_lei:
        print("  AVISO: declaracao sobre a materia %s, que nao esta na lista de leis decididas desde %s" % (d.get("materia"), DESDE))
    faltam = {a["parl"] for l in leis for a in l["aut"] if a["parl"] and a["parl"] not in ids}
    faltam |= {d["parlamentar"] for l in leis for d in l.get("decl", []) if d["parlamentar"] not in ids}

    saida = {
        "atualizado": bruto.get("baixado"),
        "ultimaVotacao": vot[0]["d"] if vot else None,
        "fonte": SAPL,
        "parl": {p: {"n": parl[p]["n"], "c": parl[p]["c"], "sq": pid_sq.get(p)} for p in ids},
        "porCand": {pid_sq[p]: p for p in ids if p in pid_sq},
        "vot": vot,
        "leis": leis,
        "leisDesde": DESDE,
        "leisAtualizado": bruto.get("leisBaixado"),
    }
    if faltam:
        print("  AVISO: %d autores/declarantes sem voto nominal registrado (sem nome de parlamentar no arquivo): %s" % (len(faltam), sorted(faltam)))
    out = os.path.join(DATA, "alero.js")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.ALERO=")
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(tmp, out)

    por_tipo = collections.Counter(x["t"] for x in vot)
    print()
    print("OK - %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576))
    print("  %d votacoes nominais, de %s a %s" % (len(vot), vot[-1]["d"] if vot else "-", vot[0]["d"] if vot else "-"))
    print("  por tipo:", ", ".join("%s %d" % (k, n) for k, n in por_tipo.most_common()))
    if leis:
        sem_ind = sum(1 for l in leis if not l.get("nominal"))
        print("  %d leis/PECs decididas em plenario desde %s; %d sem voto individual registrado; %d declaracao(oes) oficiais"
              % (len(leis), DESDE, sem_ind, sum(len(l.get("decl", [])) for l in leis)))
    print("  %d deputados com voto registrado; %d casados com candidatos 2026:" % (len(ids), len(saida["porCand"])))
    cand_sq = {c["sq"]: c for c in cands}
    for sq, p in sorted(saida["porCand"].items(), key=lambda x: parl[x[1]]["n"]):
        c = cand_sq.get(sq, {})
        nv = sum(1 for x in vot if p in x["v"])
        print("    %-26s -> %-28s %-18s %5d votos (ultimo %s)" % (parl[p]["n"], c.get("urna"), c.get("cargo"), nv, ultimo.get(p)))


def main():
    t0 = time.time()
    if "--sem-baixar" in sys.argv or "--so-simbolicas" in sys.argv:
        if not os.path.exists(BRUTO):
            raise SystemExit("Nao achei %s - rode sem opcoes primeiro." % BRUTO)
        bruto = json.load(open(BRUTO, encoding="utf-8"))
        print("Usando %s (baixado em %s)" % (BRUTO, bruto.get("baixado")))
        if "--so-simbolicas" in sys.argv:
            bruto["leis"] = baixar_leis()
            bruto["leisBaixado"] = datetime.date.today().isoformat()
    else:
        bruto = baixar()
        bruto["leis"] = baixar_leis()
        bruto["leisBaixado"] = bruto["baixado"]
    if "--sem-baixar" not in sys.argv:
        os.makedirs(RAW, exist_ok=True)
        with open(BRUTO, "w", encoding="utf-8") as f:
            json.dump(bruto, f, ensure_ascii=False, separators=(",", ":"))
    processar(bruto)
    print("  (%.0f s)" % (time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
