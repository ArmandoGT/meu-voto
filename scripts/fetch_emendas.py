# -*- coding: utf-8 -*-
"""
fetch_emendas.py - "para onde cada politico mandou emendas": baixa e cruza as emendas parlamentares
federais (deputados federais e senadores, Portal da Transparencia/CGU) e estaduais de Rondonia
(deputados estaduais, Portal da Transparencia do Governo de RO) com os candidatos de 2026.
Grava data/emendas.js (window.EMENDAS).

Uso:
    python scripts/fetch_emendas.py              # baixa as duas fontes (~200 MB descompactados) e gera o arquivo
    python scripts/fetch_emendas.py --sem-baixar # reaproveita raw/EmendasParlamentares.zip e raw/emendas_ro_estaduais.csv
    python scripts/fetch_emendas.py --uf-detalhe RO,MT   # UFs com lista item a item por municipio (padrao RO)

Fontes (publicas, sem chave, baixam por script):
  Federal  https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO  (atualizado diariamente)
           EmendasParlamentares.csv            emenda x localidade: autor, funcao, acao, empenhado/liquidado/pago
           EmendasParlamentares_PorFavorecido  quem recebeu o dinheiro (prefeitura, fundo, entidade) e onde
           EmendasParlamentares_Convenios      objeto do convenio (ex.: "Aquisicao de um trator")
  RO       https://transparencia.ro.gov.br/emenda  (exportacao CSV, 2023 em diante; inclui transferencias especiais)

Casamento autor -> candidato: nome de urna/nome civil normalizados, na mesma UF (ver casar()).
Correcoes manuais em data/emendas_alias.json: {"NOME DO AUTOR COMO NA FONTE": "SQ_CANDIDATO" ou null}.
Emendas de bancada, comissao e relator nao tem autor individual: aparecem por municipio, sem candidato.

Somente stdlib.
"""
import argparse
import collections
import csv
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(ROOT, "raw")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

URL_FED = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
ZIP_FED = os.path.join(RAW, "EmendasParlamentares.zip")
URL_RO = "https://transparencia.ro.gov.br/emenda"
URL_RO_CSV = "https://transparencia.ro.gov.br/Emenda/GerarArquivo"
CSV_RO = os.path.join(RAW, "emendas_ro_estaduais.csv")
MUNICIPIO_FOCO = "ARIQUEMES"
UF_FOCO = "RO"

UF_NOME = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
           "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
           "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
           "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC",
           "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}
TITULOS = {"dr", "dra", "delegado", "delegada", "coronel", "cel", "capitao", "cap", "sargento", "sgt", "pastor", "pastora",
           "professor", "professora", "prof", "profa", "missionario", "irmao", "irma", "doutor", "doutora", "eng", "juiza", "juiz",
           "padre", "tenente", "major", "subtenente", "cabo", "soldado", "enfermeira", "enfermeiro", "vereador", "deputado", "deputada"}
LIGA = {"da", "de", "do", "das", "dos", "e"}
SEM_AUTOR = ("sem informacao", "bancada", "comissao", "relator", "lideranca", "mesa diretora", "s/i")


