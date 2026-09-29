# -*- coding: utf-8 -*-
"""
fetch_alero_atas.py - baixa as ATAS das sessoes plenarias da ALE-RO (SAPL) desde 01/02/2023, extrai o texto
(OCR quando o PDF e escaneado) e lista os trechos em que um deputado registra posicao individual sobre uma votacao
simbolica (declaracao de voto, voto contrario, abstencao, "que conste em ata"...).

O script NAO cadastra nada sozinho: gera logs/atas_trechos.md para conferencia humana. O que for confirmado na
ata vira uma entrada em data/alero_declaracoes.json (com folha e link), e o fetch_alero.py --sem-baixar publica.

Uso:
    python scripts/fetch_alero_atas.py              # baixa o que falta, extrai texto/OCR e gera o relatorio
    python scripts/fetch_alero_atas.py --so-busca   # so refaz a busca nos textos ja extraidos (segundos)

Cache: raw/alero_atas/<id da sessao>.pdf e .txt (o .txt marca as paginas com "=== folha N ===").
OCR: Windows.Media.Ocr (nativo do Windows, pt-BR) via scripts/ocr_windows.ps1 - sem instalar nada.
"""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_alero import API, DESDE, RAW, ROOT, paginar, sem_acento  # noqa: E402

PASTA = os.path.join(RAW, "alero_atas")
RELATORIO = os.path.join(ROOT, "logs", "atas_trechos.md")
OCR_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_windows.ps1")

# expressoes de posicao individual numa votacao (texto sem acento, minusculo)
PADROES = [
    r"declara\w* (de |o )?(seu )?voto", r"voto contrari", r"votou contra", r"voto (e |foi )?(pela|a favor|favoravel|contra|nao)",
    r"meu voto", r"voto nao", r"votar contra", r"votarei contra", r"abst(en|ev|er)\w*", r"conste (em|na|da) ata",
    r"registr\w+ (em|na) ata", r"consign\w+ (em|na) ata", r"nao participou da votacao", r"nao (vot|particip)\w+",
    r"contrari\w+ (a|ao) (projeto|materia|veto|emenda|proposta)", r"encaminh\w+ (o )?voto", r"votos? contrarios?",
]
RE_POS = re.compile("|".join("(?:%s)" % p for p in PADROES))


def baixar_pdf(s):
    destino = os.path.join(PASTA, "%d.pdf" % s["id"])
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return
    url = s["upload_ata"].replace("http://", "https://")
    req = urllib.request.Request(url, headers={"User-Agent": "MeuVoto2026/1.0"})
    for i in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                dados = r.read()
            with open(destino + ".tmp", "wb") as f:
                f.write(dados)
            os.replace(destino + ".tmp", destino)
            return
        except Exception as e:  # noqa: BLE001
            if i == 4:
                print("  FALHA ao baixar a ata da sessao %d: %s" % (s["id"], e))
            time.sleep(2 ** (i + 1))


def extrair(sid):
    """Texto por folha. Usa a camada de texto do PDF; folha sem texto vai para o OCR do Windows."""
    import pymupdf
    pdf = os.path.join(PASTA, "%d.pdf" % sid)
    txt = os.path.join(PASTA, "%d.txt" % sid)
    if os.path.exists(txt) or not os.path.exists(pdf):
        return
    partes, ocr = [], 0
    with pymupdf.open(pdf) as doc:
        for i, pg in enumerate(doc):
            t = pg.get_text()
            if len(t.strip()) < 80:
                png = os.path.join(PASTA, "_%d_%d.png" % (sid, i))
                pg.get_pixmap(dpi=300).save(png)
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1, png],
                                   capture_output=True, timeout=180)
                os.remove(png)
                t = r.stdout.decode("utf-8", "replace")
                ocr += 1
            partes.append("=== folha %d ===\n%s" % (i + 1, t))
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))
    return ocr


