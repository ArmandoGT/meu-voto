# -*- coding: utf-8 -*-
"""
build_mapas.py - contorno dos municipios de cada UF (malha do IBGE) -> data/mapa_XX.js, usado no mapa
"mais votado por cidade" da tela Resultados.

Fonte: API de malhas do IBGE (qualidade minima, ja simplificada)
  https://servicodados.ibge.gov.br/api/v3/malhas/estados/<UF>?intrarregiao=municipio&qualidade=minima&formato=application/vnd.geo+json
Os GeoJSON ficam em raw/malhas/<UF>.json (baixados uma vez; --baixar forca de novo).
O codigo IBGE de cada municipio vira o codigo TSE pela tabela raw/municipio_tse_ibge.zip (o mesmo dos resultados).

Saida: window.MAPA_XX = {"vb": "0 0 L A", "m": {"<codTSE>": "M..Z"}} - caminhos SVG ja projetados
(equiretangular com correcao pelo cosseno da latitude media da UF), em coordenadas inteiras.
Somente stdlib.

Uso:
    python scripts/build_mapas.py               # todas as UFs
    python scripts/build_mapas.py --ufs RO,AC
"""
import argparse
import csv
import gzip
import io
import json
import math
import os
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw", "malhas")
DATA = os.path.join(ROOT, "data")
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/%s?intrarregiao=municipio&qualidade=minima&formato=application/vnd.geo+json"
LARGURA = 1000  # largura do viewBox; a altura segue a proporcao da UF


def baixar(uf, forcar):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, uf + ".json")
    if os.path.exists(p) and not forcar:
        return p
    req = urllib.request.Request(URL % uf, headers={"User-Agent": "meu-voto-2026 (uso pessoal)", "Accept": "application/json"})
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                dados = r.read()
            if dados[:2] == bytes([0x1F, 0x8B]):  # o IBGE responde em gzip mesmo sem pedir
                dados = gzip.decompress(dados)
            json.loads(dados)  # valida antes de gravar
            with open(p, "wb") as f:
                f.write(dados)
            return p
        except Exception as e:  # noqa: BLE001
            if tentativa == 3:
                print("  %s: falhou (%s)" % (uf, e))
                return None
            time.sleep(2 + 3 * tentativa)


def tabela_ibge_tse():
    z = zipfile.ZipFile(os.path.join(ROOT, "raw", "municipio_tse_ibge.zip"))
    t = {}
    for r in csv.DictReader(io.TextIOWrapper(z.open("municipio_tse_ibge.csv"), encoding="latin-1"), delimiter=";"):
        if r["CD_MUNICIPIO_IBGE"]:
            t[r["CD_MUNICIPIO_IBGE"].strip()] = r["CD_MUNICIPIO_TSE"].strip().zfill(5)
    return t


def aneis(geom):
    if geom["type"] == "Polygon":
        return list(geom["coordinates"])
    if geom["type"] == "MultiPolygon":
        return [a for pol in geom["coordinates"] for a in pol]
    return []


def gerar(uf, p, ibge_tse):
    gj = json.load(open(p, encoding="utf-8"))
    feats = gj.get("features", [])
    pts = [pt for f in feats for a in aneis(f["geometry"]) for pt in a]
    if not pts:
        return None
    x0 = min(p_[0] for p_ in pts); x1 = max(p_[0] for p_ in pts)
    y0 = min(p_[1] for p_ in pts); y1 = max(p_[1] for p_ in pts)
    k = math.cos(math.radians((y0 + y1) / 2))
    esc = LARGURA / ((x1 - x0) * k)
    altura = int(math.ceil((y1 - y0) * esc))
    m, sem = {}, 0
    for f in feats:
        cod = str(f.get("properties", {}).get("codarea", ""))
        tse = ibge_tse.get(cod)
        if not tse:
            sem += 1
            continue
        partes = []
        for a in aneis(f["geometry"]):
            ult, seg = None, []
            for lon, lat in a:
                q = (round((lon - x0) * k * esc), round((y1 - lat) * esc))
                if q != ult:
                    seg.append(q); ult = q
            if len(seg) < 3:
                continue
            # 1o ponto absoluto, os demais relativos (caminho menor)
            d = "M%d %d" % seg[0]
            for (ax, ay), (bx, by) in zip(seg, seg[1:]):
                d += "l%d %d" % (bx - ax, by - ay)
            partes.append(d + "z")
        if partes:
            m[tse] = "".join(partes)
    if sem:
        print("  %s: %d municipio(s) sem codigo TSE" % (uf, sem))
    return {"vb": "0 0 %d %d" % (LARGURA, altura), "m": m}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ufs", default=",".join(UFS))
    ap.add_argument("--baixar", action="store_true", help="baixa de novo mesmo se ja existir em raw/malhas")
    args = ap.parse_args()
    ibge_tse = tabela_ibge_tse()
    total = 0
    for uf in [u.strip().upper() for u in args.ufs.split(",") if u.strip()]:
        p = baixar(uf, args.baixar)
        if not p:
            continue
        mapa = gerar(uf, p, ibge_tse)
        if not mapa:
            print("  %s: malha vazia" % uf)
            continue
        out = os.path.join(DATA, "mapa_%s.js" % uf)
        with open(out, "w", encoding="utf-8") as f:
            f.write("window.MAPA_%s=" % uf)
            json.dump(mapa, f, separators=(",", ":"))
            f.write(";\n")
        total += os.path.getsize(out)
        print("  %s: %d municipios, %.0f KB" % (uf, len(mapa["m"]), os.path.getsize(out) / 1024))
    print("OK - data/mapa_XX.js (%.0f KB no total)" % (total / 1024))


if __name__ == "__main__":
    main()