# ---------------------------------------------------------------- utilidades
def sem_acento(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", sem_acento(s).lower()).split()


MUN_OFICIAL = {}          # (uf, chave_solta) -> nome oficial sem acento em maiusculas (tabela TSE/IBGE)
SEM_MUNICIPIO = {"", "MULTIPLO", "SEM INFORMACAO", "NACIONAL", "EXTERIOR"}


def _solto(nome):
    """Chave tolerante a grafias: "Espigao D'Oeste" == "Espigao do Oeste"; "Alta Floresta" == "Alta Floresta D'Oeste"."""
    return " ".join(t for t in norm(nome) if t not in ("d", "do", "da", "de", "oeste"))


def carregar_municipios():
    p = os.path.join(RAW, "municipio_tse_ibge.zip")
    if not os.path.exists(p):
        print("  aviso: raw/municipio_tse_ibge.zip ausente (rode scripts/baixar_tse.py --so municipio_tse_ibge); nomes de municipio nao serao unificados")
        return
    z = zipfile.ZipFile(p)
    n = next(x for x in z.namelist() if x.lower().endswith(".csv"))
    vistos = collections.Counter()
    linhas = []
    for r in abrir_csv_zip(z, n):
        nome = " ".join(sem_acento(r["NM_MUNICIPIO_IBGE"] or r["NM_MUNICIPIO_TSE"]).upper().split())
        linhas.append((r["SG_UF"], nome))
        vistos[(r["SG_UF"], _solto(nome))] += 1
    for uf, nome in linhas:
        MUN_OFICIAL[(uf, " ".join(nome.split()))] = nome
        if vistos[(uf, _solto(nome))] == 1:
            MUN_OFICIAL[(uf, _solto(nome))] = nome


def nome_mun(uf, mun):
    m = " ".join(sem_acento(mun or "").upper().split())
    if m in SEM_MUNICIPIO:
        return ""
    oficial = MUN_OFICIAL.get((uf, m)) or MUN_OFICIAL.get((uf, _solto(m)))
    if oficial or not MUN_OFICIAL:
        return oficial or m
    return ""   # nome que nao existe nessa UF (erro da fonte): conta no nivel estadual


def chave_mun(uf, mun):
    return "%s|%s" % (uf, nome_mun(uf, mun))


def valor(s):
    """'1.234,56' / 'R$ 1.234,56' / '1234,56' -> float"""
    s = (s or "").replace("R$", "").replace("\xa0", "").strip()
    if not s:
        return 0.0
    neg = s.startswith("-")
    s = s.lstrip("-").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def r2(v):
    return round(v, 2)


def baixar(url, destino, opener=None, dados=None):
    op = opener or urllib.request.build_opener()
    req = urllib.request.Request(url, data=dados, headers={"User-Agent": UA})
    for i in range(3):
        try:
            with op.open(req, timeout=600) as r, open(destino + ".part", "wb") as f:
                total = int(r.headers.get("content-length") or 0)
                feito = 0
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
                    feito += len(b)
                    sys.stdout.write("\r    %.1f MB%s   " % (feito / 1048576.0, (" de %.1f" % (total / 1048576.0)) if total else ""))
                    sys.stdout.flush()
            sys.stdout.write("\n")
            os.replace(destino + ".part", destino)
            return
        except Exception as e:  # noqa: BLE001
            if i == 2:
                raise
            print("    falhou (%s); tentando de novo..." % e)
            time.sleep(5 * (i + 1))


def ler_js_var(p):
    txt = open(p, encoding="utf-8").read()
    return json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))


# ---------------------------------------------------------------- candidatos e casamento de nomes
def carregar_candidatos():
    cands = []
    for nome in sorted(os.listdir(DATA)):
        if re.match(r"cand_[A-Z]{2}\.js$", nome):
            try:
                cands += ler_js_var(os.path.join(DATA, nome))
            except (ValueError, OSError):
                print("  aviso: nao consegui ler", nome)
    return cands


PRIORIDADE_CARGO = {"Deputado Federal": 0, "Senador": 1, "Deputado Estadual": 2, "Governador": 3, "Vice-Governador": 4,
                    "Presidente": 5, "Deputado Distrital": 2}


# cargos que comprovam o mandato de quem apresentou a emenda (historico_candidatura do TSE)
CARGOS_MANDATO = {"fed": {"DEPUTADO FEDERAL", "SENADOR", "1º SUPLENTE", "2º SUPLENTE", "1º SUPLENTE SENADOR", "2º SUPLENTE SENADOR"},
                  "est": {"DEPUTADO ESTADUAL"}}


