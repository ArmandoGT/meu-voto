# -*- coding: utf-8 -*-
"""
fetch_votacoes_federais.py - votacoes NOMINAIS na Camara dos Deputados e no Senado dos candidatos de 2026 de RO
que sao ou ja foram deputados federais / senadores. Grava data/votacoes_federais.js.

Precisa de internet. Somente stdlib. ~15 min (a Camara publica ~60 MB de CSV por ano; o script le direto da
internet, linha a linha, e guarda so os votos dos candidatos de RO - nada de 500 MB em disco).

Uso:
    python scripts/fetch_votacoes_federais.py                  # 2015-2026 (legislaturas 55, 56 e 57)
    python scripts/fetch_votacoes_federais.py --desde 2023     # so a legislatura atual (mais rapido)

Fontes:
    Camara: arquivos anuais de dados abertos (dadosabertos.camara.leg.br/arquivos): votacoes-ANO.csv (data, orgao,
            descricao, placar), votacoesVotos-ANO.csv (voto de cada deputado), votacoesProposicoes-ANO.csv (projeto).
            Deputado -> candidato: data/camara.js (ja casado por data de nascimento em fetch_camara.py).
    Senado: https://legis.senado.leg.br/dadosabertos/votacao?dataInicio=..&dataFim=.. (todas as votacoes do ano, com
            os votos). Senador -> candidato: raw/senado_senadores.json (lista oficial com nascimento, baixada por
            fetch_emendas.py) + data de nascimento (+-1 dia) + nome civil quase igual (regra de fetch_alero.py).

Neutralidade: o voto vai com o rotulo oficial da Casa (Sim, Nao, Abstencao, Obstrucao, "Votou" em votacao secreta,
licencas e ausencias do Senado...). Nenhum voto e classificado como bom ou ruim.
"""
import collections
import csv
import datetime
import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_alero import nome_quase_igual  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(ROOT, "raw")
UF = "RO"
CAMARA_ARQ = "https://dadosabertos.camara.leg.br/arquivos/%s/csv/%s-%d.csv"
SENADO = "https://legis.senado.leg.br/dadosabertos/votacao?dataInicio=%d-01-01&dataFim=%d-12-31"
UA = {"User-Agent": "MeuVoto2026/1.0"}

# rotulos oficiais do Senado (siglaVotoParlamentar) por extenso
SENADO_ROT = {"P-NRV": "Presente, não registrou voto", "AP": "Ausente em atividade parlamentar", "MIS": "Ausente em missão",
              "LS": "Licença saúde", "LP": "Licença particular", "LA": "Licença", "NCom": "Não compareceu",
              "NA": "Não apurado", "Votou": "Votou (voto secreto)", "P-OD": "Obstrução", "REP": "Representação da Casa",
              "LAP": "Licença-maternidade/paternidade", "AUS": "Ausente"}


def ler(p):
    t = open(p, encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))


def abrir(url, tentativas=4):
    for i in range(tentativas):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300)
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == 404 or i == tentativas - 1:
                raise
            time.sleep(2 ** (i + 2))


def tentar(fn, rotulo, tentativas=4):
    """Repete a leitura INTEIRA (a conexao as vezes cai no meio do arquivo: IncompleteRead)."""
    for i in range(tentativas):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                raise SystemExit("Falhou %s depois de %d tentativas: %s - rode de novo mais tarde." % (rotulo, tentativas, e))
            print("    %s: %s - tentando de novo" % (rotulo, e.__class__.__name__))
            time.sleep(2 ** (i + 2))


def csv_remoto(url):
    """Le um CSV da Camara direto da internet, linha a linha (separador ';', UTF-8 com BOM)."""
    r = abrir(url)
    return csv.DictReader(io.TextIOWrapper(r, encoding="utf-8-sig", newline=""), delimiter=";")


def camara(anos, cands):
    cam = ler(os.path.join(DATA, "camara.js"))
    dep_sq = {str(info["id"]): sq for sq, info in cam.items() if sq in cands}
    print("Camara: %d candidatos de %s sao ou foram deputados federais" % (len(dep_sq), UF))
    vot = {}
    for ano in anos:
        t0 = time.time()

        def ler_votos():
            vs, n = collections.defaultdict(dict), 0
            for row in csv_remoto(CAMARA_ARQ % ("votacoesVotos", "votacoesVotos", ano)):
                n += 1
                if row["deputado_id"] in dep_sq:
                    vs[row["idVotacao"]][row["deputado_id"]] = row["voto"] or "Sem registro"
            return vs, n
        votos, n = tentar(ler_votos, "votos da Camara %d" % ano)

        def ler_props():
            ps = {}
            for row in csv_remoto(CAMARA_ARQ % ("votacoesProposicoes", "votacoesProposicoes", ano)):
                if row["idVotacao"] in votos and row["idVotacao"] not in ps:
                    ps[row["idVotacao"]] = row
            return ps
        props = tentar(ler_props, "proposicoes da Camara %d" % ano)
        linhas = tentar(lambda: [row for row in csv_remoto(CAMARA_ARQ % ("votacoes", "votacoes", ano)) if row["id"] in votos], "votacoes da Camara %d" % ano)
        novas = 0
        for row in linhas:
            vid = row["id"]
            if vid not in votos:
                continue
            p = props.get(vid) or {}
            ap = row.get("aprovacao")
            vot[vid] = {
                "id": vid, "d": row["data"], "org": row["siglaOrgao"],
                "t": p.get("proposicao_siglaTipo") or None, "n": int(p["proposicao_numero"]) if (p.get("proposicao_numero") or "").isdigit() else None,
                "a": int(p["proposicao_ano"]) if (p.get("proposicao_ano") or "").isdigit() else None,
                "m": p.get("proposicao_id") or None,
                "e": " ".join((p.get("proposicao_ementa") or "").split()), "desc": " ".join((row.get("descricao") or "").split()),
                "r": "Aprovada" if ap == "1" else "Rejeitada" if ap == "0" else "",
                "sim": int(row["votosSim"] or 0), "nao": int(row["votosNao"] or 0), "outros": int(row["votosOutros"] or 0),
                "v": votos[vid],
            }
            novas += 1
        print("  %d: %d votos lidos, %d votacoes com candidato de %s (%.0f s)" % (ano, n, novas, UF, time.time() - t0))
    lista = sorted(vot.values(), key=lambda x: (x["d"], x["id"]), reverse=True)
    parl = {d: {"n": cam[sq]["nomeParlamentar"], "sq": sq} for d, sq in dep_sq.items() if any(d in x["v"] for x in lista)}
    return {"parl": parl, "porCand": {v["sq"]: d for d, v in parl.items()}, "vot": lista,
            "ultimaVotacao": lista[0]["d"] if lista else None, "desde": str(anos[0])}


