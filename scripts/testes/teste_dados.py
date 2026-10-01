# -*- coding: utf-8 -*-
"""
teste_dados.py - confere os arquivos gerados (data/*.js) contra as fontes brutas em raw/.

Uso:  python scripts/testes/teste_dados.py        (sai com codigo 1 se algum teste falhar)

Cobre: candidatos x consulta_cand, arquivos locais (fotos/PDFs), limite de gastos, prestacao de contas x CSV
do TSE, emendas x CSV da CGU, casamento autor -> candidato (sem homonimos), registro de downloads e
atualidade dos dados (avisos, nao falhas).
"""
import collections
import csv
import datetime
import io
import json
import os
import sys
import unicodedata
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(ROOT, "raw")
falhas, oks, avisos = [], [], []


def ok(cond, msg):
    (oks if cond else falhas).append(msg)
    print(("  OK   " if cond else "  FALHA ") + msg)


def aviso(cond, msg):
    if not cond:
        avisos.append(msg)
    print(("  OK   " if cond else "  AVISO ") + msg)


def ler(p):
    t = open(p, encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))


def v(s):
    s = (s or "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


print("1. Candidatos")
man = ler(os.path.join(DATA, "manifest.js"))
cands = {}
dup = 0
for uf in man["ufs"]:
    lst = ler(os.path.join(DATA, "cand_%s.js" % uf))
    ok(len(lst) == man["contagens"][uf]["total"], "cand_%s: %d = manifest" % (uf, len(lst)))
    for c in lst:
        dup += c["sq"] in cands
        cands[c["sq"]] = c
ok(dup == 0, "sem SQ duplicado (%d candidatos)" % len(cands))
ok(not man.get("amostra"), "manifest nao e amostra")
z = zipfile.ZipFile(os.path.join(RAW, "consulta_cand_2026.zip"))
m = [n for n in z.namelist() if n.endswith("_BRASIL.csv")][0]
raw_cand = {r["SQ_CANDIDATO"]: r for r in csv.DictReader(io.TextIOWrapper(z.open(m), encoding="latin-1"), delimiter=";")}
sq_raw = set(raw_cand)
ok(set(cands) <= sq_raw, "todo candidato gerado existe no consulta_cand bruto")

print("1b. Partido, federacao e coligacao (tela Coligacoes)")
nul = lambda x: "" if (x or "").strip() in ("#NULO", "#NE", "-1", "-3") else (x or "").strip()
dif = [sq for sq, c in cands.items() if sq in raw_cand and (
    c.get("nrFederacao", "") != nul(raw_cand[sq]["NR_FEDERACAO"]) or c.get("nomeFederacao", "") != nul(raw_cand[sq]["NM_FEDERACAO"])
    or c.get("sqColigacao", "") != nul(raw_cand[sq]["SQ_COLIGACAO"]) or c.get("tipoAgremiacao", "") != nul(raw_cand[sq]["TP_AGREMIACAO"]))]
ok(not dif, "nrFederacao/nomeFederacao/sqColigacao/tipoAgremiacao = consulta_cand bruto (%d diferentes)" % len(dif))
deps = [c for c in cands.values() if c["cargo"].startswith("Deputado")]
ok(deps and not [c for c in deps if c["tipoAgremiacao"] == "COLIGAÇÃO"], "nenhum deputado em coligacao (EC 97/2017) - %d deputados" % len(deps))
feds = collections.Counter(c["nrFederacao"] for c in cands.values() if c["tipoAgremiacao"] == "FEDERAÇÃO")
ok(set(feds) <= {"100", "101", "102", "103", "104"}, "federacoes nos dados = as 5 registradas no TSE (%s)" % dict(sorted(feds.items())))
ok(all(c["nrFederacao"] and c["nomeFederacao"] for c in cands.values() if c["tipoAgremiacao"] == "FEDERAÇÃO"), "todo candidato federado tem numero e nome da federacao")
grp = collections.defaultdict(set)
for c in cands.values():
    if c["tipoAgremiacao"] == "COLIGAÇÃO":
        grp[c["sqColigacao"]].add((c["coligacao"], c["cargo"], c["uf"]))
ok(all(len(x) == 1 for x in grp.values()), "cada sqColigacao = uma coligacao, um cargo, uma UF (%d coligacoes)" % len(grp))

print("2. Arquivos locais referenciados (fotos, planos, certidoes)")
faltando = []
for c in cands.values():
    for obj in [c] + c.get("chapa", []):
        for p in ([obj["foto"]] if obj.get("foto") else []) + obj.get("propostas", []) + obj.get("certidoes", []):
            if not os.path.exists(os.path.join(ROOT, p)):
                faltando.append(p)
ok(not faltando, "todos os caminhos existem em disco (faltando: %d %s)" % (len(faltando), faltando[:3]))

print("3. Limite de gastos (bug do ponto decimal)")
lim = collections.defaultdict(set)
for c in cands.values():
    if c.get("despesaMax"):
        lim[c["cargo"]].add(c["despesaMax"])
for cargo, vals in sorted(lim.items()):
    print("       %-18s min %14s  max %16s" % (cargo, "{:,.2f}".format(min(vals)), "{:,.2f}".format(max(vals))))
ok(max(max(x) for x in lim.values()) < 200e6, "nenhum limite acima de R$ 200 mi (presidente ~R$ 130 mi)")
ro_fed = [c["despesaMax"] for c in cands.values() if c["uf"] == "RO" and c["cargo"] == "Deputado Federal" and c.get("despesaMax")]
ok(all(abs(x - 3176572.53) < 0.01 for x in ro_fed), "dep. federal RO = R$ 3.176.572,53")

print("4. Prestacao de contas x arquivo bruto (RO)")
zc = zipfile.ZipFile(os.path.join(RAW, "prestacao_de_contas_eleitorais_candidatos_2026.zip"))
rec = collections.defaultdict(float)
for r in csv.DictReader(io.TextIOWrapper(zc.open("receitas_candidatos_2026_RO.csv"), encoding="latin-1"), delimiter=";"):
    rec[r["SQ_CANDIDATO"]] += v(r["VR_RECEITA"])
desp = collections.defaultdict(float)
for r in csv.DictReader(io.TextIOWrapper(zc.open("despesas_contratadas_candidatos_2026_RO.csv"), encoding="latin-1"), delimiter=";"):
    desp[r["SQ_CANDIDATO"]] += v(r["VR_DESPESA_CONTRATADA"])
dif_r = [sq for sq in rec if sq in cands and abs(cands[sq].get("contas", {}).get("rec", 0) - rec[sq]) > 0.05]
dif_d = [sq for sq in desp if sq in cands and abs(cands[sq].get("contas", {}).get("desp", 0) - desp[sq]) > 0.05]
ok(not dif_r, "receita por candidato RO bate com o CSV (%d candidatos, divergentes %d)" % (len(rec), len(dif_r)))
ok(not dif_d, "despesa contratada por candidato RO bate com o CSV (%d, divergentes %d)" % (len(desp), len(dif_d)))
inconsist = []
for c in cands.values():
    ct = c.get("contas")
    if not ct:
        continue
    if abs(sum(ct["fontes"].values()) - ct["rec"]) > 1 or abs(sum(x[1] for x in ct["origens"]) - ct["rec"]) > 1:
        inconsist.append(c["sq"])
ok(not inconsist, "fontes e origens somam o total arrecadado (todos os %d com contas)" % sum(1 for c in cands.values() if c.get("contas")))
ok(all(c["contas"]["nPF"] <= c["contas"]["nDoadores"] for c in cands.values() if c.get("contas")), "nPF <= nDoadores")

print("5. Emendas")
E = ler(os.path.join(DATA, "emendas.js"))
orfaos = [sq for sq in E["porCand"] if sq not in cands]
ok(not orfaos, "todo sq de emendas existe nos candidatos (%d)" % len(E["porCand"]))
orf_it = [x for l in E["porMun"].values() for x in l if x.get("sq") and x["sq"] not in cands]
ok(not orf_it, "todo sq dos itens por municipio existe")
zm = zipfile.ZipFile(os.path.join(RAW, "municipio_tse_ibge.zip"))
mun_ro = set()
for r in csv.DictReader(io.TextIOWrapper(zm.open("municipio_tse_ibge.csv"), encoding="latin-1"), delimiter=";"):
    if r["SG_UF"] == "RO":
        import unicodedata
        mun_ro.add("".join(ch for ch in unicodedata.normalize("NFD", r["NM_MUNICIPIO_IBGE"]) if unicodedata.category(ch) != "Mn").upper())
chaves = {k.split("|")[1] for k in E["porMun"]}
ok(chaves - {""} <= mun_ro, "chaves de municipio sao todas oficiais de RO (%d de %d)" % (len(chaves - {""}), len(mun_ro)))
# foco (Ariquemes) de cada candidato = soma dos itens da tela Ariquemes
itens = E["porMun"].get("RO|ARIQUEMES", [])
soma = collections.defaultdict(lambda: collections.defaultdict(float))
for x in itens:
    if x.get("sq"):
        if x["nv"] == "fed":
            soma[x["sq"]]["fed_emp"] += x["e"]
        elif x["nv"] == "fav":
            soma[x["sq"]]["fed_rec"] += x["r"]
        else:
            soma[x["sq"]]["est_prev"] += x.get("pv", 0)
div = []
for sq, s in soma.items():
    f = E["porCand"].get(sq, {}).get("foco", {})
    if abs(f.get("fed", {}).get("emp", 0) - s["fed_emp"]) > 1 or abs(f.get("fed", {}).get("rec", 0) - s["fed_rec"]) > 1 or abs(f.get("est", {}).get("prev", 0) - s["est_prev"]) > 1:
        div.append(sq)
ok(not div, "foco Ariquemes na ficha = soma da tela Emendas (%d candidatos)" % len(soma))
# totais federais x CSV bruto para 3 autores
zf = zipfile.ZipFile(os.path.join(RAW, "EmendasParlamentares.zip"))
alvos = {"RAFAEL FERA": "220002536035", "THIAGO FLORES": "220002542944", "LUCIO MOSQUINI": "220002536882"}
tot = collections.defaultdict(float)
for r in csv.DictReader(io.TextIOWrapper(zf.open("EmendasParlamentares.csv"), encoding="latin-1"), delimiter=";"):
    if r["Nome do Autor da Emenda"] in alvos:
        tot[r["Nome do Autor da Emenda"]] += v(r["Valor Empenhado"])
for a, sq in alvos.items():
    g = E["porCand"][sq]["fed"]["emp"]
    extra = 0.0
    if a == "RAFAEL FERA":  # tambem recebe as emendas registradas como "RAFAEL BENTO (EX-PARLAMENTAR LEBRAO...)"
        for r in csv.DictReader(io.TextIOWrapper(zf.open("EmendasParlamentares.csv"), encoding="latin-1"), delimiter=";"):
            if r["Nome do Autor da Emenda"].startswith("RAFAEL BENTO"):
                extra += v(r["Valor Empenhado"])
    ok(abs(g - tot[a] - extra) < 1, "empenhado federal %s = CSV bruto (%.2f)" % (a, g))
cod_ro = collections.Counter(x["cod"] for x in itens if x["nv"] == "fed" and x["cod"].isdigit())
ok(all(n == 1 for n in cod_ro.values()), "sem emenda federal (com codigo) duplicada em Ariquemes")
sem_cod = [x for x in itens if x["nv"] == "fed" and not x["cod"].isdigit()]
ok(len({x["o"] for x in sem_cod}) == len(sem_cod) or not sem_cod, "emendas sem codigo nao herdam objeto de convenio alheio")

print("6. Casamento autor da emenda -> candidato 2026")
CARGOS = {"fed": {"DEPUTADO FEDERAL", "SENADOR", "1º SUPLENTE", "2º SUPLENTE", "1º SUPLENTE SENADOR", "2º SUPLENTE SENADOR"},
          "est": {"DEPUTADO ESTADUAL"}}
sem_crit, sem_prova, so_urna, est_so_urna = [], [], [], []
for sq, d in E["porCand"].items():
    c = cands[sq]
    cargos = {" ".join((h.get("cargo") or "").upper().split()) for h in c.get("hist", [])}
    for nv in ("fed", "est"):
        if nv not in d:
            continue
        crit = d[nv].get("casamento") or []
        if not crit:
            sem_crit.append(c["urna"])
        if any(x.startswith("historico") for x in crit) and not cargos & CARGOS[nv]:
            sem_prova.append(c["urna"])
        if nv == "fed" and not all(x == "alias" or x.endswith("+nascimento") for x in crit):
            so_urna.append("%s/%s <- %s %s" % (c["urna"], c["uf"], ", ".join(d[nv]["autores"]), crit))
        if nv == "est" and crit == ["urna"] and not cargos & CARGOS[nv]:
            est_so_urna.append("%s <- %s" % (c["urna"], ", ".join(d[nv]["autores"])))
ok(not sem_crit, "todo casamento registra o criterio usado (%d)" % len(E["porCand"]))
ok(not sem_prova, "casamento por historico tem o cargo no historico do TSE")
# homonimos/parentes que NAO podem casar (achados na auditoria de 2026-09-22)
proibidos = {"JADER BARBALHO": "JADER FILHO", "RODRIGO PACHECO": "PACHECO", "JARBAS VASCONCELOS": "JARBAS FILHO",
             "FATIMA BEZERRA": "MARLENE BEZERRA", "RICARDO SALLES": "RAMOS", "EDSON SANTOS": "EDSON DOS SANTOS",
             "ALMEIDA LIMA": "DRA. JEANNE LIMA", "SERGIO VIDIGAL": "SERGINHO VIDIGAL", "CARLOS BRANDAO": "ORLEANS BRANDÃO",
             # nome de urna identico, mas outra pessoa (data de nascimento diferente da Camara/Senado)
             "ELEUSES PAIVA": "ELEUSES PAIVA", "EDUARDO LOPES": "EDUARDO LOPES", "CLEITINHO": "CLEITINHO",
             "ROBERTO SANTIAGO": "ROBERTO SANTIAGO", "JOSE AUGUSTO MAIA": "JOSE AUGUSTO", "ALEXANDRE SANTOS": "ALEXANDRE SALGADO"}
errados = [a for sq, d in E["porCand"].items() for nv in ("fed", "est") if nv in d
           for a in d[nv]["autores"] if a in proibidos and cands[sq]["urna"] == proibidos[a]]
ok(not errados, "nenhum dos %d homonimos/parentes conhecidos foi casado %s" % (len(proibidos), errados))
ok(not so_urna, "todo casamento federal confirmado por data de nascimento (Camara/Senado) ou alias %s" % so_urna[:3])
ok(len(est_so_urna) <= 25, "estaduais RO casados pelo nome de urna sem historico (sem API da ALE-RO): %d" % len(est_so_urna))
ok(os.path.exists(os.path.join(RAW, "camara_deputados.csv")) and os.path.exists(os.path.join(RAW, "senado_senadores.json")), "listas oficiais da Camara e do Senado em raw/")
ok(not E.get("ambiguos"), "nenhum autor ambiguo sem resolver %s" % E.get("ambiguos", [])[:3])
# casos resolvidos a mao ou pela regra "mesma pessoa, candidatura ativa" (conferidos na API da Camara)
esperado = {"CARLOS MAGNO": "CARLOS MAGNO RAMOS", "JOAO CARLOS BACELAR": "JOÃO CARLOS PAOLILO BACELAR FILHO",
            "BACELAR": "JOAO CARLOS BACELAR BATISTA", "RENAN CALHEIROS": "JOSE RENAN VASCONCELOS CALHEIROS",
            "CARLOS JORDY": "CARLOS ROBERTO COELHO DE MATTOS JÚNIOR", "RONALDO FONSECA": "RONALDO FONSECA DE SOUZA",
            "PROFESSORA DAYANE PIMENTEL": "DAYANE JAMILLE CARNEIRO DOS SANTOS PIMENTEL",   # datas divergem 1 dia
            "RONALDO NOGUEIRA": "RONALDO NOGUEIRA DE OLIVEIRA", "CORONEL ASSIS": "JONILDO JOSÉ DE ASSIS"}
casado_com = {a: cands[sq]["nome"] for sq, d in E["porCand"].items() for nv in ("fed", "est") if nv in d for a in d[nv]["autores"]}
errados = {a: casado_com.get(a) for a, nome in esperado.items() if casado_com.get(a) != nome}
ok(not errados, "homonimos resolvidos corretamente (%d casos) %s" % (len(esperado), errados))
ok("VITAL DO REGO" not in casado_com, "VITAL DO REGO (nao candidato) nao casa com parentes")
ro = {sq: d for sq, d in E["porCand"].items() if cands[sq]["uf"] == "RO"}
ok(all(d[nv].get("casamento") for d in ro.values() for nv in ("fed", "est") if nv in d), "RO: %d parlamentares casados, todos com criterio" % len(ro))

print("6b. Camara (data/camara.js): cada deputado casado com o candidato certo")
cam_p = os.path.join(DATA, "camara.js")
if os.path.exists(cam_p):
    CAM = ler(cam_p)
    errados = []
    for sq, info in CAM.items():
        c = cands.get(sq)
        try:
            d_c = datetime.datetime.strptime(c["nasc"], "%d/%m/%Y").date()
            d_d = datetime.date.fromisoformat(info["nasc"][:10])
            if abs((d_c - d_d).days) > 1:
                errados.append(c["urna"])
        except (TypeError, KeyError, ValueError):
            errados.append((c or {}).get("urna", sq))
    ok(not errados, "%d deputados: data de nascimento da Camara = do candidato %s" % (len(CAM), errados[:3]))
    ids = collections.Counter(i["id"] for i in CAM.values())
    ok(all(n == 1 for n in ids.values()), "nenhum deputado ligado a dois candidatos")
    irmaos = [sq for sq, i in CAM.items() if cands[sq]["urna"] == "MARIANA CARVALHO" and i["id"] == 220609]
    ok(not irmaos, "Mariana Carvalho nao recebe os dados do irmao Mauricio (id 220609)")
    gemeo = [sq for sq, i in CAM.items() if cands.get(sq, {}).get("urna") == "FABRICIO FURLAN"]
    ok(not gemeo, "gemeos Furlan (AP, mesma data): so Cristiano, o deputado, recebe os dados")
else:
    print("  (sem data/camara.js - rode scripts/fetch_camara.py)")

print("6c. ALE-RO (data/alero.js): votacoes nominais e deputado -> candidato")
al_p = os.path.join(DATA, "alero.js")
if os.path.exists(al_p):
    AL = ler(al_p)
    ok(all(sq in cands and cands[sq]["uf"] == "RO" for sq in AL["porCand"]), "todo candidato ligado a deputado estadual existe em RO (%d)" % len(AL["porCand"]))
    ok(all(AL["parl"][p]["sq"] == sq for sq, p in AL["porCand"].items()), "porCand e parl apontam um para o outro")
    ok(len(set(AL["porCand"].values())) == len(AL["porCand"]), "nenhum deputado ligado a dois candidatos")
    ok(all(v in "SNAUX?" for x in AL["vot"] for v in x["v"].values()), "votos so com codigos conhecidos (Sim/Nao/Abstencao/Ausente/Nao votou/Sem registro)")
    ok(all(p in AL["parl"] for x in AL["vot"] for p in x["v"]), "todo voto aponta para um deputado do arquivo (cadastros duplicados unidos)")
    ok(all(x["d"] and x["t"] and x["n"] for x in AL["vot"]), "toda votacao tem data, tipo e numero (%d)" % len(AL["vot"]))
    ok(AL["vot"] == sorted(AL["vot"], key=lambda x: (x["d"], x["id"]), reverse=True), "votacoes da mais recente para a mais antiga")
    por_nome = {cands[sq]["urna"]: AL["parl"][p]["n"] for sq, p in AL["porCand"].items()}
    # parentes e homonimos que um casamento so por nome de urna ligava errado
    ok(por_nome.get("JEAN MENDONÇA") == "JEAN MENDONÇA", "Jean Mendonca nao recebe os votos de Kaka Mendonca (Joao Ricardo, outra pessoa): %s" % por_nome.get("JEAN MENDONÇA"))
    ok(por_nome.get("DR. RIBAMAR ARAÚJO") in ("RIBAMAR ARAUJO", "RIBAMAR ARAÚJO"), "Dr. Ribamar Araujo nao recebe os votos de Zequinha Araujo (Jose Francisco): %s" % por_nome.get("DR. RIBAMAR ARAÚJO"))
    ok("JAIR MONTES JR." not in por_nome, "Jair Montes Jr. (filho) nao recebe os votos de Jair Montes (pai)")
    redano = [p for sq, p in AL["porCand"].items() if cands[sq]["urna"] == "ALEX REDANO"]
    anos = sorted({x["d"][:4] for x in AL["vot"] if redano and redano[0] in x["v"]})
    ok(redano and anos[0] <= "2019" and anos[-1] >= "2025", "Alex Redano: dois cadastros no SAPL unidos (votos de %s a %s)" % (anos[0] if anos else "-", anos[-1] if anos else "-"))
    # fase 2: leis decididas sem voto individual
    LE = AL.get("leis", [])
    ok(len(LE) > 500, "leis/PECs decididas em plenario desde %s: %d" % (AL.get("leisDesde"), len(LE)))
    ok(all(l["d"] >= AL["leisDesde"] and l["t"] in ("PL", "PLC", "PEC") and l["res"] for l in LE), "todas no periodo, do tipo PL/PLC/PEC e com resultado")
    ok(all(v in {x["id"] for x in AL["vot"]} for l in LE for v in l.get("nominal", [])), "'teve votacao nominal' aponta para votacoes que existem")
    pl1243 = next((l for l in LE if l["t"] == "PL" and l["n"] == 1243 and l["a"] == 2025), None)
    ok(pl1243 and pl1243["d"] == "2026-01-26" and not pl1243.get("nominal") and "6.328" in (pl1243.get("lei") or ""),
       "PL 1243/2025: aprovado em 26/01/2026, sem voto individual, virou a Lei 6.328 %s" % ({k: pl1243.get(k) for k in ("d", "lei", "nominal")} if pl1243 else None))
    ok(pl1243 and any("Executivo" in a["nome"] for a in pl1243["aut"]), "PL 1243/2025: autoria do Poder Executivo")
    decl = (pl1243 or {}).get("decl", [])
    ok(len(decl) == 1 and AL["parl"].get(decl[0]["parlamentar"], {}).get("n") == "DELEGADO LUCAS" and decl[0]["url"].startswith("http"),
       "PL 1243/2025: declaracao oficial do Delegado Lucas (ata n. 252) ligada ao deputado certo")
    ok(all(d["url"] and d["fonte"] for l in LE for d in l.get("decl", [])), "toda declaracao tem fonte oficial e link")
    # levantamento nas atas (fetch_alero_atas.py, 24/09/2026)
    DL = [(l, d) for l in LE for d in l.get("decl", [])]
    ok(len(DL) >= 36, "declaracoes oficiais tiradas das atas: %d" % len(DL))
    ok(all(d["parlamentar"] in AL["parl"] for _, d in DL), "toda declaracao aponta para um deputado com nome no arquivo")
    ok(all(not l.get("nominal") for l, _ in DL), "declaracoes so em leis SEM voto individual no SAPL (senao o voto ja aparece)")
    ok(all("/sessaoplenaria/" in d["url"] and "/ata/" in d["url"] and "folha" in d["fonte"] for _, d in DL),
       "toda declaracao cita a ata (link do PDF no SAPL) e a folha")
    atas_dir = os.path.join(ROOT, "raw", "alero_atas")
    if os.path.isdir(atas_dir):
        # o nome do deputado esta no texto da ata citada (pela ultima palavra do nome parlamentar, sem acento)
        def sem_ac(s):
            return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper()
        falta = []
        for l, d in DL:
            sid = d["url"].split("/sessaoplenaria/")[1].split("/")[0]
            tp = os.path.join(atas_dir, sid + ".txt")
            chave = sem_ac(AL["parl"][d["parlamentar"]]["n"]).split()[-1]
            if os.path.exists(tp) and chave not in sem_ac(open(tp, encoding="utf-8").read()):
                falta.append("%s %s/%s: %s" % (l["t"], l["n"], l["a"], chave))
        ok(not falta, "o deputado de cada declaracao aparece no texto da ata citada %s" % falta[:5])
    achar = lambda t, n, a, nome: next((d for l in LE if (l["t"], l["n"], l["a"]) == (t, n, a) for d in l.get("decl", [])
                                        if AL["parl"][d["parlamentar"]]["n"] == nome), None)
    ok(achar("PL", 741, 2024, "EYDER BRASIL") and "contrário" in achar("PL", 741, 2024, "EYDER BRASIL")["texto"]
       and achar("PL", 741, 2024, "DELEGADO CAMARGO") and "abstenção" in achar("PL", 741, 2024, "DELEGADO CAMARGO")["texto"],
       "PL 741/2024 (ata 185): Eyder Brasil votou contra e Delegado Camargo se absteve - cada um com a sua posicao")
    ok(achar("PL", 804, 2025, "DELEGADO CAMARGO") and not achar("PL", 619, 2024, "DELEGADO CAMARGO"),
       "ata 196: voto contrario no PL 804/2025 (credito CBM), nao no PL 619/2024 (OCR embaralhou a folha)")
    ok(achar("PL", 237, 2023, "LUIZINHO GOEBEL") and "NÃO" in achar("PL", 237, 2023, "LUIZINHO GOEBEL")["texto"],
       "PL 237/2023: declaracao de voto contrario do Luizinho Goebel lida na sessao de 25/10/2023 (ata 083)")
    ok(achar("PL", 270, 2023, "Dra. TAÍSSA") and "parecer" in achar("PL", 270, 2023, "Dra. TAÍSSA")["texto"],
       "PL 270/2023: Dra. Taissa votou contra o PARECER (nao ha registro dela contra o projeto)")
else:
    print("  (sem data/alero.js - rode scripts/fetch_alero.py)")

print("6d. Camara e Senado (data/votacoes_federais.js): votos dos candidatos de RO")
vf_p = os.path.join(DATA, "votacoes_federais.js")
if os.path.exists(vf_p):
    VF = ler(vf_p)
    CAM_ids = {str(i["id"]): sq for sq, i in (CAM.items() if os.path.exists(cam_p) else [])}
    for casa in ("camara", "senado"):
        C = VF[casa]
        ok(all(sq in cands and cands[sq]["uf"] == "RO" for sq in C["porCand"]), "%s: todo candidato ligado existe em RO (%d)" % (casa, len(C["porCand"])))
        ok(all(p in C["parl"] for x in C["vot"] for p in x["v"]) and all(x["v"] for x in C["vot"]), "%s: todo voto aponta para um parlamentar do arquivo" % casa)
        ok(all(x["d"] and x["id"] for x in C["vot"]), "%s: toda votacao tem data e id (%d)" % (casa, len(C["vot"])))
        ok(all(a["d"] >= b["d"] for a, b in zip(C["vot"], C["vot"][1:])), "%s: da mais recente para a mais antiga" % casa)
        ok(all(isinstance(v, str) and v for x in C["vot"] for v in x["v"].values()), "%s: votos com rotulo oficial por extenso, nenhum vazio" % casa)
    ok(all(CAM_ids.get(d) == p["sq"] for d, p in VF["camara"]["parl"].items()), "camara: deputado -> candidato igual ao de data/camara.js (casado por nascimento)")
    sen_nomes = {cands[p["sq"]]["urna"] for p in VF["senado"]["parl"].values()}
    ok("MARCOS ROGÉRIO" in sen_nomes and "PASTOR MOURA" not in sen_nomes, "senado: Marcos Rogerio ligado; Pastor Moura NAO ligado a Wilson Santiago (PB, mesma data)")
    ok(not [v for x in VF["senado"]["vot"] for v in x["v"].values() if v in ("P-NRV", "AP", "MIS", "NCom")], "senado: siglas de ausencia/licenca traduzidas por extenso")
else:
    print("  (sem data/votacoes_federais.js - rode scripts/fetch_votacoes_federais.py)")

print("7. Registro de downloads")
reg = json.load(open(os.path.join(RAW, "_downloads.json"), encoding="utf-8"))
ruins = [n for n, x in reg.items() if x.get("tamanho") and os.path.exists(os.path.join(RAW, n)) and os.path.getsize(os.path.join(RAW, n)) != x["tamanho"]]
ok(not ruins, "tamanho em disco = registro (%d arquivos)" % len(reg))
ok(not [f for f in os.listdir(RAW) if f.endswith(".part")], "nenhum download .part pendente")
ok(not [f for f in os.listdir(ROOT) if f in ("body.txt", "part.zip", "p2.zip")], "sem arquivos temporarios na raiz")

print("8. Atualidade dos dados (avisos: rode scripts/atualizar_tudo.py se estiverem velhos)")
hoje = datetime.date.today()


def dias(txt, fmt):
    try:
        return (hoje - datetime.datetime.strptime(txt, fmt).date()).days
    except (TypeError, ValueError):
        return 999


d_build = dias(man.get("geradoEm", "")[:10], "%Y-%m-%d")
d_em = dias(E.get("atualizado"), "%Y-%m-%d")
datas = [c["contas"]["data"] for c in cands.values() if c.get("contas") and c["contas"].get("data")]
d_contas = min(dias(x, "%d/%m/%Y") for x in datas) if datas else 999
aviso(d_build <= 3, "base de candidatos gerada ha %d dia(s)" % d_build)
aviso(d_em <= 7, "emendas atualizadas ha %d dia(s)" % d_em)
aviso(d_contas <= 10, "prestacao de contas mais recente entregue ha %d dia(s) (parcial ate a eleicao)" % d_contas)
eleicao = datetime.date(2026, 10, 4)
if hoje <= eleicao:
    print("         faltam %d dia(s) para o 1o turno: atualize de novo na semana da eleicao" % (eleicao - hoje).days)

print("\nRESULTADO: %d ok, %d falhas, %d avisos" % (len(oks), len(falhas), len(avisos)))
for f in falhas:
    print("  FALHA:", f)
sys.exit(1 if falhas else 0)