class Casador:
    """Casa o nome do autor da emenda com um candidato de 2026.

    Nivel 0 (nome de urna identico ao da fonte) vale sozinho. Nivel 1 (igual ignorando da/de/dos: "EDSON SANTOS" x
    "EDSON DOS SANTOS"), 2 (nome da fonte contido no nome civil)
    e 3 (nome de urna contido no da fonte) so valem se o historico eleitoral do candidato mostrar que ele ja
    disputou o cargo que apresenta esse tipo de emenda — evita casar o senador com o filho ou com um homonimo
    (ex.: "JADER BARBALHO" x "Jader Filho", "RODRIGO PACHECO" x um candidato a deputado estadual).
    """

    def __init__(self, cands, alias):
        self.alias = alias
        self.por_uf = collections.defaultdict(list)
        for c in cands:
            uf = c.get("uf")
            urna = [t for t in norm(c.get("urna")) if t not in TITULOS]
            civil = norm(c.get("nome"))
            social = norm(c.get("social"))
            cargos = {" ".join((h.get("cargo") or "").upper().split()) for h in c.get("hist", [])}
            self.por_uf[uf].append((c, set(urna) - LIGA, set(civil) - LIGA, set(social) - LIGA, " ".join(urna), cargos))
        self.cache = {}
        self.criterio = {}      # (autor, uf, nivel) -> "alias" | "urna" | "historico"
        self.rejeitados = []    # (autor, candidato) casamentos por nome sem historico que confirme
        self.ambiguos = []      # autor com mais de um candidato possivel (resolver em data/emendas_alias.json)
        self._hist = {id(x[0]): x[5] for l in self.por_uf.values() for x in l}

    def _cargos(self, c):
        return self._hist.get(id(c), set())

    def casar(self, autor, uf, nivel="fed"):
        """Devolve o sq do candidato ou None. uf = UF de atuacao do parlamentar (None = qualquer)."""
        k = (autor, uf, nivel)
        if k in self.cache:
            return self.cache[k]
        if autor in self.alias:
            self.cache[k] = self.alias[autor]
            self.criterio[k] = "alias"
            return self.alias[autor]
        base = re.sub(r"\(.*?\)", " ", autor or "")   # "RAFAEL BENTO (EX-PARLAMENTAR LEBRAO...)" -> "RAFAEL BENTO"
        toks_all = [t for t in norm(base) if t not in TITULOS]
        toks = set(toks_all) - LIGA
        achados = []
        if toks:
            ufs = [uf] if uf else list(self.por_uf)
            for u in ufs:
                for c, urna, civil, social, urna_txt, cargos in self.por_uf.get(u, []):
                    if urna_txt == " ".join(toks_all):
                        achados.append((0, c, cargos))
                    elif urna and toks == urna:
                        achados.append((1, c, cargos))
                    elif len(toks) >= 2 and (toks <= civil or (social and toks <= social)):
                        achados.append((2, c, cargos))
                    elif len(urna) >= 2 and urna <= toks:
                        achados.append((3, c, cargos))
        validos = []
        for n, c, cargos in achados:
            if n == 0 or cargos & CARGOS_MANDATO[nivel]:
                validos.append((n, c))
            else:
                self.rejeitados.append((autor, "%s (%s, %s)" % (c.get("urna"), c.get("cargo"), c.get("uf"))))
        sq = None
        if validos:
            melhor = min(n for n, _ in validos)
            top = [c for n, c in validos if n == melhor]
            if len(top) > 1 and len({c.get("nasc") for c in top}) == 1 and top[0].get("nasc"):
                # mesma pessoa com duas candidaturas (ex.: renunciou a deputado e disputa senado): vale a ativa
                ativas = [c for c in top if not re.search(r"RENUN|INDEFER|CANCEL|CASSA|FALEC", sem_acento(c.get("sit") or "").upper())]
                if len(ativas) == 1:
                    top = ativas
            if len(top) > 1:
                # homonimos (ex.: dois "CARLOS MAGNO" em RO): so decide se exatamente um tem o cargo no historico
                com_prova = [c for c in top if self._cargos(c) & CARGOS_MANDATO[nivel]]
                if len(com_prova) == 1:
                    top = com_prova
                else:
                    self.ambiguos.append("%s -> %s" % (autor, " / ".join("%s (%s)" % (c.get("nome"), c.get("cargo")) for c in top)))
            if len(top) == 1:
                sq = top[0]["sq"]
                self.criterio[k] = "urna" if melhor == 0 and not self._cargos(top[0]) & CARGOS_MANDATO[nivel] else "historico" if melhor else "urna"
        self.cache[k] = sq
        return sq


def sem_autor_individual(autor):
    a = " ".join(norm(autor))
    return not a or any(a.startswith(p) for p in SEM_AUTOR)


# ---------------------------------------------------------------- agregadores
def novo_agg():
    return {"emp": 0.0, "pago": 0.0, "n": 0, "anos": collections.defaultdict(lambda: [0.0, 0.0]),
            "uf": collections.defaultdict(float), "mun": collections.defaultdict(lambda: [0.0, 0.0]),
            "funcoes": collections.defaultdict(float), "autores": set(), "tipos": collections.Counter()}


def somar(agg, autor, ano, uf, mun, funcao, emp, pago, tipo):
    agg["emp"] += emp
    agg["pago"] += pago
    agg["n"] += 1
    agg["autores"].add(autor)
    if ano:
        agg["anos"][str(ano)][0] += emp
        agg["anos"][str(ano)][1] += pago
    if uf:
        agg["uf"][uf] += emp
    if mun:
        m = agg["mun"][(mun, uf)]
        m[0] += emp
        m[1] += pago
    if funcao:
        agg["funcoes"][funcao.strip()] += emp
    if tipo:
        agg["tipos"][tipo] += 1


