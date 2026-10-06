"""
Baixa os resultados oficiais da totalizacao das eleicoes 2026 (site de divulgacao do TSE).

Fonte: https://resultados.tse.jus.br/oficial/ele2026/<eleicao>/dados/<uf>/...
  <uf>-c<cargo>-e<eleicao>-u.json  resultado consolidado do cargo na UF (votos, situacao, QE, vagas por partido)
  <uf>-e<eleicao>-ab.json          comparecimento e abstencao por municipio
  config/mun-e<eleicao>-cm.json    municipios (codigo TSE x IBGE)
  <uf><mun>-c0001-e<eleicao>-u.json  Presidente em cada municipio, resumido em pres_mun.json
                                     (os dados abertos de 2026 por municipio ainda nao trazem Presidente)

Eleicoes (codigo do TSE, ver /oficial/comum/config/ele-c.json):
  1o turno: 6257 federal (Presidente)   6259 estadual (Governador, Senador, Dep. Federal, Estadual, Distrital)
  2o turno: 6258 federal                6260 estadual

Salva em raw/resultados2026/t<turno>/. O CDN do TSE bloqueia curl comum; usa curl_cffi (impersonate chrome).

Uso:
  python scripts/fetch_resultados.py              # 1o turno, todas as UFs
  python scripts/fetch_resultados.py --ufs RO,BR
  python scripts/fetch_resultados.py --turno 2
"""
import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(ROOT, "raw", "resultados2026")
BASE = "https://resultados.tse.jus.br/oficial/ele2026/"
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
ELEICOES = {1: {"federal": 6257, "estadual": 6259}, 2: {"federal": 6258, "estadual": 6260}}
# cargos da eleicao estadual em cada UF (DF tem Distrital no lugar de Estadual)
CARGOS_UF = {1: [3, 5, 6, 7], 2: [3]}


def cargos_da_uf(uf, turno):
    cs = list(CARGOS_UF[turno])
    if uf == "DF" and 7 in cs:
        cs[cs.index(7)] = 8
    return cs


class Cliente:
    def __init__(self):
        from curl_cffi import requests as cr  # noqa: PLC0415
        self._cr = cr
        self._local = threading.local()

    @property
    def s(self):
        # uma sessao por thread (downloads em paralelo)
        if not hasattr(self._local, "s"):
            self._local.s = self._cr.Session(impersonate="chrome")
        return self._local.s

    def get(self, url):
        """Devolve o conteudo (bytes) ou None se nao existir (404)."""
        for tentativa in range(5):
            try:
                r = self.s.get(url, timeout=60)
            except Exception as e:  # noqa: BLE001 - rede instavel: tenta de novo
                erro = e
            else:
                if r.status_code == 200:
                    return r.content
                if r.status_code == 404:
                    return None
                erro = "HTTP %d" % r.status_code
            time.sleep(2 * (tentativa + 1))
        raise IOError("%s: %s" % (url, erro))


def salvar(caminho, conteudo):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "wb") as f:
        f.write(conteudo)
    os.replace(tmp, caminho)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--turno", type=int, choices=(1, 2), default=1)
    ap.add_argument("--ufs", default="todas", help="ex.: RO,BR (BR = Presidente no Brasil) ou 'todas'")
    a = ap.parse_args()

    ufs = UFS + ["BR"] if a.ufs == "todas" else [u.strip().upper() for u in a.ufs.split(",") if u.strip()]
    ele = ELEICOES[a.turno]
    pasta = os.path.join(DESTINO, "t%d" % a.turno)
    cli = Cliente()
    pedidos = []
    for e in (ele["federal"], ele["estadual"]):
        pedidos.append(("config/mun-e%06d-cm.json" % e, "%d/config/mun-e%06d-cm.json" % (e, e)))
    for uf in ufs:
        u = uf.lower()
        if uf == "BR":
            e = ele["federal"]
            pedidos.append(("br-c0001-e%06d-u.json" % e, "%d/dados/br/br-c0001-e%06d-u.json" % (e, e)))
            pedidos.append(("zz-c0001-e%06d-u.json" % e, "%d/dados/zz/zz-c0001-e%06d-u.json" % (e, e)))
            continue
        e = ele["estadual"]
        for c in cargos_da_uf(uf, a.turno):
            pedidos.append(("%s-c%04d-e%06d-u.json" % (u, c, e), "%d/dados/%s/%s-c%04d-e%06d-u.json" % (e, u, u, c, e)))
        pedidos.append(("%s-e%06d-ab.json" % (u, e), "%d/dados/%s/%s-e%06d-ab.json" % (e, u, u, e)))
        f = ele["federal"]  # Presidente apurado na UF
        pedidos.append(("%s-c0001-e%06d-u.json" % (u, f), "%d/dados/%s/%s-c0001-e%06d-u.json" % (f, u, u, f)))

    ok = falta = 0
    for nome, caminho in pedidos:
        conteudo = cli.get(BASE + caminho)
        if conteudo is None:
            falta += 1
            print("  nao publicado:", nome)
            continue
        salvar(os.path.join(pasta, nome), conteudo)
        ok += 1
    if "BR" in ufs:
        presidente_por_municipio(cli, pasta, ele["federal"], None if a.ufs == "todas" or ufs == ["BR"] else ufs)
    print("Resultados %do turno: %d arquivos salvos em %s (%d nao publicados)" % (a.turno, ok, pasta, falta))
    with open(os.path.join(pasta, "_baixado.json"), "w", encoding="utf-8") as f:
        json.dump({"em": time.strftime("%Y-%m-%d %H:%M"), "arquivos": ok, "faltando": falta}, f)


def presidente_por_municipio(cli, pasta, eleicao, so_ufs):
    """Baixa o Presidente de cada municipio (inclusive exterior) e resume em pres_mun.json {codTSE: {...}}."""
    with open(os.path.join(pasta, "config", "mun-e%06d-cm.json" % eleicao), "rb") as f:
        doc = json.loads(f.read().decode("latin-1"))
    alvos = [(a["cd"], m["cd"]) for a in doc["abr"] for m in a.get("mu", [])
             if not so_ufs or a["cd"].upper() in so_ufs or a["cd"] == "zz"]
    saida = os.path.join(pasta, "pres_mun.json")
    feito = {}
    if os.path.exists(saida):
        with open(saida, encoding="utf-8") as f:
            feito = json.load(f)

    def um(alvo):
        uf, mun = alvo
        b = cli.get(BASE + "%d/dados/%s/%s%s-c0001-e%06d-u.json" % (eleicao, uf, uf, mun, eleicao))
        if b is None:
            return mun, None
        d = json.loads(b.decode("utf-8"))
        votos = {k["sqcand"]: int(k.get("vap") or 0) for a in d["carg"][0].get("agr", [])
                 for p in a["par"] for k in p.get("cand", [])}
        return mun, {"uf": uf.upper(), "v": votos, "dg": d.get("dg"), "tf": d.get("tf")}

    # incremental: so baixa de novo o que ainda nao estava totalizado
    pendentes = [t for t in alvos if t[1] not in feito or feito[t[1]].get("tf") != "s"]
    print("  Presidente por municipio: %d de %d a baixar" % (len(pendentes), len(alvos)))
    with ThreadPoolExecutor(max_workers=8) as ex:
        for mun, r in ex.map(um, pendentes):
            if r:
                feito[mun] = r
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(feito, f, separators=(",", ":"))
    print("  %d municipios em pres_mun.json" % len(feito))


if __name__ == "__main__":
    main()