def buscar(sessoes):
    linhas = ["# Trechos das atas da ALE-RO com posicao individual em votacao",
              "", "Gerado por scripts/fetch_alero_atas.py. So para conferencia: confirme na ata antes de cadastrar em "
              "data/alero_declaracoes.json.", ""]
    n = 0
    for s in sorted(sessoes, key=lambda s: (s["data_inicio"], s["id"])):
        p = os.path.join(PASTA, "%d.txt" % s["id"])
        if not os.path.exists(p):
            continue
        texto = open(p, encoding="utf-8").read()
        folha, achados = 1, []
        plano = sem_acento(texto).lower()
        for m in RE_POS.finditer(plano):
            folha = plano.count("=== folha ", 0, m.start())
            ini, fim = max(0, m.start() - 450), min(len(texto), m.end() + 450)
            achados.append((folha, " ".join(texto[ini:fim].split())))
        if achados:
            linhas.append("## %s - %s (sessao %d)" % (s["data_inicio"], s["__str__"], s["id"]))
            linhas.append(s["upload_ata"])
            linhas.append("")
            ult = None
            for folha, trecho in achados:
                if trecho[:200] == ult:
                    continue
                ult = trecho[:200]
                linhas.append("- folha %d: %s" % (folha, trecho))
                n += 1
            linhas.append("")
    os.makedirs(os.path.dirname(RELATORIO), exist_ok=True)
    with open(RELATORIO, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    print("OK - %d trechos em %s" % (n, RELATORIO))


# deputados da 11a legislatura: palavra que identifica cada um no texto da ata (sem acento, maiusculo) -> id no SAPL
CHAVES_DEP = {
    "CAMARGO": "291", "DELEGADO LUCAS": "290", "DEP. LUCAS": "290", "DEPUTADO LUCAS": "290", "TAISSA": "293",
    "GOEBEL": "273", "EYDER": "261", "CRISPIN": "265", "CRI SPIN": "265", "CLAUDIA DE JESUS": "289",
    "MARCELO CRUZ": "274", "BOABAID": "243", "BOUABAID": "243", "REDANO": "256", "DEIRO": "260", "NEIVA": "264",
    "JEAN OLIVEIRA": "267", "LAERTE": "271", "DONADON": "276", "QUEIROZ": "277", "JEAN MENDONCA": "281",
    "AFFONSO": "287", "GOIS": "288", "HOSPITAL": "292", "EDEVALDO": "294", "LEBRINHA": "295", "IEDA": "296",
    "BARROSO": "297", "PEDRO FERNANDES": "298", "SINPOL": "299",
}
RE_MAT = re.compile(r"(PROJ ?ETO[ .]*DE[ .]*LEI(?:[ .]*COMPLEMENTAR|[ .]*ORDINARIA)?|PROPOSTA DE EMENDA (?:CONSTITUCIONAL|A CONSTITUICAO))"
                    r"[\s,.]*(?:N\s?[O0º°]?\.?\s*)?(\d[\d.]*)\s*/\s*(\d{4})")
# outras proposicoes: servem so para cortar o trecho da materia anterior (a posicao pode ser sobre elas)
RE_OUTRA = re.compile(r"PROJETO DE (?:RESOLUCAO|DECRETO|COMPLEMENTAR)|REQUERIMENTO|VETO (?:TOTAL|PARCIAL)|INDICACAO|MOCAO")
# cabecalho de cada folha ("=== folha 5 === ESTADO DE RONDONIA ... ATA N 122 23 DE MAIO DE 2024 5"): parte frases ao meio
RE_CABEC = re.compile(r"=== folha (\d+) ===.{0,300}?(?:19|20)\d\d\s+(?:FL\.?\s*|Fla\s*)?\d{1,2}\b", re.S | re.I)
# materia errada por causa do OCR (conferido na ata): (sessao, tipo, numero, ano) lido -> o certo
# 1578: o OCR embaralhou as colunas da folha 2; o voto contrario e ao credito de R$ 20 mi para o CBM (PL 804/2025)
CORRECOES = {(1578, "PL", 619, 2024): ("PL", 804, 2025)}
# posicao depois do nome ("o Deputado X se absteve") ou antes ("abstencao do Deputado X", "votos contrarios dos Deputados X e Y")
RE_DEPOIS = re.compile(r"(SE ABSTEVE|VOTOU CONTRA|MANIFESTOU VOTO CONTRARIO|VOTOU NAO|VOTARAM CONTRA)")
RE_ANTES = re.compile(r"(ABST\w*N[CÇ]AO(?: D[OA]S?)?|VOTOS? CONTRARIOS? D[OA]S?|REGISTRO DO VOTO CONTRARIO D[EOA]S?|VOTO NAO D[OA]S?)")


def deputados_em(trecho):
    achados = []
    for chave, pid in CHAVES_DEP.items():
        for m in re.finditer(r"\b%s\b" % re.escape(chave), trecho):
            achados.append((m.start(), pid))
    return [pid for _, pid in sorted(achados)]


def posicoes(sessoes, leis):
    """Para cada ata: materia (PL/PLC/PEC n/ano) -> deputados citados como abstencao ou voto contrario.
    So entra o que for de uma lei da lista (fetch_alero.py) - o resto (decreto legislativo, resolucao) fica no log."""
    por_chave = {(l["t"], int(l["n"]), int(l["a"])): l for l in leis}
    saida = []
    for s in sorted(sessoes, key=lambda s: (s["data_inicio"], s["id"])):
        p = os.path.join(PASTA, "%d.txt" % s["id"])
        if not os.path.exists(p):
            continue
        orig = RE_CABEC.sub(lambda m: " [[FOLHA %s]] " % m.group(1), open(p, encoding="utf-8").read())
        orig = " ".join(orig.split())
        up = sem_acento(orig).upper()
        if len(up) != len(orig):   # o texto mostrado precisa ter as mesmas posicoes do texto pesquisado
            orig = up
        mats = [(m.start(), m) for m in RE_MAT.finditer(up)]
        outras = list(RE_OUTRA.finditer(up))
        eventos = []
        for m in RE_DEPOIS.finditer(up):
            ini = max(0, m.start() - 70)
            deps = deputados_em(up[ini:m.start()])
            if deps:
                eventos.append((m.start(), m.group(1), deps[-1:]))
        for m in RE_ANTES.finditer(up):
            # nomes logo depois ("abstencao do Dep. X", "votos contrarios dos Deputados X, Y e Z"), ate um numero,
            # outra posicao ou outra materia ("13 votos sim, 01 voto nao do Deputado X e 01 abstencao do Deputado Y")
            jan = re.sub(r"\[\[FOLHA \d+\]\]", " ", up[m.end():m.end() + 140])
            corte = re.search(r"PEDIU|ENCERRAD|SENHOR PRESIDENTE|\d|PROJETO|AUTORIA|VETO|REQUERIMENTO|ABST|VOTO|CONTRARI|APROVAD|REJEITAD", jan)
            deps = deputados_em(jan[:corte.start()] if corte else jan)
            if deps:
                eventos.append((m.start(), m.group(1), deps))
        for pos, verbo, deps in sorted(eventos, key=lambda e: e[0]):
            ant = [x for x in mats if x[0] < pos]
            if not ant or any(ant[-1][0] < o.start() < pos for o in outras):
                continue   # sem materia antes, ou a posicao e sobre outra proposicao (resolucao, decreto, veto...)
            mpos, mm = ant[-1]
            tipo = "PEC" if mm.group(1).startswith("PROPOSTA") else "PLC" if "COMPLEMENTAR" in mm.group(1) else "PL"
            num, ano = int(mm.group(2).replace(".", "")), int(mm.group(3))
            veto = "VETO" in up[max(0, mpos - 160):mpos]
            posicao = "abstencao" if "ABST" in verbo else "contra"
            frase_ini = max(up.rfind(". ", 0, max(mpos, pos - 250)) + 2, pos - 250)
            frase_fim = up.find(". ", pos + len(verbo))
            frase_fim = len(up) if frase_fim < 0 else frase_fim + 1
            folha = max(1, orig.count("[[FOLHA ", 0, pos))
            if (s["id"], tipo, num, ano) in CORRECOES:
                tipo, num, ano = CORRECOES[(s["id"], tipo, num, ano)]
            lei = por_chave.get((tipo, num, ano))
            # conferencia: valores em R$ do trecho da ata tem de estar na ementa da lei (OCR embaralha colunas)
            valores = {re.sub(r"\D", "", v) for v in re.findall(r"R\$\s*([\d. ,]{4,}\d)", up[mpos:pos])}
            confere = None if not valores or not lei else any(v and v in re.sub(r"\D", "", lei["e"]) for v in valores)
            for d in deps:
                saida.append({"sessao": s["id"], "data": s["data_inicio"], "sn": s["__str__"], "url": s["upload_ata"],
                              "folha": folha, "materia_txt": "%s %d/%d" % (tipo, num, ano), "veto": veto,
                              "materia": lei["m"] if lei else None, "nominal": bool(lei and lei.get("nominal")),
                              "parlamentar": d, "posicao": posicao, "confere": confere, "trecho": orig[frase_ini:frase_fim]})
    # tira repetidos (a mesma frase achada pelos dois padroes)
    vistos, unicos = set(), []
    for x in saida:
        k = (x["sessao"], x["materia_txt"], x["parlamentar"], x["posicao"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(x)
    return unicos


def main():
    os.makedirs(PASTA, exist_ok=True)
    cache = os.path.join(PASTA, "_sessoes.json")
    if "--so-busca" in sys.argv and os.path.exists(cache):
        sessoes = json.load(open(cache, encoding="utf-8"))
    else:
        sessoes = [s for s in paginar("sessao/sessaoplenaria/?data_inicio__gte=%s" % DESDE, "sessoes")
                   if s.get("upload_ata") and s["data_inicio"] >= DESDE]
        json.dump(sessoes, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
        print("ALE-RO: %d sessoes com ata desde %s" % (len(sessoes), DESDE))
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            list(ex.map(baixar_pdf, sessoes))
        t0, ocr = time.time(), 0
        for i, s in enumerate(sessoes, 1):
            ocr += extrair(s["id"]) or 0
            if i % 25 == 0:
                print("  texto: %d de %d atas (%d folhas por OCR, %.0f s)" % (i, len(sessoes), ocr, time.time() - t0))
    buscar(sessoes)
    relatorio_posicoes(sessoes)


def relatorio_posicoes(sessoes):
    """logs/atas_posicoes.md: posicoes achadas nas atas x o que ja esta em data/alero_declaracoes.json."""
    js = open(os.path.join(ROOT, "data", "alero.js"), encoding="utf-8").read()
    alero = json.loads(js[js.index("=") + 1:js.rstrip().rindex(";")])
    decls = json.load(open(os.path.join(ROOT, "data", "alero_declaracoes.json"), encoding="utf-8"))["declaracoes"]
    feitas = {(d["materia"], str(d["parlamentar"])) for d in decls}
    lista = posicoes(sessoes, alero["leis"])
    novas = [x for x in lista if x["materia"] and not x["nominal"] and (x["materia"], x["parlamentar"]) not in feitas]
    linhas = ["# Posicoes individuais achadas nas atas da ALE-RO", "",
              "Status: CADASTRADA (ja em data/alero_declaracoes.json), NOVA (conferir na ata e cadastrar), "
              "NOMINAL (a votacao ja tem voto individual no SAPL), FORA (materia fora da lista de leis). "
              "'R$ nao confere' = os valores da ata nao estao na ementa: o OCR pode ter trocado a materia.", ""]
    for x in lista:
        st = ("FORA" if not x["materia"] else "NOMINAL" if x["nominal"] else
              "CADASTRADA" if (x["materia"], x["parlamentar"]) in feitas else "NOVA")
        nome = alero["parl"].get(x["parlamentar"], {}).get("n", x["parlamentar"])
        linhas.append("- **%s** %s, sessao %d, folha %d: %s - %s %s%s\n  > %s" % (
            st, x["data"], x["sessao"], x["folha"], x["materia_txt"], nome, x["posicao"],
            " (R$ nao confere)" if x["confere"] is False else "", x["trecho"][-400:]))
    p = os.path.join(ROOT, "logs", "atas_posicoes.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print("Posicoes nas atas: %d achadas, %d NOVAS para conferir -> %s" % (len(lista), len(novas), p))


if __name__ == "__main__":
    sys.exit(main())