def fechar_agg(a):
    top = sorted(a["mun"].items(), key=lambda kv: -kv[1][0])
    return {
        "emp": r2(a["emp"]), "pago": r2(a["pago"]), "n": a["n"],
        "anos": {k: [r2(v[0]), r2(v[1])] for k, v in sorted(a["anos"].items())},
        "uf": {k: r2(v) for k, v in sorted(a["uf"].items(), key=lambda kv: -kv[1])[:6]},
        "topMun": [[m, u, r2(v[0]), r2(v[1])] for (m, u), v in top[:10]],
        "nMun": len(a["mun"]),
        "funcoes": [[f, r2(v)] for f, v in sorted(a["funcoes"].items(), key=lambda kv: -kv[1])[:6]],
        "autores": sorted(a["autores"]),
    }


TIPO_CURTO = {
    "emenda individual - transferencias com finalidade definida": "Individual",
    "emenda individual - transferencias especiais": "Individual (Pix)",
    "emenda de bancada": "Bancada", "emenda de comissao": "Comissão", "emenda de relator": "Relator (RP9)",
}


def tipo_curto(t):
    return TIPO_CURTO.get(sem_acento(t or "").lower().strip(), (t or "").strip())


# ---------------------------------------------------------------- federal
def abrir_csv_zip(z, nome):
    return csv.DictReader(io.TextIOWrapper(z.open(nome), encoding="latin-1", newline=""), delimiter=";")


