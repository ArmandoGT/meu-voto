# -*- coding: utf-8 -*-
"""
build_data.py - converte os arquivos oficiais do TSE (Dados Abertos, eleicoes 2026)
em arquivos JS carregaveis por file:// (data/cand_XX.js + data/manifest.js) e extrai
fotos / propostas / certidoes para data/.

Uso:
    python scripts/build_data.py                 # le tudo de raw/
    python scripts/build_data.py --raw "D:/x"    # outra pasta
    python scripts/build_data.py --sem-arquivos  # nao extrai fotos/PDFs (mais rapido)
    python scripts/build_data.py --votacao-ufs RO  # cruza votacao so de RO (o ZIP nacional de 2022 tem 16 GB)

Arquivos reconhecidos em raw/ (ZIP ou CSV soltos; nao precisa extrair):
    consulta_cand_2026.zip               (obrigatorio) candidatos
    consulta_cand_complementar_2026.zip  situacao do julgamento, municipio de nascimento, idade, urna...
    historico_candidatura_2026.zip       eleicoes anteriores de cada candidato (cargo, municipio, resultado)
    bem_candidato_2026.zip               bens declarados
    rede_social_candidato_2026.zip       links de redes sociais
    motivo_cassacao_2026.zip             motivos de indeferimento/cassacao
    consulta_vagas_2026.zip              numero de vagas por cargo/UF
    foto_cand2026_XX_div.zip             fotos oficiais  -> data/fotos/<sq>.jpg
    proposta_governo_2026_XX.zip         planos de governo (PDF) -> data/propostas/<sq>_NN.pdf
    certidao_criminal_2026_XX.zip        certidoes criminais (PDF) -> data/certidoes/<sq>/...
    votacao_candidato_munzona_AAAA_XX.zip  votos por municipio em eleicoes anteriores (ex.: 2022_RO)
                                         -> campo "votosAnt" (cruzado pelo historico de candidaturas)
    denuncia_AAAA.zip                    denuncias do app Pardal (anonimas) -> data/denuncias.js (painel por UF/ano)
    prestacao_de_contas_eleitorais_candidatos_2026.zip  receitas e despesas de campanha -> campo "contas"

Campos de cada candidato gerado (usados pelas paginas):
    sq uf sgUe ue cargo cdCargo cdEleicao nr nome urna social partido nrPartido nomePartido
    federacao compFederacao coligacao compColigacao tipoAgremiacao sit sitApto urnaOk destVotos
    ufNasc munNasc nasc idade genero instrucao estadoCivil corRaca ocupacao nacionalidade
    quilombola etnia despesaMax substituido email reeleicao chapa[]
    hist[] {ano eleicao cargo ue uf partido nr urna resultado abrang} munHist[] vezesCand vezesEleito
    bens bensLista[] redes[] motivos[] foto propostas[] certidoes[]
    votosAnt[] {ano cargo ue abrang total municipios top[{mun uf votos pct}]}
    contas {tipo data rec recEst fontes{fefc fp outros} origens[[o,v]] doadores[[nome,tipo,v,obs]] nDoadores nPF
            desp pago cats[[categoria,v]] fornec[[nome,v]] nFornec}   chapa[] {cargo nome nomeCompleto partido sit foto certidoes[]}

Somente stdlib.
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR_DEFAULT = os.path.join(ROOT, "raw")
OUT_DIR = os.path.join(ROOT, "data")

ENCODING = "latin-1"
NULOS = {"", "#NULO#", "#NULO", "#NE#", "#NE", "-1", "-3", "-4", "N\u00c3O DIVULG\u00c1VEL", "NAO DIVULGAVEL"}


# ---------------------------------------------------------------- utilidades
def norm_cargo(s):
    s = (s or "").strip().upper()
    s = s.replace("1\u00b0 ", "1\u00ba ").replace("2\u00b0 ", "2\u00ba ").replace("1. ", "1\u00ba ").replace("2. ", "2\u00ba ")
    return s


def cargo_pai(cargo):
    """Cargo do titular para linhas de vice/suplente; None se a linha e um titular."""
    c = norm_cargo(cargo)
    if c.startswith("VICE-"):
        return c[5:]
    if "SUPLENTE" in c:
        return "SENADOR"
    return None


def get(row, *keys, default=""):
    for k in keys:
        v = row.get(k)
        if v is not None:
            v = v.strip()
            if v not in NULOS:
                return v
    return default


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def parse_money(v):
    """'1.234,56' e '1234,56' (padrao BR) ou '1234.56' (ex.: VR_DESPESA_MAX_CAMPANHA) -> float"""
    v = (v or "").strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    elif v.count(".") > 1:
        v = v.replace(".", "")
    try:
        return float(v)
    except ValueError:
        return 0.0


def titulo(s):
    return " ".join(w.capitalize() for w in (s or "").split())


def open_csv_sources(raw_dir, prefix):
    """Gera (nome, file-like texto) para cada CSV com o prefixo, dentro de ZIPs ou soltos.
    Se o ZIP tiver o arquivo _BRASIL (consolidado), usa so ele para nao duplicar."""
    if not os.path.isdir(raw_dir):
        return
    for fname in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, fname)
        low = fname.lower()
        if low.endswith(".zip") and low.startswith(prefix):
            with zipfile.ZipFile(path) as z:
                membros = [m for m in sorted(z.namelist())
                           if os.path.basename(m).lower().startswith(prefix) and m.lower().endswith(".csv")]
                brasil = [m for m in membros if os.path.basename(m).lower().endswith("_brasil.csv")]
                for member in (brasil or membros):
                    with z.open(member) as fh:
                        yield member, io.TextIOWrapper(fh, encoding=ENCODING, newline="")
        elif low.endswith(".csv") and low.startswith(prefix):
            with open(path, encoding=ENCODING, newline="") as fh:
                yield fname, fh


def iter_rows(raw_dir, prefix):
    for name, fh in open_csv_sources(raw_dir, prefix):
        for row in csv.DictReader(fh, delimiter=";"):
            yield name, row


# ---------------------------------------------------------------- prestacao de contas (campanha 2026)
def _membros_contas(raw_dir, prefixo):
    """CSV do ZIP de prestacao de contas cujo nome comeca com o prefixo (usa o _BRASIL se existir)."""
    if not os.path.isdir(raw_dir):
        return
    for fname in sorted(os.listdir(raw_dir)):
        low = fname.lower()
        if not (low.startswith("prestacao_de_contas_eleitorais_candidatos_2026") and low.endswith(".zip")):
            continue
        with zipfile.ZipFile(os.path.join(raw_dir, fname)) as z:
            membros = [m for m in sorted(z.namelist()) if os.path.basename(m).lower().startswith(prefixo) and m.lower().endswith(".csv")]
            brasil = [m for m in membros if m.lower().endswith("_brasil.csv")]
            for m in (brasil or membros):
                with z.open(m) as fh:
                    for row in csv.DictReader(io.TextIOWrapper(fh, encoding=ENCODING, newline=""), delimiter=";"):
                        yield row


def _data_br(s):
    try:
        return datetime.strptime(s, "%d/%m/%Y")
    except (TypeError, ValueError):
        return datetime.min


TIPO_DOADOR = {"recursos de partido politico": "Partido", "recursos de pessoas fisicas": "Pessoa física",
               "recursos proprios": "Próprio candidato", "recursos de outros candidatos": "Outro candidato",
               "recursos de financiamento coletivo": "Vaquinha", "doacoes pela internet": "Internet"}


def _sem_acento(s):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")


def aplicar_contas(raw_dir, titulares):
    """Receitas (quem financia) e despesas (com o que gasta) de campanha, por candidato."""
    ag = {}
    prestador = {}   # SQ_PRESTADOR_CONTAS -> sq (despesas pagas nao trazem SQ_CANDIDATO)

    def novo(sq):
        return ag.setdefault(sq, {"tipo": "", "data": datetime.min, "rec": 0.0, "recEst": 0.0,
                                  "fontes": defaultdict(float), "origens": defaultdict(float), "doadores": {},
                                  "desp": 0.0, "pago": 0.0, "cats": defaultdict(float), "fornec": defaultdict(float)})

    def marca_prestacao(a, row):
        d = _data_br(get(row, "DT_PRESTACAO_CONTAS"))
        if d >= a["data"]:
            a["data"], a["tipo"] = d, titulo(get(row, "TP_PRESTACAO_CONTAS"))

    n_rec = 0
    for row in _membros_contas(raw_dir, "receitas_candidatos_2026"):
        sq = get(row, "SQ_CANDIDATO")
        if sq not in titulares:
            continue
        a = novo(sq)
        prestador[get(row, "SQ_PRESTADOR_CONTAS")] = sq
        marca_prestacao(a, row)
        v = parse_money(get(row, "VR_RECEITA"))
        n_rec += 1
        a["rec"] += v
        if "ESTIM" in _sem_acento(get(row, "DS_NATUREZA_RECEITA")).upper():
            a["recEst"] += v
        fonte = _sem_acento(get(row, "DS_FONTE_RECEITA")).upper()
        a["fontes"]["fefc" if "ESPECIAL" in fonte else "fp" if "PARTIDARIO" in fonte else "outros"] += v
        origem = get(row, "DS_ORIGEM_RECEITA") or "Sem informação"
        a["origens"][origem] += v
        tipo = TIPO_DOADOR.get(_sem_acento(origem).lower(), titulo(origem))
        nome = get(row, "NM_DOADOR") if tipo == "Partido" else (get(row, "NM_DOADOR_RFB") or get(row, "NM_DOADOR"))
        chave = get(row, "NR_CPF_CNPJ_DOADOR") + "|" + nome
        obs = ""
        if tipo == "Outro candidato":
            obs = " ".join(x for x in (titulo(get(row, "DS_CARGO_CANDIDATO_DOADOR")), get(row, "NR_CANDIDATO_DOADOR"), get(row, "SG_PARTIDO_DOADOR")) if x)
        elif tipo == "Partido":
            obs = get(row, "SG_PARTIDO_DOADOR")
        elif tipo not in ("Pessoa física", "Próprio candidato"):
            obs = get(row, "DS_CNAE_DOADOR")
        d = a["doadores"].setdefault(chave, [titulo(nome) if tipo != "Partido" else nome, tipo, 0.0, obs])
        d[2] += v

    n_desp = 0
    for row in _membros_contas(raw_dir, "despesas_contratadas_candidatos_2026"):
        sq = get(row, "SQ_CANDIDATO")
        if sq not in titulares:
            continue
        a = novo(sq)
        prestador[get(row, "SQ_PRESTADOR_CONTAS")] = sq
        marca_prestacao(a, row)
        v = parse_money(get(row, "VR_DESPESA_CONTRATADA"))
        n_desp += 1
        a["desp"] += v
        a["cats"][get(row, "DS_ORIGEM_DESPESA") or "Sem informação"] += v
        a["fornec"][titulo(get(row, "NM_FORNECEDOR_RFB") or get(row, "NM_FORNECEDOR") or "Sem informação")] += v

    for row in _membros_contas(raw_dir, "despesas_pagas_candidatos_2026"):
        sq = prestador.get(get(row, "SQ_PRESTADOR_CONTAS"))
        if sq:
            ag[sq]["pago"] += parse_money(get(row, "VR_PAGTO_DESPESA"))

    r2 = lambda x: round(x, 2)  # noqa: E731
    for sq, a in ag.items():
        doadores = sorted(a["doadores"].values(), key=lambda d: -d[2])
        titulares[sq]["contas"] = {
            "tipo": a["tipo"], "data": a["data"].strftime("%d/%m/%Y") if a["data"] != datetime.min else "",
            "rec": r2(a["rec"]), "recEst": r2(a["recEst"]),
            "fontes": {k: r2(v) for k, v in a["fontes"].items() if v},
            "origens": [[k, r2(v)] for k, v in sorted(a["origens"].items(), key=lambda kv: -kv[1]) if v],
            "doadores": [[d[0], d[1], r2(d[2]), d[3]] for d in doadores[:10] if d[2] > 0],
            "nDoadores": sum(1 for d in doadores if d[2] > 0),
            "nPF": sum(1 for d in doadores if d[2] > 0 and d[1] == "Pessoa física"),
            "desp": r2(a["desp"]), "pago": r2(a["pago"]),
            "cats": [[k, r2(v)] for k, v in sorted(a["cats"].items(), key=lambda kv: -kv[1])[:8] if v],
            "fornec": [[k, r2(v)] for k, v in sorted(a["fornec"].items(), key=lambda kv: -kv[1])[:6] if v],
            "nFornec": sum(1 for v in a["fornec"].values() if v),
        }
    return len(ag), n_rec, n_desp


# ---------------------------------------------------------------- candidatos
def build_candidatos(raw_dir):
    titulares = {}                 # sq -> dict
    chapas = defaultdict(list)     # (SG_UE, cargo_pai, nr) -> [membros]
    total_linhas = 0
    fontes = set()

    for name, row in iter_rows(raw_dir, "consulta_cand_2026"):
        fontes.add(name)
        total_linhas += 1
        cargo = norm_cargo(get(row, "DS_CARGO"))
        ue = get(row, "SG_UE")
        nr = get(row, "NR_CANDIDATO")
        sq = get(row, "SQ_CANDIDATO")
        pai = cargo_pai(cargo)
        if pai:
            if any(m["sq"] == sq for m in chapas[(ue, pai, nr)]):
                continue
            chapas[(ue, pai, nr)].append({
                "sq": sq,
                "cargo": titulo(cargo),
                "nome": get(row, "NM_URNA_CANDIDATO") or get(row, "NM_CANDIDATO"),
                "nomeCompleto": get(row, "NM_CANDIDATO"),
                "partido": get(row, "SG_PARTIDO"),
                "sit": get(row, "DS_DETALHE_SITUACAO_CAND") or get(row, "DS_SITUACAO_CANDIDATURA"),
            })
            continue
        if not sq:
            continue
        titulares[sq] = {
            "sq": sq,
            "uf": get(row, "SG_UF"),            # presidente vem como "BR"
            "sgUe": ue,
            "ue": get(row, "NM_UE"),
            "cargo": titulo(cargo),
            "cdCargo": to_int(get(row, "CD_CARGO")),
            "cdEleicao": get(row, "CD_ELEICAO"),
            "nr": nr,
            "nome": get(row, "NM_CANDIDATO"),
            "urna": get(row, "NM_URNA_CANDIDATO"),
            "social": get(row, "NM_SOCIAL_CANDIDATO"),
            "partido": get(row, "SG_PARTIDO"),
            "nrPartido": get(row, "NR_PARTIDO"),
            "nomePartido": get(row, "NM_PARTIDO"),
            "federacao": get(row, "SG_FEDERACAO"),
            "compFederacao": get(row, "DS_COMPOSICAO_FEDERACAO"),
            "coligacao": get(row, "NM_COLIGACAO"),
            "compColigacao": get(row, "DS_COMPOSICAO_COLIGACAO"),
            "tipoAgremiacao": get(row, "TP_AGREMIACAO"),
            # situacao: no layout 2026 o arquivo principal traz so #NE; o julgamento vem do complementar
            "sit": get(row, "DS_DETALHE_SITUACAO_CAND") or get(row, "DS_SITUACAO_CANDIDATURA"),
            "sitApto": "",
            "urnaOk": None,
            "destVotos": "",
            "ufNasc": get(row, "SG_UF_NASCIMENTO"),
            "munNasc": get(row, "NM_MUNICIPIO_NASCIMENTO"),
            "nasc": get(row, "DT_NASCIMENTO"),
            "idade": to_int(get(row, "NR_IDADE_DATA_POSSE")),
            "genero": get(row, "DS_GENERO"),
            "instrucao": get(row, "DS_GRAU_INSTRUCAO"),
            "estadoCivil": get(row, "DS_ESTADO_CIVIL"),
            "corRaca": get(row, "DS_COR_RACA"),
            "ocupacao": get(row, "DS_OCUPACAO"),
            "email": get(row, "DS_EMAIL", "NM_EMAIL"),
            "reeleicao": get(row, "ST_REELEICAO").upper() == "S",
            "chapa": [],
            "hist": [],
            "munHist": [],
            "vezesCand": 0,
            "vezesEleito": 0,
        }

    # idade a partir da data de nascimento quando o TSE nao informa
    for c in titulares.values():
        if c["idade"] is None and c["nasc"]:
            try:
                d, m, a = [int(x) for x in c["nasc"].split("/")]
                c["idade"] = 2027 - a - (1 if (m, d) > (1, 1) else 0)
            except ValueError:
                pass

    return titulares, chapas, total_linhas, sorted(fontes)


def aplicar_complementar(raw_dir, titulares, chapas_por_sq):
    n = 0
    for _name, row in iter_rows(raw_dir, "consulta_cand_complementar_2026"):
        sq = get(row, "SQ_CANDIDATO")
        julg = (get(row, "DS_SITUACAO_JULGAMENTO") or get(row, "DS_DETALHE_SITUACAO_CAND")
                or get(row, "DS_SITUACAO_CANDIDATO_TOT"))
        c = titulares.get(sq)
        if c is None:
            m = chapas_por_sq.get(sq)
            if m is not None and julg:
                m["sit"] = julg
            continue
        n += 1
        c["sit"] = julg or c["sit"]
        c["sitApto"] = get(row, "DS_SITUACAO_CANDIDATO_TOT")
        c["urnaOk"] = get(row, "ST_CANDIDATO_INSERIDO_URNA").upper() == "SIM"
        c["destVotos"] = get(row, "NM_TIPO_DESTINACAO_VOTOS")
        c["munNasc"] = c["munNasc"] or get(row, "NM_MUNICIPIO_NASCIMENTO")
        c["idade"] = to_int(get(row, "NR_IDADE_DATA_POSSE"), c["idade"])
        c["nacionalidade"] = get(row, "DS_NACIONALIDADE")
        c["quilombola"] = get(row, "ST_QUILOMBOLA").upper() == "S"
        etnia = get(row, "DS_ETNIA_INDIGENA")
        c["etnia"] = "" if etnia.upper().startswith(("N\u00c3O INFORMADA", "NAO INFORMADA")) else etnia
        c["despesaMax"] = parse_money(get(row, "VR_DESPESA_MAX_CAMPANHA")) or None
        c["substituido"] = get(row, "ST_SUBSTITUIDO").upper() == "S"
        if get(row, "ST_REELEICAO").upper() == "S":
            c["reeleicao"] = True
    return n


def aplicar_historico(raw_dir, titulares):
    n = 0
    for _name, row in iter_rows(raw_dir, "historico_candidatura_2026"):
        c = titulares.get(get(row, "SQ_CANDIDATO_ATUAL"))
        if c is None:
            continue
        ano = to_int(get(row, "ANO_ELEICAO"))
        if ano == 2026:
            continue
        h = {
            "ano": ano,
            "eleicao": get(row, "DS_ELEICAO"),
            "cargo": titulo(norm_cargo(get(row, "DS_CARGO"))),
            "ue": get(row, "NM_UE"),
            "uf": get(row, "SG_UF"),
            "partido": get(row, "SG_PARTIDO"),
            "nr": get(row, "NR_CANDIDATO"),
            "urna": get(row, "NM_URNA_CANDIDATO"),
            "resultado": get(row, "DS_SIT_TOT_TURNO"),
            "abrang": get(row, "TP_ABRANGENCIA_ELEICAO"),
            "sqAnt": get(row, "SQ_CANDIDATO"),
        }
        if any(x["ano"] == h["ano"] and x["cargo"] == h["cargo"] and x["ue"] == h["ue"] and x["eleicao"] == h["eleicao"]
               for x in c["hist"]):
            continue
        c["hist"].append(h)
        n += 1

    for c in titulares.values():
        if not c["hist"]:
            continue
        c["hist"].sort(key=lambda h: (-(h["ano"] or 0), h["cargo"]))
        eleitos = [h for h in c["hist"] if h["resultado"].upper().startswith("ELEITO")]
        c["vezesCand"] = len(c["hist"])
        c["vezesEleito"] = len(eleitos)
        c["munHist"] = sorted({h["ue"] for h in c["hist"] if h["abrang"] == "M" and h["ue"]})
        # reeleicao: eleito na ultima eleicao para o mesmo cargo (2022; senador tambem 2018)
        cargo_atual = c["cargo"].upper()
        anos_ref = (2022, 2018) if cargo_atual == "SENADOR" else (2022,)
        if any(h["ano"] in anos_ref and h["cargo"].upper() == cargo_atual for h in eleitos):
            c["reeleicao"] = True
    return n


def aplicar_bens(raw_dir, titulares):
    n = 0
    for _name, row in iter_rows(raw_dir, "bem_candidato_2026"):
        c = titulares.get(get(row, "SQ_CANDIDATO"))
        if c is None:
            continue
        valor = parse_money(get(row, "VR_BEM_CANDIDATO"))
        c["bens"] = round(c.get("bens", 0.0) + valor, 2)
        c.setdefault("bensLista", []).append({
            "tipo": get(row, "DS_TIPO_BEM_CANDIDATO"),
            "desc": get(row, "DS_BEM_CANDIDATO"),
            "valor": valor,
        })
        n += 1
    for c in titulares.values():
        if "bensLista" in c:
            c["bensLista"].sort(key=lambda b: -b["valor"])
    return n


def aplicar_redes(raw_dir, titulares):
    n = 0
    for _name, row in iter_rows(raw_dir, "rede_social_candidato_2026"):
        c = titulares.get(get(row, "SQ_CANDIDATO"))
        if c is None:
            continue
        url = get(row, "DS_URL")
        if url and url.lower() not in [u.lower() for u in c.get("redes", [])]:
            c.setdefault("redes", []).append(url)
            n += 1
    return n


def aplicar_motivos(raw_dir, titulares):
    n = 0
    for _name, row in iter_rows(raw_dir, "motivo_cassacao_2026"):
        c = titulares.get(get(row, "SQ_CANDIDATO"))
        if c is None:
            continue
        m = get(row, "DS_MOTIVO")
        if m and m not in c.get("motivos", []):
            c.setdefault("motivos", []).append(m)
            n += 1
    return n


def _fontes_votacao(raw_dir, ufs):
    """CSVs de votacao_candidato_munzona_* em raw/ (ZIP ou soltos), um por UF.
    Ao contrario dos outros arquivos, aqui o consolidado _BRASIL e ignorado (tem varios GB):
    le-se os arquivos por UF, e so das UFs pedidas (None = todas)."""
    if not os.path.isdir(raw_dir):
        return
    prefix = "votacao_candidato_munzona_"

    def uf_de(nome):
        m = re.search(r"_(\d{4})_([A-Z]{2})\.csv$", os.path.basename(nome), re.I)
        return (m.group(2).upper() if m else None)

    for fname in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, fname)
        low = fname.lower()
        if low.endswith(".zip") and low.startswith(prefix):
            with zipfile.ZipFile(path) as z:
                for member in sorted(z.namelist()):
                    uf = uf_de(member)
                    if not member.lower().endswith(".csv") or uf is None or uf == "BRASIL":
                        continue
                    if ufs and uf not in ufs:
                        continue
                    with z.open(member) as fh:
                        yield member, io.TextIOWrapper(fh, encoding=ENCODING, newline="")
        elif low.endswith(".csv") and low.startswith(prefix):
            uf = uf_de(fname)
            if uf and (not ufs or uf in ufs):
                with open(path, encoding=ENCODING, newline="") as fh:
                    yield fname, fh


def aplicar_votacao(raw_dir, titulares, ufs=None):
    """Cruza votacao_candidato_munzona_AAAA (votos por municipio/zona) com o historico:
    o SQ_CANDIDATO da eleicao antiga aparece em hist[].sqAnt.
    Os arquivos sao enormes (2022: ~16 GB descompactados no Brasil), entao cada linha e
    pre-filtrada por string antes de passar pelo parser CSV."""
    por_sq_ant = {}
    for c in titulares.values():
        for h in c["hist"]:
            if h.get("sqAnt"):
                por_sq_ant[(h["ano"], h["sqAnt"])] = (c, h)
    if not por_sq_ant:
        return 0, []
    sqs = {sq for (_ano, sq) in por_sq_ant}
    acum = defaultdict(lambda: defaultdict(int))   # (ano, sqAnt) -> {(mun, uf): votos}
    n = 0
    fontes = []
    for name, fh in _fontes_votacao(raw_dir, ufs):
        fontes.append(os.path.basename(name))
        header = next(csv.reader([fh.readline()], delimiter=";"))
        idx = {k: i for i, k in enumerate(header)}
        i_sq = idx.get("SQ_CANDIDATO")
        i_ano, i_turno = idx.get("ANO_ELEICAO"), idx.get("NR_TURNO")
        i_mun, i_uf = idx.get("NM_MUNICIPIO"), idx.get("SG_UF")
        i_votos = idx.get("QT_VOTOS_NOMINAIS", idx.get("QT_VOTOS_NOMINAIS_VALIDOS"))
        if i_sq is None or i_votos is None:
            continue
        for line in fh:
            # pre-filtro barato: o campo SQ_CANDIDATO e um numero de 12 digitos
            partes = line.split(";", i_sq + 1)
            if len(partes) <= i_sq:
                continue
            bruto = partes[i_sq].strip().strip('"')
            if bruto.isdigit():
                if bruto not in sqs:
                    continue
                row = next(csv.reader([line], delimiter=";"))
            else:                       # ';' dentro de algum nome: parse completo
                row = next(csv.reader([line], delimiter=";"))
                if len(row) <= i_sq or row[i_sq].strip() not in sqs:
                    continue
            if i_turno is not None and row[i_turno].strip() not in ("", "1"):
                continue
            chave = (to_int(row[i_ano].strip()) if i_ano is not None else None, row[i_sq].strip())
            if chave not in por_sq_ant:
                continue
            votos = to_int(row[i_votos].strip(), 0)
            acum[chave][(row[i_mun].strip() if i_mun is not None else "", row[i_uf].strip() if i_uf is not None else "")] += votos
            n += 1
    for chave, muns in acum.items():
        c, h = por_sq_ant[chave]
        total = sum(muns.values())
        if not total:
            continue
        top = sorted(muns.items(), key=lambda kv: -kv[1])
        c.setdefault("votosAnt", []).append({
            "ano": chave[0],
            "cargo": h["cargo"],
            "ue": h["ue"],
            "abrang": h["abrang"],      # M = municipal (votos so naquele municipio), E/F = estadual/federal
            "total": total,
            "municipios": len(muns),
            "top": [{"mun": m, "uf": uf, "votos": v, "pct": round(100.0 * v / total, 1)} for (m, uf), v in top[:12]],
        })
    for c in titulares.values():
        if "votosAnt" in c:
            c["votosAnt"].sort(key=lambda v: -v["ano"])
    return n, fontes


def ler_denuncias(raw_dir):
    """Denuncias do app Pardal (denuncia_AAAA.zip). Sao anonimas (sem candidato): agrega por UF/ano ->
    total, por cargo, por tipo, por municipio, e lista os processos PJe (com municipio) quando existem."""
    agg = {}
    for _name, row in iter_rows(raw_dir, "denuncia_"):
        uf = get(row, "SG_UF")
        ano = get(row, "AA_ELEICAO") or get(row, "ANO_ELEICAO")
        if not uf or not ano:
            continue
        d = agg.setdefault(uf, {}).setdefault(ano, {"total": 0, "porCargo": {}, "porTipo": {}, "porMunicipio": {}, "porStatus": {}, "processos": []})
        d["total"] += 1
        for chave, col in (("porCargo", "DS_CARGO"), ("porTipo", "TP_IRREGULARIDADE"), ("porMunicipio", "NM_MUNICIPIO"), ("porStatus", "ST_PETICIONAMENTO")):
            v = get(row, col) or "(nao informado)"
            d[chave][v] = d[chave].get(v, 0) + 1
        nr = get(row, "NR_PROCESSO_PJE")
        if nr and len(d["processos"]) < 400:
            d["processos"].append({"municipio": get(row, "NM_MUNICIPIO"), "cargo": get(row, "DS_CARGO"),
                                   "tipo": get(row, "TP_IRREGULARIDADE"), "nr": nr, "status": get(row, "ST_PETICIONAMENTO")})
    return agg


def ler_vagas(raw_dir):
    vagas = defaultdict(dict)
    for _name, row in iter_rows(raw_dir, "consulta_vagas_2026"):
        uf = get(row, "SG_UF")
        cargo = titulo(norm_cargo(get(row, "DS_CARGO")))
        vagas[uf][cargo] = to_int(get(row, "QT_VAGA"), 0)
    return vagas


# ---------------------------------------------------------------- arquivos (fotos / pdfs)
def limpar_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def extrair_arquivos(raw_dir, titulares, chapas_por_sq=None):
    """Extrai fotos, propostas de governo e certidoes para data/ e anota os caminhos
    (fotos e certidoes tambem para vices/suplentes, dentro da chapa do titular)."""
    alvos = dict(titulares)
    alvos.update(chapas_por_sq or {})
    fotos_dir = os.path.join(OUT_DIR, "fotos")
    prop_dir = os.path.join(OUT_DIR, "propostas")
    cert_dir = os.path.join(OUT_DIR, "certidoes")
    limpar_dir(fotos_dir)
    limpar_dir(prop_dir)
    limpar_dir(cert_dir)
    n_foto = n_prop = n_cert = 0
    re_sq = re.compile(r"(\d{12})")

    for fname in sorted(os.listdir(raw_dir)):
        low = fname.lower()
        if not low.endswith(".zip"):
            continue
        path = os.path.join(raw_dir, fname)
        if low.startswith("foto_cand"):
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    base = os.path.basename(member)
                    if not base.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    m = re_sq.search(base)
                    if not m or m.group(1) not in alvos:
                        continue
                    ext = os.path.splitext(base)[1].lower()
                    with z.open(member) as src, open(os.path.join(fotos_dir, m.group(1) + ext), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    alvos[m.group(1)]["foto"] = "data/fotos/" + m.group(1) + ext
                    n_foto += 1
        elif low.startswith("proposta_governo"):
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    base = os.path.basename(member)
                    if not base.lower().endswith(".pdf") or base.lower() == "leiame.pdf":
                        continue
                    m = re_sq.search(base)
                    if not m or m.group(1) not in titulares:
                        continue
                    seq = base[m.end():].strip("_").rsplit(".", 1)[0] or "01"
                    nome = "%s_%s.pdf" % (m.group(1), re.sub(r"[^\w-]+", "_", seq))
                    with z.open(member) as src, open(os.path.join(prop_dir, nome), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    titulares[m.group(1)].setdefault("propostas", []).append("data/propostas/" + nome)
                    n_prop += 1
        elif low.startswith("certidao_criminal"):
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    base = os.path.basename(member)
                    if not base.lower().endswith(".pdf") or base.lower() == "leiame.pdf":
                        continue
                    m = re_sq.search(base)
                    if not m or m.group(1) not in alvos:
                        continue
                    sq = m.group(1)
                    resto = base[m.end():].lstrip("_")
                    resto = re.sub(r"\.pdf\.pdf$", ".pdf", resto, flags=re.I)
                    resto = re.sub(r"[^\w.\-]+", "_", resto).strip("_") or "certidao.pdf"
                    sub = os.path.join(cert_dir, sq)
                    os.makedirs(sub, exist_ok=True)
                    destino = os.path.join(sub, resto)
                    k = 1
                    while os.path.exists(destino):
                        k += 1
                        destino = os.path.join(sub, "%s_%d.pdf" % (resto[:-4], k))
                    with z.open(member) as src, open(destino, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    alvos[sq].setdefault("certidoes", []).append("data/certidoes/%s/%s" % (sq, os.path.basename(destino)))
                    n_cert += 1
    for c in alvos.values():
        for k in ("propostas", "certidoes"):
            if k in c:
                c[k].sort()
    return n_foto, n_prop, n_cert


# ---------------------------------------------------------------- saida
def write_js(path, varname, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.%s=" % varname)
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=RAW_DIR_DEFAULT, help="pasta com os arquivos do TSE")
    ap.add_argument("--sem-arquivos", action="store_true", help="nao extrai fotos/propostas/certidoes")
    ap.add_argument("--votacao-ufs", default="", help="UFs a cruzar na votacao por municipio, ex.: RO,AC (vazio = todas as UFs presentes)")
    args = ap.parse_args()

    print("Lendo candidatos de:", args.raw)
    titulares, chapas, total_linhas, fontes = build_candidatos(args.raw)
    if not titulares:
        print("\nNenhum CSV consulta_cand_2026 encontrado em", args.raw)
        print("Baixe consulta_cand_2026.zip em https://dadosabertos.tse.jus.br/dataset/candidatos-2026")
        print("e coloque em raw/ (nao precisa extrair).")
        sys.exit(1)
    print("  linhas lidas: %d | titulares: %d | fontes: %s" % (total_linhas, len(titulares), ", ".join(fontes)))

    chapas_por_sq = {m["sq"]: m for lst in chapas.values() for m in lst}
    print("  complementar: %d candidatos" % aplicar_complementar(args.raw, titulares, chapas_por_sq))
    for cand in titulares.values():
        membros = chapas.get((cand["sgUe"], cand["cargo"].upper(), cand["nr"]))
        if membros:
            cand["chapa"] = membros
    print("  historico: %d candidaturas anteriores" % aplicar_historico(args.raw, titulares))
    print("  bens: %d itens" % aplicar_bens(args.raw, titulares))
    print("  redes sociais: %d links" % aplicar_redes(args.raw, titulares))
    print("  motivos de indeferimento/cassacao: %d" % aplicar_motivos(args.raw, titulares))
    ufs_vot = [u.strip().upper() for u in args.votacao_ufs.split(",") if u.strip()] if args.votacao_ufs else None
    nv, fontes_vot = aplicar_votacao(args.raw, titulares, ufs_vot)
    print("  votacao por municipio: %d linhas cruzadas de %s" % (nv, ", ".join(fontes_vot)) if fontes_vot else
          "  votacao por municipio: nenhum votacao_candidato_munzona_*.zip em raw/ (opcional)")
    nc_, nr_, nd_ = aplicar_contas(args.raw, titulares)
    print("  prestacao de contas: %d candidatos, %d receitas, %d despesas" % (nc_, nr_, nd_) if nc_ else
          "  prestacao de contas: prestacao_de_contas_eleitorais_candidatos_2026.zip ausente em raw/ (opcional)")
    vagas = ler_vagas(args.raw)
    print("  vagas: %d UFs" % len(vagas))
    os.makedirs(OUT_DIR, exist_ok=True)
    denuncias = ler_denuncias(args.raw)
    if denuncias:
        write_js(os.path.join(OUT_DIR, "denuncias.js"), "DENUNCIAS", denuncias)
        print("  denuncias (Pardal): %d UFs, anos %s" % (len(denuncias), sorted({a for d in denuncias.values() for a in d})))

    os.makedirs(OUT_DIR, exist_ok=True)
    if not args.sem_arquivos:
        nf, np_, nc = extrair_arquivos(args.raw, titulares, chapas_por_sq)
        print("  fotos: %d | propostas: %d | certidoes: %d" % (nf, np_, nc))

    por_uf = defaultdict(list)
    for c in titulares.values():
        por_uf[c["uf"] or "XX"].append(c)

    for f in os.listdir(OUT_DIR):
        if re.match(r"cand_[A-Z]{2}\.js$", f):
            os.remove(os.path.join(OUT_DIR, f))

    manifest = {
        "geradoEm": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "amostra": False,
        "fontes": fontes,
        "ufs": [],
        "contagens": {},
        "vagas": vagas,
        "cargos": sorted({c["cargo"] for c in titulares.values()}),
        "partidos": sorted({c["partido"] for c in titulares.values() if c["partido"]}),
    }
    for uf in sorted(por_uf):
        lst = sorted(por_uf[uf], key=lambda c: (c["cdCargo"] or 99, c["urna"] or c["nome"]))
        write_js(os.path.join(OUT_DIR, "cand_%s.js" % uf), "CAND_%s" % uf, lst)
        cont = defaultdict(int)
        for c in lst:
            cont[c["cargo"]] += 1
        manifest["ufs"].append(uf)
        manifest["contagens"][uf] = {"total": len(lst), **dict(cont)}
        print("  %s: %5d candidatos" % (uf, len(lst)))

    write_js(os.path.join(OUT_DIR, "manifest.js"), "MANIFEST", manifest)
    print("\nOK - arquivos gerados em", OUT_DIR)


if __name__ == "__main__":
    main()
