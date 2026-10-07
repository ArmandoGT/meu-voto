"""
Gera data/resultados_XX.js (window.RES_XX) com o resultado das eleicoes 2026 por UF (e RES_BR p/ Presidente).

Entradas (raw/):
  resultados2026/t1/*.json                  site de divulgacao do TSE (scripts/fetch_resultados.py)
  votacao_candidato_munzona_2026.zip        dados abertos: votos de cada candidato por municipio e zona

Para os cargos proporcionais (deputados) recalcula a distribuicao das vagas com as regras atuais
(Codigo Eleitoral arts. 106 a 109, Lei 14.211/2021, e STF ADIs 7228/7263/7325 de 2024) e confere com o
resultado do TSE. Se nao bater, o script para: a explicacao "por que nao foi eleito" so e gerada sobre um
calculo que reproduz exatamente o oficial.

Estrutura de RES_XX:
  meta  {uf turno fonte dg hg secoesPct}
  muns  {codTSE: [nome, eleitores, comparecimento, abstencao]}
  cargos {nomeCargo: {cd nv qe tot{...} agr[] vagas[] cand{sq: {...}} fora[]}}
    agr[i]  {nome sigla tipo comp votos nom leg qp vQP vMed vag ok80}
    vagas[] [sq, fase('qp'|'m2'|'m3'), agrIdx, media]   em ordem de preenchimento
    cand[sq] {n nome sg a v p pos st e dvt mun[[cod,v]] x{...}}

Somente stdlib.
"""
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
DATA = os.path.join(ROOT, "data")
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
ELE = {1: (6257, 6259), 2: (6258, 6260)}
NOME_CARGO = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual",
              8: "Deputado Distrital"}
PROPORCIONAIS = (6, 7, 8)

csv.field_size_limit(10 ** 8)


def inteiro(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).replace("d oeste", "do oeste")
    return re.sub(r"\s+", " ", s).strip()


