# -*- coding: utf-8 -*-
"""
build_mobile.py - gera UM arquivo HTML autocontido (mobile/meu-voto-mobile.html) com TODAS as
funcionalidades do sistema (pesquisa, ficha completa, criterios, ranking, escolhas, colinha para
imprimir/compartilhar, denuncias, fontes externas, dados da Camara, emendas parlamentares, votacoes da ALE-RO), para abrir no celular sem internet.

Uso:
    python scripts/build_mobile.py               # UF de foco (RO) + presidente, com fotos  (~4,5 MB)
    python scripts/build_mobile.py --todas       # + todos os outros estados, carregados sob demanda (~45 MB)
    python scripts/build_mobile.py --uf MT       # outra UF de foco
    python scripts/build_mobile.py --sem-fotos   # sem fotos (~1 MB)

Como funciona:
  * CSS, JS e dados ficam dentro do HTML. A UF de foco e o presidente entram como variaveis JS (uso
    imediato); com --todas, cada outra UF entra como <script type="application/json"> e so e parseada
    quando o usuario a seleciona na pesquisa.
  * Fotos entram em base64 (so das UFs de foco; as outras UFs nao tem foto baixada).
  * PDFs (certidoes e planos de governo) nao cabem no arquivo: a ficha mostra um link para os mesmos
    documentos no DivulgaCandContas (TSE), que abre quando houver internet.
  * Favoritos/notas/tags/criterios/escolhas ficam no navegador do celular; Exportar/Importar usa o
    mesmo JSON do computador.
Rode de novo depois de cada build_data.py / fetch_camara.py / fetch_emendas.py / fetch_alero.py / fetch_votacoes_federais.py.
"""
import argparse
import base64
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "mobile")


