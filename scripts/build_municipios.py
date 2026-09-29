# -*- coding: utf-8 -*-
"""
build_municipios.py - lista oficial de municipios por UF (raw/municipio_tse_ibge.zip, do TSE) -> data/municipios.js,
usada pelo seletor de municipio da aba Perfil. Somente stdlib, alguns segundos. Rode de novo se o arquivo do TSE mudar.

Uso:
    python scripts/build_municipios.py
"""
import collections
import csv
import io
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    z = zipfile.ZipFile(os.path.join(ROOT, "raw", "municipio_tse_ibge.zip"))
    por_uf = collections.defaultdict(set)
    for r in csv.DictReader(io.TextIOWrapper(z.open("municipio_tse_ibge.csv"), encoding="latin-1"), delimiter=";"):
        por_uf[r["SG_UF"]].add(r["NM_MUNICIPIO_TSE"].strip())
    saida = {uf: sorted(ms, key=lambda m: m.lower()) for uf, ms in sorted(por_uf.items())}
    out = os.path.join(ROOT, "data", "municipios.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.MUNICIPIOS=")
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("OK - %s (%d UFs, %d municipios, %.0f KB)" % (out, len(saida), sum(map(len, saida.values())), os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