def senado(anos, cands):
    sen = json.load(open(os.path.join(RAW, "senado_senadores.json"), encoding="utf-8"))
    cod_sq = {}
    for c in cands.values():
        try:
            dc = datetime.datetime.strptime(c.get("nasc") or "", "%d/%m/%Y").date()
        except ValueError:
            continue
        for cod, s in sen.items():
            if not s.get("nasc"):
                continue
            if abs((datetime.date.fromisoformat(s["nasc"]) - dc).days) <= 1 and nome_quase_igual(s.get("nomeCompleto") or s["nome"], c["nome"]):
                if cod in cod_sq and cod_sq[cod] != c["sq"]:
                    print("  AVISO: senador %s bate com dois candidatos - nao casado" % s["nome"])
                    cod_sq[cod] = None
                elif cod not in cod_sq:
                    cod_sq[cod] = c["sq"]
                    print("  senador %s (%s) -> %s (%s, %s)" % (s["nome"], s.get("nomeCompleto"), c["urna"], c["nome"], c["cargo"]))
    cod_sq = {k: v for k, v in cod_sq.items() if v}
    print("Senado: %d candidatos de %s sao ou foram senadores (titulares ou suplentes)" % (len(cod_sq), UF))
    lista = []
    for ano in anos:
        def ler_ano():
            with urllib.request.urlopen(urllib.request.Request(SENADO % (ano, ano), headers=dict(UA, Accept="application/json")), timeout=300) as r:
                return json.load(r)
        dados = tentar(ler_ano, "Senado %d" % ano)
        n = 0
        for x in dados:
            vs = {str(v["codigoParlamentar"]): v.get("siglaVotoParlamentar") or "" for v in x.get("votos") or [] if str(v.get("codigoParlamentar")) in cod_sq}
            if not vs:
                continue
            n += 1
            lista.append({
                "id": x["codigoSessaoVotacao"], "d": x.get("dataSessao"), "t": x.get("sigla"), "n": int(x["numero"]) if str(x.get("numero") or "").isdigit() else None,
                "a": x.get("ano"), "m": x.get("codigoMateria"), "ident": x.get("identificacao"),
                "e": " ".join((x.get("ementa") or "").split()), "desc": " ".join((x.get("descricaoVotacao") or "").split()),
                "r": {"A": "Aprovada", "R": "Rejeitada"}.get(x.get("resultadoVotacao"), x.get("resultadoVotacao") or ""),
                "secreta": x.get("votacaoSecreta") == "S",
                "sim": x.get("totalVotosSim"), "nao": x.get("totalVotosNao"), "abs": x.get("totalVotosAbstencao"),
                "v": {k: SENADO_ROT.get(v, v) or "Sem registro" for k, v in vs.items()},
            })
        print("  %d: %d votacoes do Senado, %d com candidato de %s" % (ano, len(dados), n, UF))
        time.sleep(0.5)
    lista.sort(key=lambda x: (x["d"] or "", x["id"]), reverse=True)
    parl = {cod: {"n": sen[cod]["nome"], "sq": sq} for cod, sq in cod_sq.items() if any(cod in x["v"] for x in lista)}
    return {"parl": parl, "porCand": {v["sq"]: c for c, v in parl.items()}, "vot": lista,
            "ultimaVotacao": lista[0]["d"] if lista else None, "desde": str(anos[0])}


def main():
    desde = int(sys.argv[sys.argv.index("--desde") + 1]) if "--desde" in sys.argv else 2015
    anos = list(range(desde, datetime.date.today().year + 1))
    cands = {c["sq"]: c for c in ler(os.path.join(DATA, "cand_%s.js" % UF))}
    t0 = time.time()
    saida = {"atualizado": datetime.date.today().isoformat(), "uf": UF, "camara": camara(anos, cands), "senado": senado(anos, cands)}
    out = os.path.join(DATA, "votacoes_federais.js")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.VOTFED=")
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    os.replace(tmp, out)
    print("\nOK - %s (%.1f MB) em %.0f min" % (out, os.path.getsize(out) / 1048576, (time.time() - t0) / 60))
    for casa in ("camara", "senado"):
        C = saida[casa]
        print("  %s: %d votacoes nominais com candidato de %s (ultima %s)" % (casa, len(C["vot"]), UF, C["ultimaVotacao"]))
        for pid, p in sorted(C["parl"].items(), key=lambda x: x[1]["n"]):
            c = cands[p["sq"]]
            rot = collections.Counter(x["v"][pid] for x in C["vot"] if pid in x["v"])
            print("    %-24s -> %-22s %-18s %5d votos  %s" % (p["n"], c["urna"], c["cargo"], sum(rot.values()), dict(rot.most_common(4))))


if __name__ == "__main__":
    main()
