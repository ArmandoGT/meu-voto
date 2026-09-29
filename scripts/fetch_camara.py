# -*- coding: utf-8 -*-
"""
fetch_camara.py - busca, na API de Dados Abertos da Camara dos Deputados, a atuacao dos candidatos de 2026
que sao ou ja foram deputados federais (desde 2015) e grava data/camara.js.

Precisa de internet (a API da Camara e publica e nao bloqueia scripts). Nao precisa de chave.

Uso:
    python scripts/fetch_camara.py                 # UF do foco (RO) - ~1 min
    python scripts/fetch_camara.py --uf RR,RS,SC   # algumas UFs (refaz so elas; as outras ficam como estao)
    python scripts/fetch_camara.py --todas         # 27 UFs (~2 h; grava a cada UF, pode interromper e retomar por --uf)

Casamento candidato -> deputado (todos os deputados da UF nas legislaturas 55-57):
    DATA DE NASCIMENTO (+-1 dia) + palavra do nome em comum que identifique (nao contam "dos", "Silva", titulos...).
    Um deputado fica com um candidato so: o de mais palavras em comum (gemeos Furlan/AP); mesma pessoa com duas
    candidaturas fica a ativa (Ronaldo Fonseca/DF, Carlos Jordy/RJ); empate de verdade nao casa e vai para o log.

O que traz por deputado (chave = SQ_CANDIDATO de 2026):
    id, url, nomeParlamentar, partido, uf, situacao, atual, mandatos, nasc, proposicoes (desde propDesde),
    frentes, e para quem esta no mandato: email, gabinete, orgaos (comissoes), despesas.
UFs cuja API falhou aparecem no fim como "UFs INCOMPLETAS" com o comando para refazer.

Somente stdlib.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://dadosabertos.camara.leg.br/api/v2"
LEGISLATURA = 57                                  # atual (2023-2027)
LEGISLATURAS = (55, 56, 57)                       # desde 2015: pega tambem ex-deputados que disputam 2026
INICIO_LEG = {55: "2015-02-01", 56: "2019-02-01", 57: "2023-02-01"}
ANOS_DESPESA = (2025, 2026)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z ]", " ", s.lower()).split()


def get_json(url, tentativas=5):   # a API da Camara as vezes devolve 504; espera 2, 4, 8, 16 s
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "MeuVoto2026/1.0"})
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                print("    falhou:", url, e)
                return None
            time.sleep(2 ** (i + 1))


# palavras que nao identificam ninguem: nao contam como "nome em comum"
COMUNS = {"da", "de", "do", "das", "dos", "e", "filho", "filha", "junior", "neto", "neta", "sobrinho", "segundo",
          "silva", "santos", "souza", "sousa", "oliveira", "pereira", "lima", "costa", "ferreira", "rodrigues", "alves",
          "almeida", "nascimento", "gomes", "ribeiro", "carvalho", "martins", "araujo", "barbosa", "rocha", "dias",
          "moura", "melo", "mello", "cardoso", "teixeira", "correia", "nunes", "mendes", "soares", "vieira", "lopes",
          "dr", "dra", "prof", "professor", "professora", "pastor", "delegado", "delegada", "coronel", "capitao",
          "sargento", "cabo", "irmao", "irma", "doutor", "doutora", "enfermeira", "tenente", "major"}


def palavras(*nomes):
    return {t for n in nomes for t in norm(n) if len(t) > 2 and t not in COMUNS}


def data_tse(s):
    """'16/06/1958' -> date"""
    try:
        return datetime.datetime.strptime(s or "", "%d/%m/%Y").date()
    except ValueError:
        return None


def data_iso(s):
    try:
        return datetime.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


FALHAS = []   # consultas que falharam mesmo apos as tentativas


def paginar(url, limite=2000):
    """Segue os links 'next' da API e devolve todos os 'dados'."""
    out = []
    while url and len(out) < limite:
        j = get_json(url)
        if not j:
            FALHAS.append(url)
            break
        out.extend(j.get("dados", []))
        url = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
    return out


def carregar_candidatos(uf):
    p = os.path.join(DATA, "cand_%s.js" % uf)
    if not os.path.exists(p):
        return []
    txt = open(p, encoding="utf-8").read()
    return json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))


def gravar(saida_p, resultado):
    os.makedirs(DATA, exist_ok=True)
    tmp = saida_p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.CAMARA=")
        json.dump(resultado, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(tmp, saida_p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="RO", help="UFs separadas por virgula")
    ap.add_argument("--todas", action="store_true")
    args = ap.parse_args()

    manifest_p = os.path.join(DATA, "manifest.js")
    ufs_disp = []
    if os.path.exists(manifest_p):
        txt = open(manifest_p, encoding="utf-8").read()
        ufs_disp = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";")).get("ufs", [])
    ufs = [u for u in ufs_disp if u != "BR"] if args.todas else [u.strip().upper() for u in args.uf.split(",") if u.strip()]

    saida_p = os.path.join(DATA, "camara.js")
    resultado = {}
    if os.path.exists(saida_p):
        txt = open(saida_p, encoding="utf-8").read()
        try:
            resultado = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
        except ValueError:
            resultado = {}

    incompletas = []
    for uf in ufs:
        print("UF", uf)
        n_falhas = len(FALHAS)
        # refaz a UF do zero (casamentos antigos errados nao ficam gravados); as outras UFs ficam como estavam
        sq_da_uf = {c["sq"] for c in carregar_candidatos(uf)}
        resultado = {sq: v for sq, v in resultado.items() if sq not in sq_da_uf}
        # deputados da UF em todas as legislaturas desde 2015 (inclui ex-deputados que disputam 2026)
        deputados = {}
        for leg in LEGISLATURAS:
            for dep in paginar("%s/deputados?siglaUf=%s&idLegislatura=%d&itens=100&ordem=ASC&ordenarPor=nome" % (API, uf, leg)):
                deputados.setdefault(dep["id"], set()).add(leg)
        print("  deputados de %s na Camara desde 2015: %d" % (uf, len(deputados)))
        cands = carregar_candidatos(uf)   # qualquer cargo: deputado pode disputar senado/governo/estadual
        detalhes = {}
        for dep_id in deputados:
            det = get_json("%s/deputados/%d" % (API, dep_id))
            if det:
                detalhes[dep_id] = det["dados"]
            time.sleep(0.15)
        # casa por DATA DE NASCIMENTO (+-1 dia) + ao menos uma palavra do nome em comum que identifique
        # (nao conta "dos", "Silva", "Santos", titulos...).
        # So nome nao basta: "Mariana Carvalho" e "Mauricio Carvalho" (irmaos) tem nomes civis quase iguais.
        # 1) para cada candidato, o deputado com mesma data e MAIS palavras do nome em comum
        melhor_por_cand = []
        for c in cands:
            d_c = data_tse(c.get("nasc"))
            if not d_c:
                continue
            toks_c = palavras(c["nome"], c["urna"], c.get("social"))
            melhor = None
            for dep_id, det in detalhes.items():
                d_d = data_iso(det.get("dataNascimento"))
                if not d_d or abs((d_c - d_d).days) > 1:
                    continue
                toks_d = palavras(det.get("nomeCivil"), (det.get("ultimoStatus") or {}).get("nome"))
                pontos = len(toks_c & toks_d)
                if pontos and (not melhor or pontos > melhor[0]):
                    melhor = (pontos, dep_id)
            if melhor:
                melhor_por_cand.append((melhor[0], melhor[1], c))
        # 2) cada deputado fica com UM candidato: o de mais palavras em comum. Empate = nao casa (ex.: gemeos
        #    Cristiano e Fabricio Bevilacqua Furlan, AP, mesma data; o nome civil completo desempata)
        pares = []
        por_dep = collections.defaultdict(list)
        for pontos, dep_id, c in melhor_por_cand:
            por_dep[dep_id].append((pontos, c))
        for dep_id, lista in por_dep.items():
            lista.sort(key=lambda x: -x[0])
            if len(lista) > 1 and lista[0][0] == lista[1][0]:
                # mesma pessoa com duas candidaturas (ex.: Ronaldo Fonseca, DF: renunciou a deputado, disputa senado)
                empatados = [x for x in lista if x[0] == lista[0][0]]
                ativos = [x for x in empatados if not re.search(r"RENUN|INDEFER|CANCEL|CASSA|FALEC", "".join(
                    ch for ch in unicodedata.normalize("NFD", x[1].get("sit") or "") if unicodedata.category(ch) != "Mn").upper())]
                if len(ativos) == 1 and len({x[1].get("nasc") for x in empatados}) == 1:
                    lista = ativos + [x for x in lista if x not in ativos]
                    print("  obs.: deputado %s tem duas candidaturas; fica a ativa (%s, %s)" % (dep_id, ativos[0][1]["urna"], ativos[0][1]["cargo"]))
                    pares.append((lista[0][1], detalhes[dep_id]))
                    continue
            if len(lista) > 1:
                if lista[0][0] == lista[1][0]:
                    print("  AVISO: deputado %s empatado entre %s - nao casado" % (dep_id, ", ".join(c["urna"] for _, c in lista)))
                    continue
                print("  obs.: deputado %s bate com %s; fica com %s (mais palavras do nome em comum)"
                      % (dep_id, ", ".join(c["urna"] for _, c in lista), lista[0][1]["urna"]))
            pares.append((lista[0][1], detalhes[dep_id]))
        usados = {}
        for c, achado in pares:
            dep_id = achado["id"]
            usados[dep_id] = c["urna"]
            legs = sorted(deputados[dep_id])
            atual = LEGISLATURA in legs
            st = achado.get("ultimoStatus", {}) or {}
            print("  %-30s -> %s (id %s, nasc. %s, legislaturas %s%s)" % (c["urna"], st.get("nome"), dep_id, achado.get("dataNascimento"),
                                                                           ",".join(map(str, legs)), "" if atual else " - ex-deputado"))
            info = {
                "id": dep_id,
                "url": "https://www.camara.leg.br/deputados/%d" % dep_id,
                "nomeParlamentar": st.get("nome"),
                "partido": st.get("siglaPartido"),
                "uf": st.get("siglaUf"),
                "situacao": st.get("situacao") if atual else "Ex-deputado federal",
                "condicao": st.get("condicaoEleitoral"),
                "email": (st.get("gabinete") or {}).get("email") if atual else None,
                "gabinete": (st.get("gabinete") or {}).get("nome") if atual else None,
                "atual": atual,
                "nasc": achado.get("dataNascimento"),
                "mandatos": [INICIO_LEG[l][:4] + "–" + str(int(INICIO_LEG[l][:4]) + 4) for l in legs],
            }
            desde = INICIO_LEG[legs[0]]
            props = paginar("%s/proposicoes?idDeputadoAutor=%d&dataApresentacaoInicio=%s&itens=100" % (API, dep_id, desde), limite=5000)
            info["proposicoes"] = len(props)
            info["propDesde"] = desde[:4]
            frentes = get_json("%s/deputados/%d/frentes" % (API, dep_id))
            info["frentes"] = len(frentes["dados"]) if frentes else None
            if atual:
                orgaos = get_json("%s/deputados/%d/orgaos?dataInicio=2026-01-01&itens=100" % (API, dep_id))
                if orgaos:
                    info["orgaos"] = sorted({(o.get("siglaOrgao") or o.get("nomeOrgao") or "") + (" (" + o["titulo"] + ")" if o.get("titulo") and o["titulo"] != "Titular" else "") for o in orgaos["dados"]})[:12]
                info["despesas"] = {}
                for ano in ANOS_DESPESA:
                    desp = paginar("%s/deputados/%d/despesas?ano=%d&itens=100" % (API, dep_id, ano), limite=5000)
                    total = round(sum(float(x.get("valorLiquido") or 0) for x in desp), 2)
                    if total > 0:
                        info["despesas"][str(ano)] = total
                if not info["despesas"]:   # a API tem devolvido vazio; a ficha mostra so o link "Gastos"
                    del info["despesas"]
            resultado[c["sq"]] = info
            time.sleep(0.3)
        sem = [det.get("ultimoStatus", {}).get("nome") for i, det in detalhes.items() if i not in usados]
        print("  deputados de %s sem candidatura em 2026: %d (%s)" % (uf, len(sem), ", ".join(sorted(filter(None, sem)))))
        if len(FALHAS) > n_falhas:
            incompletas.append(uf)
            print("  ATENCAO: %s ficou incompleta (%d consultas falharam) - rode de novo: --uf %s" % (uf, len(FALHAS) - n_falhas, uf))
        gravar(saida_p, resultado)   # grava a cada UF: uma queda no meio nao perde o que ja foi feito

    print("\nOK - %d deputados gravados em %s" % (len(resultado), saida_p))
    if incompletas:
        print("UFs INCOMPLETAS (API da Camara falhou): %s  ->  python scripts/fetch_camara.py --uf %s"
              % (", ".join(incompletas), ",".join(incompletas)))


if __name__ == "__main__":
    main()