def ler(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()


def ler_js_var(p):
    txt = open(p, encoding="utf-8").read()
    return json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def js_var(nome, obj):
    return "window.%s=%s;" % (nome, dumps(obj))


def json_tag(id_, obj):
    # "</script" dentro de dados fecharia a tag; escapa a barra
    return '<script type="application/json" id="%s">%s</script>' % (id_, dumps(obj).replace("</", "<\\/"))


def miolo_id(html, id_tela):
    """Extrai <section class="tela..." id="X"> ... </section> (a secao termina antes da proxima <section class="tela" ou de </main>)."""
    m = re.search(r'(<section class="tela[^"]*" id="%s">.*?</section>)\s*(?=<section class="tela|</main>)' % id_tela, html, re.S)
    if not m:
        raise SystemExit("nao achei a secao %s" % id_tela)
    return m.group(1)


def miolo(html, id_tela):
    m = re.search(r'(<section class="tela[^"]*" id="%s">.*?</section>)\s*</main>' % id_tela, html, re.S)
    if not m:
        raise SystemExit("nao achei a secao %s" % id_tela)
    return m.group(1)


def foto_uri(caminho):
    p = os.path.join(ROOT, caminho)
    if not os.path.exists(p):
        return None
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:%s;base64,%s" % (mime, base64.b64encode(open(p, "rb").read()).decode("ascii"))


def preparar(lista, com_fotos, stats):
    """Troca PDFs por flag online, embute fotos em base64."""
    for c in lista:
        docs = {}
        cert = c.pop("certidoes", None)
        if cert:
            docs["certidoes"] = len(cert)
        if c.pop("propostas", None):
            docs["propostas"] = True
        for mbr in c.get("chapa", []):
            cert_m = mbr.pop("certidoes", None)
            if cert_m:
                docs["certidoes"] = docs.get("certidoes", 0) + len(cert_m)
        if docs:
            c["docsOnline"] = docs
        for obj in [c] + c.get("chapa", []):
            if obj.get("foto"):
                uri = foto_uri(obj["foto"]) if com_fotos else None
                if uri:
                    obj["foto"] = uri
                    stats["fotos"] += 1
                else:
                    obj.pop("foto", None)
    return lista


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="RO")
    ap.add_argument("--todas", action="store_true", help="embute todas as UFs (carregadas sob demanda)")
    ap.add_argument("--sem-fotos", action="store_true")
    args = ap.parse_args()
    uf = args.uf.upper()

    manifest = ler_js_var(os.path.join(DATA, "manifest.js"))
    foco = [u for u in (uf, "BR") if u in manifest["ufs"]]
    todas = manifest["ufs"] if args.todas else foco
    manifest_m = dict(manifest)
    manifest_m["ufs"] = todas
    manifest_m["contagens"] = {u: manifest["contagens"][u] for u in todas}
    manifest_m["vagas"] = {u: v for u, v in manifest.get("vagas", {}).items() if u in todas}
    manifest_m["mobile"] = True

    stats = {"fotos": 0}
    dados_js = [js_var("MANIFEST", manifest_m)]
    json_tags = []
    for u in todas:
        lista = preparar(ler_js_var(os.path.join(DATA, "cand_%s.js" % u)), not args.sem_fotos and u in foco, stats)
        if u in foco:
            dados_js.append(js_var("CAND_" + u, lista))
        else:
            json_tags.append(json_tag("cand-" + u, lista))
    # resultados da eleicao (opcionais): JSON lido so quando a tela Resultados ou a ficha precisam
    n_res = 0
    for u in todas:
        res_p = os.path.join(DATA, "resultados_%s.js" % u)
        if os.path.exists(res_p):
            json_tags.append(json_tag("res-" + u, ler_js_var(res_p)))
            n_res += 1
    cam_p = os.path.join(DATA, "camara.js")
    if os.path.exists(cam_p):
        dados_js.append(js_var("CAMARA", ler_js_var(cam_p)))
    em_p = os.path.join(DATA, "emendas.js")
    if os.path.exists(em_p):
        em = ler_js_var(em_p)
        sqs = set()
        for u in todas:
            sqs.update(c["sq"] for c in ler_js_var(os.path.join(DATA, "cand_%s.js" % u)))
        em["porCand"] = {sq: v for sq, v in em["porCand"].items() if sq in sqs}
        em["porMun"] = {k: v for k, v in em["porMun"].items() if k.split("|")[0] in foco}
        em.pop("naoCasados", None)
        dados_js.append(js_var("EMENDAS", em))
    al_p = os.path.join(DATA, "alero.js")
    if os.path.exists(al_p):
        dados_js.append(js_var("ALERO", ler_js_var(al_p)))
    vf_p = os.path.join(DATA, "votacoes_federais.js")
    if os.path.exists(vf_p):
        dados_js.append(js_var("VOTFED", ler_js_var(vf_p)))
    mu_p = os.path.join(DATA, "municipios.js")
    if os.path.exists(mu_p):
        dados_js.append(js_var("MUNICIPIOS", ler_js_var(mu_p)))
    den_p = os.path.join(DATA, "denuncias.js")
    if os.path.exists(den_p):
        den = ler_js_var(den_p)
        dados_js.append(js_var("DENUNCIAS", {u: den[u] for u in todas if u in den}))

    css = ler("assets/styles.css")
    app = ler("assets/app.js")
    busca = ler("assets/busca.js")
    voto = ler("assets/meu-voto.js")
    emendas = ler("assets/emendas.js")
    votacoes = ler("assets/votacoes.js")
    coligacoes = ler("assets/coligacoes.js")
    resultados = ler("assets/resultados.js")
    tela_resultados = miolo(ler("resultados.html"), "tela-resultados").replace('class="tela ativa"', 'class="tela"')
    tela_coligacoes = miolo(ler("coligacoes.html"), "tela-coligacoes").replace('class="tela ativa"', 'class="tela"')
    tela_votacoes = miolo(ler("votacoes.html"), "tela-votacoes").replace('class="tela ativa"', 'class="tela"')
    tela_emendas = miolo(ler("emendas.html"), "tela-emendas").replace('class="tela ativa"', 'class="tela"')
    pagina_voto = ler("meu-voto.html")
    tela_busca = miolo(ler("index.html"), "tela-busca")
    tela_voto = miolo_id(pagina_voto, "tela-voto").replace('class="tela ativa"', 'class="tela"')
    tela_cola = miolo_id(pagina_voto, "tela-cola")
    tela_perfil = miolo_id(pagina_voto, "tela-perfil")
    tela_mais = miolo_id(pagina_voto, "tela-mais")
    perfil_js = ler("assets/perfil.js")

    nl = chr(10)
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#1d4ed8">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Meu Voto 2026 — {uf}</title>
<style>
{css}
</style>
<script>
{nl.join(dados_js)}
</script>
{nl.join(json_tags)}
</head>
<body class="mobile">
<main class="wrap" id="conteudo">
{tela_busca}
{tela_voto}
{tela_cola}
{tela_emendas}
{tela_votacoes}
{tela_coligacoes}
{tela_resultados}
{tela_perfil}
{tela_mais}
</main>
<div id="colinha-print" aria-hidden="true"></div>
<script>
{app}
</script>
<script>
{busca}
</script>
<script>
{voto}
</script>
<script>
{emendas}
</script>
<script>
{votacoes}
</script>
<script>
{coligacoes}
</script>
<script>
{resultados}
</script>
<script>
{perfil_js}
</script>
</body>
</html>
"""
    os.makedirs(OUT_DIR, exist_ok=True)
    nome = "meu-voto-mobile%s%s.html" % ("" if uf == "RO" else "-" + uf, "-brasil" if args.todas else "")
    out = os.path.join(OUT_DIR, nome)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK - %s (%.1f MB, %d UFs, %d fotos embutidas, resultados de %d UFs)" % (out, os.path.getsize(out) / 1048576, len(todas), stats["fotos"], n_res))


if __name__ == "__main__":
    main()