# ---------------------------------------------------------------- verificacao oficial (Camara + Senado)
URL_CAMARA_CSV = "https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv"
URL_SENADO_LISTA = "https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/54/57"
URL_SENADO_DET = "https://legis.senado.leg.br/dadosabertos/senador/%s"
CSV_CAMARA = os.path.join(RAW, "camara_deputados.csv")
JSON_SENADO = os.path.join(RAW, "senado_senadores.json")


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def carregar_parlamentares(baixar_de_novo):
    """{data_nascimento 'AAAA-MM-DD': [conjunto de palavras do nome parlamentar + civil]} de todo deputado federal
    (Camara, historico completo) e senador/suplente desde 2011 (Senado). None se nao houver como obter."""
    por_nasc = collections.defaultdict(list)
    try:
        if baixar_de_novo or not os.path.exists(CSV_CAMARA):
            try:
                baixar(URL_CAMARA_CSV, CSV_CAMARA)
            except Exception as e:  # noqa: BLE001 - API fora do ar: vale a copia ja baixada
                if not os.path.exists(CSV_CAMARA):
                    raise
                print("  AVISO: Camara indisponivel (%s); usando a copia local de %s" % (e, CSV_CAMARA))
        with open(CSV_CAMARA, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r.get("dataNascimento"):
                    por_nasc[r["dataNascimento"]].append(set(norm(r.get("nome"))) | set(norm(r.get("nomeCivil"))))
        cache = {}
        if os.path.exists(JSON_SENADO):
            cache = json.load(open(JSON_SENADO, encoding="utf-8"))
        lista = None
        if baixar_de_novo or not cache:
            try:
                lista = _get_json(URL_SENADO_LISTA)["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"]
            except Exception as e:  # noqa: BLE001 - API fora do ar: vale a copia ja baixada
                if not cache:
                    raise
                print("  AVISO: Senado indisponivel (%s); usando a copia local de %s (%d senadores)" % (e, JSON_SENADO, len(cache)))
        if lista is not None:
            faltam = [p["IdentificacaoParlamentar"] for p in lista if p["IdentificacaoParlamentar"]["CodigoParlamentar"] not in cache]
            print("  Senado: %d senadores/suplentes, buscando %d detalhes..." % (len(lista), len(faltam)))
            for i, ident in enumerate(faltam, 1):
                try:
                    d = _get_json(URL_SENADO_DET % ident["CodigoParlamentar"])["DetalheParlamentar"]["Parlamentar"]
                    cache[ident["CodigoParlamentar"]] = {"nome": ident.get("NomeParlamentar"), "nomeCompleto": ident.get("NomeCompletoParlamentar"),
                                                         "nasc": (d.get("DadosBasicosParlamentar") or {}).get("DataNascimento")}
                except Exception as e:  # noqa: BLE001
                    print("    senador %s: %s" % (ident["CodigoParlamentar"], e))
                if i % 50 == 0:
                    print("    %d/%d" % (i, len(faltam)))
                time.sleep(0.1)
            with open(JSON_SENADO, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        for x in cache.values():
            if x.get("nasc"):
                por_nasc[x["nasc"]].append(set(norm(x.get("nome"))) | set(norm(x.get("nomeCompleto"))))
    except Exception as e:  # noqa: BLE001
        print("  AVISO: nao consegui as listas da Camara/Senado (%s); casamentos federais sem verificacao por data de nascimento" % e)
        return None
    return por_nasc


def nascimento_confere(parl, cand, autor):
    """O candidato nasceu no mesmo dia de um deputado/senador cujo nome tem alguma palavra do nome do autor?"""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", cand.get("nasc") or "")
    if not m:
        return False
    import datetime  # noqa: PLC0415
    d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    toks = {t for t in norm(re.sub(r"\(.*?\)", " ", autor)) if t not in TITULOS and t not in LIGA and len(t) > 2}
    # tolerancia de 1 dia: Camara e TSE as vezes divergem (ex.: Dayane Pimentel 30/01 x 31/01/1986)
    for delta in (0, -1, 1):
        iso = (d + datetime.timedelta(days=delta)).isoformat()
        if any(toks & nomes for nomes in parl.get(iso, [])):
            return True
    return False


def processar_federal(casador, ufs_detalhe, por_cand, por_mun, nao_casados, foco, criterios, parl=None, cand_por_sq=None):
    z = zipfile.ZipFile(ZIP_FED)
    nomes = z.namelist()
    base = next(n for n in nomes if n.lower() == "emendasparlamentares.csv")
    fav = next((n for n in nomes if "favorecido" in n.lower()), None)
    conv = next((n for n in nomes if "convenio" in n.lower()), None)

    # 1a passada: UF de atuacao de cada autor (UF onde mais destinou; ignora "Nacional"/"Exterior")
    uf_autor = collections.defaultdict(collections.Counter)
    linhas = []
    for r in abrir_csv_zip(z, base):
        uf = UF_NOME.get(sem_acento(r.get("UF", "")).upper().strip())
        if not uf:
            m = re.search(r"\(UF\)$", r.get("Localidade de aplicação do recurso", ""))
            loc = sem_acento(r.get("Localidade de aplicação do recurso", "")).upper()
            if m:
                uf = UF_NOME.get(loc.replace("(UF)", "").strip())
        r["_uf"] = uf
        uf_autor[r["Nome do Autor da Emenda"]][uf] += valor(r["Valor Empenhado"]) + 1
        linhas.append(r)
    print("  federal: %d linhas (emenda x localidade), %d autores" % (len(linhas), len(uf_autor)))

    def uf_principal(autor):
        c = uf_autor.get(autor)
        if not c:
            return None
        for uf, _ in c.most_common():
            if uf:
                return uf
        return None

    sq_autor = {}
    for autor in uf_autor:
        if sem_autor_individual(autor):
            sq_autor[autor] = None
            continue
        sq = casador.casar(autor, uf_principal(autor), "fed")
        crit = casador.criterio.get((autor, uf_principal(autor), "fed"))
        if sq and crit != "alias" and parl is not None:
            if nascimento_confere(parl, cand_por_sq[sq], autor):
                crit = crit + "+nascimento"
            else:
                c = cand_por_sq[sq]
                casador.rejeitados.append((autor, "%s (%s, %s, nasc. %s) - data de nascimento nao bate com nenhum deputado/senador"
                                           % (c.get("urna"), c.get("cargo"), c.get("uf"), c.get("nasc"))))
                sq = None
        sq_autor[autor] = sq
        if sq:
            criterios[sq].setdefault("fed", set()).add(crit)
        if not sq and uf_principal(autor) in ufs_detalhe:
            nao_casados["federal"].add("%s (%s)" % (autor, uf_principal(autor)))

    # objeto dos convenios, por codigo da emenda
    objetos = collections.defaultdict(list)
    if conv:
        for r in abrir_csv_zip(z, conv):
            ob = (r.get("Objeto Convênio") or "").strip()
            if ob:
                objetos[r["Código da Emenda"]].append((r.get("Convenente", "").strip(), ob[:220], valor(r.get("Valor Convênio"))))

    for r in linhas:
        autor = r["Nome do Autor da Emenda"]
        sq = sq_autor.get(autor)
        uf = r["_uf"]
        mun = (r.get("Município") or "").strip()
        emp, pago = valor(r["Valor Empenhado"]), valor(r["Valor Pago"]) + valor(r.get("Valor Restos A Pagar Pagos"))
        tipo = tipo_curto(r["Tipo de Emenda"])
        if sq:
            a = por_cand[sq].setdefault("fed", novo_agg())
            somar(a, autor, r["Ano da Emenda"], uf, nome_mun(uf, mun) or "(sem município)", r.get("Nome Função"), emp, pago, tipo)
            if uf == UF_FOCO and nome_mun(uf, mun) == MUNICIPIO_FOCO:
                f = foco[sq].setdefault("fed", {"emp": 0.0, "pago": 0.0, "n": 0, "rec": 0.0})
                f["emp"] += emp
                f["pago"] += pago
                f["n"] += 1
        if uf in ufs_detalhe:
            # so busca o objeto do convenio por codigo real: "Sem informacao" casaria com convenios de outras emendas
            obs = objetos.get(r["Código da Emenda"], []) if r["Código da Emenda"].isdigit() else []
            ob = next((o for cv, o, _ in obs if nome_mun(uf, mun) and nome_mun(uf, mun) in sem_acento(cv).upper()), None) or (obs[0][1] if len(obs) == 1 else None)
            por_mun[chave_mun(uf, mun)].append({
                "nv": "fed", "a": autor, "sq": sq, "ano": int(r["Ano da Emenda"] or 0), "t": tipo,
                "f": (r.get("Nome Função") or "").strip(), "o": ob or (r.get("Nome Ação") or "").strip().capitalize(),
                "e": r2(emp), "p": r2(pago), "cod": r["Código da Emenda"],
            })

    # favorecidos: dinheiro que efetivamente chegou a quem esta no municipio
    if fav:
        grupos = {}
        for r in abrir_csv_zip(z, fav):
            uf = (r.get("UF Favorecido") or "").strip().upper()
            mun = (r.get("Município Favorecido") or "").strip()
            autor = r["Nome do Autor da Emenda"]
            sq = sq_autor.get(autor)
            if sq:   # para onde o dinheiro do parlamentar chegou de fato (todas as UFs)
                a = por_cand[sq].setdefault("fed", novo_agg())
                rm = a.setdefault("recMun", collections.defaultdict(float))
                v = valor(r.get("Valor Recebido"))
                rm[(nome_mun(uf, mun) if uf in UF_NOME.values() else "") or "(sem município)", uf or None] += v
                a["rec"] = a.get("rec", 0.0) + v
            if uf not in ufs_detalhe:
                continue
            pf = "fisica" in sem_acento(r.get("Tipo Favorecido", "")).lower()
            nome_fav = "Pessoas físicas" if pf else (r.get("Favorecido") or "").strip()
            k = (chave_mun(uf, mun), r["Código da Emenda"], nome_fav)
            g = grupos.get(k)
            if not g:
                g = grupos[k] = {"nv": "fav", "a": autor, "sq": sq_autor.get(autor), "ano": int((r.get("Ano/Mês") or "0")[:4] or 0),
                                 "t": tipo_curto(r.get("Tipo de Emenda")), "fav": nome_fav, "r": 0.0, "cod": r["Código da Emenda"], "npf": 0}
            g["r"] += valor(r.get("Valor Recebido"))
            if pf:
                g["npf"] += 1
        for (km, _, _), g in grupos.items():
            if g["r"] <= 0:
                continue
            g["r"] = r2(g["r"])
            if not g["npf"]:
                del g["npf"]
            por_mun[km].append(g)
            if g["sq"] and km == chave_mun(UF_FOCO, MUNICIPIO_FOCO):
                f = foco[g["sq"]].setdefault("fed", {"emp": 0.0, "pago": 0.0, "n": 0, "rec": 0.0})
                f["rec"] += g["r"]
                f["n"] += 1
        print("  federal: %d grupos de favorecidos nas UFs de detalhe" % len(grupos))
    casados = sum(1 for a, s in sq_autor.items() if s)
    print("  federal: %d autores casados com candidatos de 2026" % casados)


# ---------------------------------------------------------------- estadual RO
def baixar_ro():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    html = op.open(URL_RO, timeout=120).read().decode("utf-8", "replace")
    tok = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', html).group(1)
    # a exportacao traz todos os exercicios (estaduais + transferencias especiais), em UTF-8
    dados = urllib.parse.urlencode({"Exercicio": "", "MesInicial": "", "MesFinal": "", "CodDocumento": "", "NomeFonteDetalhada": "",
                                    "TipoEmenda": "", "Descricao": "", "__RequestVerificationToken": tok,
                                    "ContentTypeFile": "1", "DespesaOuEmpenho": "emendas_estaduais.csv"}).encode()
    baixar(URL_RO_CSV, CSV_RO, op, dados)


def municipios_ro():
    p = os.path.join(RAW, "municipio_tse_ibge.zip")
    nomes = []
    if os.path.exists(p):
        z = zipfile.ZipFile(p)
        n = next(x for x in z.namelist() if x.lower().endswith(".csv"))
        for r in abrir_csv_zip(z, n):
            if r["SG_UF"] == UF_FOCO:
                nomes.append(r["NM_MUNICIPIO_IBGE"] or r["NM_MUNICIPIO_TSE"])
    return nomes


def processar_ro(casador, por_cand, por_mun, nao_casados, foco, criterios):
    muns = municipios_ro()
    # procura nomes mais longos primeiro ("Alto Paraiso" antes de "Paraiso"...)
    pads = [(m, re.compile(r"\b%s\b" % re.escape(" ".join(norm(m))))) for m in sorted(muns, key=len, reverse=True)]
    n = 0
    anos = collections.Counter()
    with open(CSV_RO, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            n += 1
            autor = (r.get("Nome_fonte_detalhada") or "").strip()
            ano = int(r.get("Exercicio") or 0)
            anos[ano] += 1
            loc = (r.get("LocalidadeBeneficiada") or "").strip()
            inferido = False
            if loc.endswith("- RO"):
                mun = loc[:-4].strip()
            else:
                # "Estado de Rondonia": tenta achar o municipio na descricao do objeto
                desc_n = " ".join(norm(r.get("Descricao")))
                achados = []
                for m, pad in pads:
                    if pad.search(desc_n) and not any(" ".join(norm(m)) in " ".join(norm(a)) for a in achados):
                        achados.append(m)
                mun = achados[0] if len(achados) == 1 else ""
                inferido = bool(mun)
            emp, pago, prev = valor(r.get("Empenhado")), valor(r.get("Pago")), valor(r.get("Maior_empenhar"))
            sq = None if sem_autor_individual(autor) else casador.casar(autor, UF_FOCO, "est")
            if sq:
                criterios[sq].setdefault("est", set()).add(casador.criterio[(autor, UF_FOCO, "est")])
            if not sq and autor:
                nao_casados["estadual"].add(autor)
            forma = (r.get("FormaRepasse") or "").strip()
            tipo = "Transferência especial" if "especial" in sem_acento(forma).lower() else (r.get("TipoEmenda") or "").strip()
            funcao = (r.get("Descricao_funcao") or "").strip().capitalize()
            if sq:
                a = por_cand[sq].setdefault("est", novo_agg())
                somar(a, autor, ano, UF_FOCO, nome_mun(UF_FOCO, mun) or "(sem município)", funcao, emp, pago, tipo)
                a.setdefault("prev", 0.0)
                a["prev"] += prev
                if nome_mun(UF_FOCO, mun) == MUNICIPIO_FOCO:
                    fo = foco[sq].setdefault("est", {"emp": 0.0, "pago": 0.0, "n": 0, "prev": 0.0})
                    fo["emp"] += emp
                    fo["pago"] += pago
                    fo["prev"] += prev
                    fo["n"] += 1
            benef = (r.get("Beneficiario") or "").strip()
            if sem_acento(benef).lower().startswith("nao informado"):
                benef = ""
            item = {"nv": "est", "a": autor, "sq": sq, "ano": ano, "t": tipo, "f": funcao,
                    "o": re.sub(r"\s+", " ", (r.get("Descricao") or "").strip())[:260], "e": r2(emp), "p": r2(pago), "pv": r2(prev),
                    "fav": benef[:120], "doc": (r.get("Cod_documento") or r.get("Cod_documento_pe") or "").strip(), "fr": forma}
            if inferido:
                item["inf"] = 1
            por_mun[chave_mun(UF_FOCO, mun)].append(item)
    print("  estadual RO: %d linhas (%s)" % (n, ", ".join("%d: %d" % kv for kv in sorted(anos.items()))))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-baixar", action="store_true", help="usa os arquivos ja baixados em raw/")
    ap.add_argument("--uf-detalhe", default="RO", help="UFs com lista item a item por municipio (padrao RO)")
    ap.add_argument("--sem-estadual", action="store_true")
    args = ap.parse_args()
    ufs_detalhe = {u.strip().upper() for u in args.uf_detalhe.split(",") if u.strip()}
    os.makedirs(RAW, exist_ok=True)

    if not args.sem_baixar or not os.path.exists(ZIP_FED):
        print("Baixando emendas federais (Portal da Transparencia)...")
        baixar(URL_FED, ZIP_FED)
    if not args.sem_estadual and (not args.sem_baixar or not os.path.exists(CSV_RO)):
        print("Baixando emendas estaduais de RO (transparencia.ro.gov.br)...")
        try:
            baixar_ro()
        except Exception as e:  # noqa: BLE001
            print("  falhou (%s). Baixe manualmente em %s (botao CSV) e salve como %s" % (e, URL_RO, CSV_RO))

    carregar_municipios()
    cands = carregar_candidatos()
    print("Candidatos 2026 carregados: %d" % len(cands))
    alias_p = os.path.join(DATA, "emendas_alias.json")
    alias = {}
    if os.path.exists(alias_p):
        alias = {k: v for k, v in json.load(open(alias_p, encoding="utf-8")).items() if not k.startswith("_")}
    casador = Casador(cands, alias)
    print("Carregando deputados (Camara) e senadores (Senado) para conferir data de nascimento...")
    parl = carregar_parlamentares(not args.sem_baixar)
    cand_por_sq = {c["sq"]: c for c in cands}

    por_cand = collections.defaultdict(dict)
    por_mun = collections.defaultdict(list)
    foco = collections.defaultdict(dict)
    nao_casados = {"federal": set(), "estadual": set()}

    print("Processando emendas federais...")
    criterios = collections.defaultdict(dict)
    processar_federal(casador, ufs_detalhe, por_cand, por_mun, nao_casados, foco, criterios, parl, cand_por_sq)
    if not args.sem_estadual and os.path.exists(CSV_RO):
        print("Processando emendas estaduais de RO...")
        processar_ro(casador, por_cand, por_mun, nao_casados, foco, criterios)

    saida_cand = {}
    for sq, d in por_cand.items():
        o = {}
        for nv in ("fed", "est"):
            if nv in d:
                o[nv] = fechar_agg(d[nv])
                if "prev" in d[nv]:
                    o[nv]["prev"] = r2(d[nv]["prev"])
                o[nv]["casamento"] = sorted(criterios[sq].get(nv, []))
        rm = d.get("fed", {}).get("recMun")
        if rm:
            o["fed"]["rec"] = r2(d["fed"].get("rec", 0.0))
            o["fed"]["recMun"] = [[m, u, r2(v)] for (m, u), v in sorted(rm.items(), key=lambda kv: -kv[1])[:10] if v > 0]
            o["fed"]["nRecMun"] = sum(1 for v in rm.values() if v > 0)
        if sq in foco:
            o["foco"] = {nv: {k: (r2(v) if isinstance(v, float) else v) for k, v in x.items()} for nv, x in foco[sq].items()}
        saida_cand[sq] = o
    for k in por_mun:
        por_mun[k].sort(key=lambda x: (-(x.get("ano") or 0), -(x.get("e") or x.get("r") or 0)))

    saida = {
        "atualizado": time.strftime("%Y-%m-%d"),
        "foco": {"uf": UF_FOCO, "mun": MUNICIPIO_FOCO},
        "ufsDetalhe": sorted(ufs_detalhe),
        "fontes": {"federal": URL_FED, "estadual": URL_RO},
        "porCand": saida_cand,
        "porMun": dict(sorted(por_mun.items())),
        "naoCasados": {k: sorted(v) for k, v in nao_casados.items()},
        "rejeitados": sorted({"%s -> %s" % r for r in casador.rejeitados}),
        "ambiguos": sorted(set(casador.ambiguos)),
    }
    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, "emendas.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.EMENDAS=")
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    if not os.path.exists(alias_p):
        with open(alias_p, "w", encoding="utf-8") as f:
            json.dump({"_comentario": "Correcoes manuais: \"NOME DO AUTOR COMO NA FONTE\": \"SQ_CANDIDATO\" (ou null para nao casar)."}, f, ensure_ascii=False, indent=1)

    print("\nOK - %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576.0))
    print("  candidatos com emendas: %d   municipios com detalhe: %d" % (len(saida_cand), len(por_mun)))
    kf = chave_mun(UF_FOCO, MUNICIPIO_FOCO)
    print("  itens em %s: %d" % (kf, len(por_mun.get(kf, []))))
    for a in saida["ambiguos"]:
        print("  AMBIGUO (resolva em data/emendas_alias.json): " + a)
    print("  casamentos recusados (sem historico ou data de nascimento que confirme): %d (lista em EMENDAS.rejeitados)" % len(saida["rejeitados"]))
    for nv, l in saida["naoCasados"].items():
        if l:
            print("  autores %s sem candidato 2026 correspondente (%d): %s" % (nv, len(l), "; ".join(l[:40]) + (" ..." if len(l) > 40 else "")))


if __name__ == "__main__":
    main()