def ler_json(caminho):
    """Os arquivos de dados vem em UTF-8; os de configuracao, em latin-1."""
    with open(caminho, "rb") as f:
        b = f.read()
    try:
        return json.loads(b.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(b.decode("latin-1"))


def nasc_ord(dt):
    """'30/01/1959' -> 19590130 (menor = mais velho; desempate da lei favorece o mais idoso)."""
    try:
        d, m, a = dt.split("/")
        return int(a) * 10000 + int(m) * 100 + int(d)
    except (AttributeError, ValueError):
        return 99999999


# ---------------------------------------------------------------- calculo das vagas (proporcional)
def calcular_vagas(agrs, nv, extra=None):
    """
    agrs: lista de {"votos": int, "cands": [(sq, votos, nascOrd), ...]} (so candidatos com voto valido).
    extra: (agrIdx, sq, x) soma x votos a um candidato (e ao partido e aos validos) p/ simular.
    Devolve (qe, vagas[], porAgr[]) onde vagas = [(agrIdx, sq, fase, media)].
    """
    votos = [a["votos"] for a in agrs]
    cands = [a["cands"] for a in agrs]
    validos = sum(votos)
    if extra:
        ia, sqx, x = extra
        votos = list(votos)
        votos[ia] += x
        validos += x
        cands = list(cands)
        cands[ia] = [(s, v + x if s == sqx else v, n) for s, v, n in cands[ia]]
    # quociente eleitoral: fracao ate 0,5 desprezada, acima arredonda (CE art. 106)
    qe = int(validos / nv + 0.5) if validos % nv * 2 != nv else validos // nv
    if qe <= 0:
        return 0, [], [0] * len(agrs)
    ordem = [sorted(c, key=lambda t: (-t[1], t[2])) for c in cands]
    usados = [0] * len(agrs)      # quantos da lista ja foram eleitos
    vag = [0] * len(agrs)
    vagas = []
    # 1a fase: quociente partidario, candidato precisa de 10% do QE (CE art. 108)
    for i, v in enumerate(votos):
        qp = v // qe
        for _ in range(qp):
            if usados[i] < len(ordem[i]) and ordem[i][usados[i]][1] * 10 >= qe:
                vagas.append((i, ordem[i][usados[i]][0], "qp", None))
                usados[i] += 1
                vag[i] += 1
            else:
                break
    # 2a fase: sobras entre partidos com 80% do QE e candidatos com 20% do QE (CE art. 109, I e II)
    while len(vagas) < nv:
        melhor = None
        for i, v in enumerate(votos):
            if v * 10 < qe * 8 or usados[i] >= len(ordem[i]) or ordem[i][usados[i]][1] * 5 < qe:
                continue
            media = v / (vag[i] + 1)
            if melhor is None or media > melhor[1] or (media == melhor[1] and v > votos[melhor[0]]):
                melhor = (i, media)
        if melhor is None:
            break
        i = melhor[0]
        vagas.append((i, ordem[i][usados[i]][0], "m2", melhor[1]))
        usados[i] += 1
        vag[i] += 1
    # 3a fase: o que sobrar vai para todos os partidos pela maior media, sem exigencias (STF, ADI 7228)
    while len(vagas) < nv:
        melhor = None
        for i, v in enumerate(votos):
            if usados[i] >= len(ordem[i]) or v <= 0:
                continue
            media = v / (vag[i] + 1)
            if melhor is None or media > melhor[1] or (media == melhor[1] and v > votos[melhor[0]]):
                melhor = (i, media)
        if melhor is None:
            break
        i = melhor[0]
        vagas.append((i, ordem[i][usados[i]][0], "m3", melhor[1]))
        usados[i] += 1
        vag[i] += 1
    return qe, vagas, vag


def votos_para_eleger(agrs, nv, ia, sq, v_atual, teto):
    """Menor x tal que o candidato seria eleito com x votos a mais (demais votos iguais). None se > teto."""
    def eleito(x):
        _, vagas, _ = calcular_vagas(agrs, nv, (ia, sq, x))
        return any(s == sq for _, s, _, _ in vagas)
    if not eleito(teto):
        return None
    lo, hi = 0, teto
    while hi - lo > 1:
        meio = (lo + hi) // 2
        if eleito(meio):
            hi = meio
        else:
            lo = meio
    return hi


def votos_para_partido(agrs, nv, ia, teto):
    """Menor x de votos a mais para a agremiacao ganhar mais uma vaga (com o 1o da fila apto). None se > teto."""
    base = calcular_vagas(agrs, nv)[2][ia]
    fila = sorted(agrs[ia]["cands"], key=lambda t: (-t[1], t[2]))
    if len(fila) <= base:
        return None
    # votos de legenda: simula somando ao partido sem mudar candidatos (sq inexistente)
    def ganha(x):
        return calcular_vagas(agrs, nv, (ia, "__legenda__", x))[2][ia] > base
    if not ganha(teto):
        return None
    lo, hi = 0, teto
    while hi - lo > 1:
        meio = (lo + hi) // 2
        if ganha(meio):
            hi = meio
        else:
            lo = meio
    return hi


# ---------------------------------------------------------------- leitura
def nomes_municipios(cfgs):
    """codTSE -> (uf, nome com acentos da lista oficial do sistema)."""
    oficiais = {}
    try:
        with open(os.path.join(DATA, "municipios.js"), encoding="utf-8") as f:
            txt = f.read()
        mun = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
        for uf, nomes in mun.items():
            for n in nomes:
                oficiais[(uf, norm(n))] = n
    except (OSError, ValueError):
        pass
    out = {}
    for cfg in cfgs:
        for a in cfg.get("abr", []):
            uf = a["cd"].upper()
            for m in a.get("mu", []):
                nm = m.get("nm", "")
                out[m["cd"]] = (uf, oficiais.get((uf, norm(nm)), nm.title()), m.get("cdi"))
    return out


def votos_munzona(zip_path, ufs):
    """{uf: {cdCargo: {sq: {codTSE: votos}}}} somando as zonas. Le os CSVs por UF (o _BRASIL tem 3 GB)."""
    out = {}
    if not os.path.exists(zip_path):
        print("  AVISO: %s ausente; sem votos por municipio" % os.path.basename(zip_path))
        return out, None
    gerado = None
    with zipfile.ZipFile(zip_path) as z:
        for uf in ufs:
            nome = "votacao_candidato_munzona_2026_%s.csv" % uf
            if nome not in z.namelist():
                continue
            d = out.setdefault(uf, {})
            with z.open(nome) as f:
                for row in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"):
                    if row["NR_TURNO"] != "1":
                        continue
                    gerado = gerado or "%s %s" % (row["DT_GERACAO"], row["HH_GERACAO"])
                    cargo = int(row["CD_CARGO"])
                    m = "%05d" % int(row["CD_MUNICIPIO"])
                    porSq = d.setdefault(cargo, {}).setdefault(row["SQ_CANDIDATO"], {})
                    porSq[m] = porSq.get(m, 0) + inteiro(row["QT_VOTOS_NOMINAIS"])
            sys.stdout.write("\r  votos por municipio: %s   " % uf)
            sys.stdout.flush()
    print()
    return out, gerado


def totais(doc):
    s, e, v = doc.get("s", {}), doc.get("e", {}), doc.get("v", {})
    return {
        "secoes": inteiro(s.get("ts")), "secoesTot": inteiro(s.get("st")),
        "eleitores": inteiro(e.get("te")), "comp": inteiro(e.get("c")), "abst": inteiro(e.get("a")),
        "votos": inteiro(v.get("tv")), "validos": inteiro(v.get("vv")), "nominais": inteiro(v.get("vnom")),
        "legenda": inteiro(v.get("vl")), "brancos": inteiro(v.get("vb")), "nulos": inteiro(v.get("tvn")),
        "anulados": inteiro(v.get("vansj")) + inteiro(v.get("van")),
        # base da maioria absoluta: validos + anulados sub judice (o TSE so proclama se nem esses votos mudarem o resultado)
        "baseMaioria": inteiro(v.get("vvc")) or inteiro(v.get("vv")),
    }


def cargo_resultado(doc, votos_mun):
    """Monta o bloco de um cargo a partir do arquivo -u do TSE."""
    c = doc["carg"][0]
    cd = int(c["cd"])
    nv = inteiro(c.get("nv"))
    tot = totais(doc)
    agr_out, cand = [], {}
    agrs_calc = []
    for a in c.get("agr", []):
        nom = sum(inteiro(p.get("tvtn")) for p in a["par"])
        leg = sum(inteiro(p.get("tvtl")) for p in a["par"])
        siglas = [p["sg"] for p in a["par"]]
        ia = len(agr_out)
        agr_out.append({"nome": a.get("nm"), "sigla": a.get("com") or "/".join(siglas), "tipo": a.get("tp"),
                        "votos": nom + leg, "nom": nom, "leg": leg, "vag": inteiro(a.get("vag"))})
        lista = []
        for p in a["par"]:
            for k in p.get("cand", []):
                sq = k["sqcand"]
                valido = k.get("dvt", "").startswith("V")
                cand[sq] = {"n": k["n"], "nome": k.get("nmu") or k.get("nm"), "sg": p["sg"], "a": ia,
                            "v": inteiro(k.get("vap")), "p": float((k.get("pvapn") or "0").replace(",", ".")),
                            "pos": inteiro(k.get("seq")), "st": k.get("st"),
                            # "e" do TSE tambem vale "s" p/ quem foi ao 2o turno: eleito so pela situacao
                            "e": 1 if (k.get("st") or "").lower().startswith("eleit") else 0,
                            "dvt": k.get("dvt")}
                if k.get("vs"):
                    cand[sq]["vice"] = [x.get("nmu") or x.get("nm") for x in k["vs"]]
                mun = (votos_mun or {}).get(sq)
                if mun:
                    cand[sq]["mun"] = sorted(([m, v] for m, v in mun.items() if v > 0), key=lambda t: -t[1])
                if valido:
                    lista.append((sq, cand[sq]["v"], nasc_ord(k.get("dt"))))
        agrs_calc.append({"votos": nom + leg, "cands": lista})
    bloco = {"cd": cd, "nv": nv, "tot": tot, "agr": agr_out, "cand": cand,
             # oficial = TSE terminou a totalizacao e proclamou a situacao de cada candidato
             "oficial": doc.get("tf") == "s" and any(k["st"] for k in cand.values())}
    if doc.get("mntf"):
        bloco["aviso"] = doc["mntf"]
    if cd in PROPORCIONAIS:
        proporcional(bloco, c, agrs_calc)
    else:
        majoritario(bloco)
    return bloco


def proporcional(bloco, c, agrs_calc):
    nv, cand, agr = bloco["nv"], bloco["cand"], bloco["agr"]
    qe, vagas, vag = calcular_vagas(agrs_calc, nv)
    qe_tse = inteiro(c.get("qe"))
    eleitos_tse = {sq for sq, k in cand.items() if k["e"]}
    eleitos_calc = {sq for _, sq, _, _ in vagas}
    if not bloco["oficial"]:
        # ainda sem proclamacao: mostra a projecao pelo calculo da lei, marcada como tal
        for i, a in enumerate(agr):
            a["vag"] = vag[i]
        for sq in eleitos_calc:
            cand[sq]["pe"] = 1
    elif qe != qe_tse or eleitos_tse != eleitos_calc or any(a["vag"] != vag[i] for i, a in enumerate(agr)):
        raise SystemExit("ERRO: calculo das vagas nao reproduz o TSE (%s): qe %d x %d, eleitos a mais %s, a menos %s" % (
            NOME_CARGO[bloco["cd"]], qe, qe_tse, sorted(eleitos_calc - eleitos_tse), sorted(eleitos_tse - eleitos_calc)))
    bloco["qe"] = qe
    bloco["vagas"] = [[sq, fase, i, round(m, 2) if m else None] for i, sq, fase, m in vagas]
    for i, a in enumerate(agr):
        a["qp"] = a["votos"] // qe if qe else 0
        a["vQP"] = sum(1 for j, _, f, _ in vagas if j == i and f == "qp")
        a["vMed"] = a["vag"] - a["vQP"]
        a["ok80"] = a["votos"] * 10 >= qe * 8
    eleitos = sorted((cand[sq] for sq in eleitos_calc), key=lambda k: k["v"])
    menor_eleito = eleitos[0]["v"] if eleitos else 0
    # posicao de cada candidato na lista da propria agremiacao
    for i, ac in enumerate(agrs_calc):
        fila = sorted(ac["cands"], key=lambda t: (-t[1], t[2]))
        for k, (sq, _, _) in enumerate(fila):
            cand[sq]["lst"] = k + 1
    teto = qe * 3 + (eleitos[-1]["v"] if eleitos else 0)
    for sq, k in cand.items():
        if sq in eleitos_calc:
            if k["v"] > qe:
                k["x"] = {"sobra": k["v"] - qe}   # votos acima do QE ajudaram a eleger colegas da lista
            continue
        i = k["a"]
        a = agr[i]
        x = {"vagAgr": a["vag"], "lst": k.get("lst"), "pc10": k["v"] * 10 >= qe, "pc20": k["v"] * 5 >= qe}
        if not k["dvt"].startswith("V"):
            x["anulado"] = 1
            k["x"] = x
            continue
        if a["vag"]:
            ult = min((cand[s] for j, s, _, _ in vagas if j == i), key=lambda t: t["v"])
            x["ultAgr"] = [ult["nome"], ult["v"]]
        # eleitos com menos votos (o que mais gera duvida)
        menos = [s for s in eleitos_calc if cand[s]["v"] < k["v"]]
        if menos:
            x["menos"] = len(menos)
            x["menosEx"] = [[cand[s]["nome"], cand[s]["v"], agr[cand[s]["a"]]["sigla"]]
                            for s in sorted(menos, key=lambda s: cand[s]["v"])[:3]]
        # quantos votos a mais o candidato precisaria (simulacao refazendo todo o calculo)
        if k["v"] * 20 >= menor_eleito or k.get("lst", 99) <= a["vag"] + 3:
            x["falta"] = votos_para_eleger(agrs_calc, nv, i, sq, k["v"], teto)
        if not a["vag"]:
            x["faltaAgr"] = votos_para_partido(agrs_calc, nv, i, teto)
        k["x"] = x
    bloco["menorEleito"] = menor_eleito


def majoritario(bloco):
    cand, nv, validos = bloco["cand"], bloco["nv"], bloco["tot"]["validos"]
    ordem = sorted(cand.values(), key=lambda k: -k["v"])
    maioria = bloco["tot"]["baseMaioria"] // 2 + 1
    if not bloco["oficial"]:
        # projecao: Presidente/Governador precisam de maioria absoluta dos validos; Senador, os nv mais votados
        validos_c = [k for k in ordem if k["dvt"].startswith("V")]
        if bloco["cd"] in (1, 3) and validos_c and validos_c[0]["v"] < maioria:
            for k in validos_c[:2]:
                k["p2"] = 1
        else:
            for k in validos_c[:nv]:
                k["pe"] = 1
    eleitos = [k for k in ordem if k["e"] or k.get("pe")]
    segundo = [k for k in ordem if "2" in (k["st"] or "") or k.get("p2")]
    bloco["maioria"] = maioria if bloco["cd"] in (1, 3) else None
    for k in ordem:
        if k in eleitos:
            continue
        x = {}
        if not k["dvt"].startswith("V"):
            x["anulado"] = 1
        elif eleitos:
            alvo = eleitos[-1]
            x["ult"] = [alvo["nome"], alvo["v"]]
            x["falta"] = alvo["v"] - k["v"] + 1
        if bloco["cd"] in (1, 3) and k in segundo:
            x["maioria"] = max(0, maioria - k["v"])
        elif bloco["cd"] in (1, 3) and segundo:
            x["ult"] = [segundo[-1]["nome"], segundo[-1]["v"]]
            x["falta"] = segundo[-1]["v"] - k["v"] + 1
        k["x"] = x
    bloco["segundoTurno"] = [k["n"] for k in segundo]


# ---------------------------------------------------------------- saida
def write_js(path, varname, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.%s=" % varname)
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def main():
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--turno", type=int, default=1)
    ap.add_argument("--ufs", default="todas")
    a = ap.parse_args()
    t0 = time.time()
    pasta = os.path.join(RAW, "resultados2026", "t%d" % a.turno)
    if not os.path.isdir(pasta):
        raise SystemExit("Rode antes: python scripts/fetch_resultados.py")
    fed, est = ELE[a.turno]
    ufs = UFS if a.ufs == "todas" else [u.strip().upper() for u in a.ufs.split(",") if u.strip() and u.strip().upper() != "BR"]
    cfgs = [ler_json(os.path.join(pasta, "config", n)) if os.path.exists(os.path.join(pasta, "config", n)) else
            ler_json(os.path.join(pasta, n)) for n in ("mun-e%06d-cm.json" % fed, "mun-e%06d-cm.json" % est)
            if os.path.exists(os.path.join(pasta, "config", n)) or os.path.exists(os.path.join(pasta, n))]
    munis = nomes_municipios(cfgs)
    votos, gerado_mz = votos_munzona(os.path.join(RAW, "votacao_candidato_munzona_2026.zip"), ufs)

    pres_uf = {}     # votos de presidente por UF (p/ RES_BR)
    estados = {"Governador": {}, "Senador": {}}   # resumo por UF (3 mais votados) p/ o mapa do Brasil desses cargos
    pres_mun = {}    # sq -> {codTSE: votos} de todas as UFs (site do TSE, municipio a municipio)
    arq_pm = os.path.join(pasta, "pres_mun.json")
    if os.path.exists(arq_pm):
        with open(arq_pm, encoding="utf-8") as f:
            for m, r in json.load(f).items():
                for sq, v in r["v"].items():
                    pres_mun.setdefault(sq, {})[m] = v
    for uf in ufs:
        u = uf.lower()
        res = {"meta": {"uf": uf, "turno": a.turno, "munzona": gerado_mz}, "muns": {}, "cargos": {}}
        ab = os.path.join(pasta, "%s-e%06d-ab.json" % (u, est))
        if os.path.exists(ab):
            for m in ler_json(ab).get("abr", []):
                if m.get("tpabr") != "mun":
                    continue
                e = m.get("e", {})
                nome = munis.get(m["cdabr"], (uf, m["cdabr"]))[1]
                res["muns"][m["cdabr"]] = [nome, inteiro(e.get("te")), inteiro(e.get("c")), inteiro(e.get("a"))]
        for cd in (3, 5, 6, 7, 8):
            arq = os.path.join(pasta, "%s-c%04d-e%06d-u.json" % (u, cd, est))
            if not os.path.exists(arq):
                continue
            doc = ler_json(arq)
            res["meta"].update({"dg": doc.get("dg"), "hg": doc.get("hg"), "dt": doc.get("dt"), "ht": doc.get("ht")})
            res["cargos"][NOME_CARGO[cd]] = cargo_resultado(doc, votos.get(uf, {}).get(cd))
        for nome_c, resumo in estados.items():
            blc = res["cargos"].get(nome_c)
            if blc:
                ordem = sorted(blc["cand"].items(), key=lambda x: -x[1]["v"])[:3]
                resumo[uf] = {"base": blc["tot"].get("baseMaioria") or blc["tot"]["validos"], "oficial": blc.get("oficial"),
                              "c": [dict({c: k[c] for c in ("n", "nome", "sg", "v", "st", "dvt", "e", "pe", "p2") if c in k}, sq=sq) for sq, k in ordem]}
        arq = os.path.join(pasta, "%s-c0001-e%06d-u.json" % (u, fed))
        if os.path.exists(arq):
            doc = ler_json(arq)
            bl = cargo_resultado(doc, votos.get(uf, {}).get(1))
            pres_uf[uf] = {"tot": bl["tot"], "v": {sq: k["v"] for sq, k in bl["cand"].items()}}
        write_js(os.path.join(DATA, "resultados_%s.js" % uf), "RES_%s" % uf, res)
        dep = res["cargos"].get("Deputado Federal", {})
        print("  %s: %d municipios, Dep. Federal QE %s, %d eleitos" % (
            uf, len(res["muns"]), dep.get("qe"), sum(1 for k in dep.get("cand", {}).values() if k["e"])))

    arq = os.path.join(pasta, "br-c0001-e%06d-u.json" % fed)
    if os.path.exists(arq) and a.ufs == "todas":
        doc = ler_json(arq)
        bl = cargo_resultado(doc, pres_mun)
        zz = os.path.join(pasta, "zz-c0001-e%06d-u.json" % fed)
        if os.path.exists(zz):
            dz = cargo_resultado(ler_json(zz), None)
            pres_uf["ZZ"] = {"tot": dz["tot"], "v": {sq: k["v"] for sq, k in dz["cand"].items()}}
        bl["porUf"] = pres_uf
        muns_br = {m: [nome, uf] for m, (uf, nome, _) in munis.items()}
        res = {"meta": {"uf": "BR", "turno": a.turno, "munzona": gerado_mz, "dg": doc.get("dg"), "hg": doc.get("hg"),
                        "dt": doc.get("dt"), "ht": doc.get("ht")},
               "muns": muns_br, "cargos": {"Presidente": bl}, "estados": estados}
        write_js(os.path.join(DATA, "resultados_BR.js"), "RES_BR", res)
        print("  BR: Presidente, %d UFs + exterior, %d municipios" % (len(pres_uf), len(muns_br)))
    print("Pronto em %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
