# -*- coding: utf-8 -*-
"""
baixar_tse.py - baixa automaticamente os arquivos de dados abertos do TSE para raw/.

O CDN do TSE (Akamai) bloqueia curl/urllib/PowerShell pela "impressao digital" TLS. Este script usa:
  1. curl_cffi imitando o Chrome (rapido, sem janela)            -> motor "cffi"
  2. se ainda der 403: o Microsoft Edge instalado, via Playwright -> motor "edge" (abre uma janela)

Instalar uma vez:   python -m pip install curl_cffi playwright
(nao precisa de "playwright install": usa o Edge que ja vem no Windows)

Uso:
    python scripts/baixar_tse.py --listar                 # mostra o que baixaria (com tamanhos), sem baixar
    python scripts/baixar_tse.py                          # perfil essencial, UFs RO e BR
    python scripts/baixar_tse.py --perfil tudo            # tudo que o TSE publica nos datasets abaixo
    python scripts/baixar_tse.py --ufs RO,MT,BR           # arquivos por UF so dessas UFs
    python scripts/baixar_tse.py --ufs todas              # todas as UFs (muitos GB!)
    python scripts/baixar_tse.py --so consulta_cand       # so arquivos cujo nome contem o texto
    python scripts/baixar_tse.py --forcar                 # baixa de novo mesmo sem mudanca
    python scripts/baixar_tse.py --motor edge             # usa direto o Edge
    python scripts/baixar_tse.py --rebuild                # no fim roda scripts/build_data.py

Incremental: raw/_downloads.json guarda ETag/tamanho de cada arquivo; o que nao mudou no TSE e pulado.
A lista de arquivos vem da API do portal (dadosabertos.tse.jus.br, CKAN); se ela falhar usa o catalogo fixo abaixo.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
REGISTRO = os.path.join(RAW, "_downloads.json")
CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id="
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/"
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
GRANDE = 300 * 1024 * 1024

# Datasets do portal. "essencial" = o que o sistema usa hoje (+ prestacao de contas p/ uso futuro).
DATASETS_TUDO = [
    "candidatos-2026",
    "prestacao-de-contas-eleitorais-2026",
    "denuncias-eleitorais", "denuncias-eleitorais-2024", "denuncias-eleitorais-2022", "denuncias-eleitorais-2020",
    "resultados-2022",
    "resultados-2024",
    "resultados-2026",
    "eleitorado-2026",
    "pesquisas-eleitorais-2026",
    "processual-2026",
    "codigos-oficiais-de-uf-e-municipios-segundo-o-tse-e-o-ibge",
]
ESSENCIAL = [
    r"^consulta_cand_2026", r"^consulta_cand_complementar_2026", r"^bem_candidato_2026", r"^consulta_coligacao_2026",
    r"^consulta_vagas_2026", r"^motivo_cassacao_2026", r"^rede_social_candidato_2026", r"^historico_candidatura_2026",
    r"^foto_cand2026_", r"^proposta_governo_2026_", r"^certidao_criminal_2026_",
    r"^prestacao_de_contas_eleitorais_candidatos_2026",
    r"^denuncia_20(20|22|24|26)",
    r"^votacao_candidato_munzona_20(22|24|26)", r"^votacao_secao_2022_(?!BR)",
    r"^municipio_tse_ibge",
]
# Catalogo fixo (fallback se a API do portal cair). Formato: caminho relativo ao CDN; {UF} e expandido.
CATALOGO = [
    "consulta_cand/consulta_cand_2026.zip",
    "consulta_cand_complementar/consulta_cand_complementar_2026.zip",
    "bem_candidato/bem_candidato_2026.zip",
    "consulta_coligacao/consulta_coligacao_2026.zip",
    "consulta_vagas/consulta_vagas_2026.zip",
    "motivo_cassacao/motivo_cassacao_2026.zip",
    "consulta_cand/rede_social_candidato_2026.zip",
    "historico_candidatura/historico_candidatura_2026.zip",
    "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/fotos/foto_cand2026_{UF}_div.zip",
    "proposta_governo/proposta_governo_2026_{UF}.zip",
    "certidao_criminal/certidao_criminal_2026_{UF}.zip",
    "prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip",
    "prestacao_contas/prestacao_de_contas_eleitorais_orgaos_partidarios_2026.zip",
    "prestacao_contas/CNPJ_campanha_2026.zip",
    "denuncia/denuncia_2026.zip", "denuncia/denuncia_2024.zip", "denuncia/denuncia_2022.zip", "denuncia/denuncia_2020.zip",
    "votacao_candidato_munzona/votacao_candidato_munzona_2022.zip",
    "votacao_candidato_munzona/votacao_candidato_munzona_2024.zip",
    "votacao_candidato_munzona/votacao_candidato_munzona_2026.zip",
    "votacao_partido_munzona/votacao_partido_munzona_2022.zip",
    "detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip",
    "detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip",
    "votacao_secao/votacao_secao_2022_{UF}.zip",
    "perfil_eleitorado/perfil_eleitorado_2026.zip",
    "eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip",
    "pesquisa_eleitoral/pesquisa_eleitoral_2026.zip",
    "processual/processo_eleitoral_2026.zip",
    "municipio_tse_ibge/municipio_tse_ibge.zip",
]


# ---------------------------------------------------------------- utilidades
def humano(n):
    if n is None:
        return "?"
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return ("%.0f %s" if u in ("B", "KB") else "%.1f %s") % (n, u)
        n /= 1024.0


def nome_arquivo(url):
    return url.rstrip("/").split("/")[-1]


def uf_do_arquivo(nome):
    """Devolve a UF (ou BR/ZZ) se o arquivo for 'por UF'; None se for nacional/unico."""
    m = re.search(r"_(%s|BR|ZZ)(_div)?\.zip$" % "|".join(UFS), nome)
    return m.group(1) if m else None


def carregar_registro():
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def salvar_registro(reg):
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1, sort_keys=True)


# ---------------------------------------------------------------- motores
class MotorCffi:
    nome = "cffi"

    def __init__(self):
        from curl_cffi import requests as cr  # noqa: PLC0415
        self.s = cr.Session(impersonate="chrome")

    def json(self, url):
        r = self.s.get(url, timeout=60)
        if r.status_code != 200:
            raise IOError("HTTP %d" % r.status_code)
        return r.json()

    def info(self, url):
        """(status, tamanho, etag, last_modified). HEAD do TSE devolve content-length errado; usa Range 0-0."""
        for tentativa in range(4):
            r = self.s.get(url, headers={"Range": "bytes=0-0"}, timeout=60)
            if r.status_code in (200, 206, 404):
                break
            time.sleep(2 * (tentativa + 1))   # o CDN as vezes nega pedidos muito seguidos
        tam = None
        cr_ = r.headers.get("content-range") or ""
        if "/" in cr_:
            try:
                tam = int(cr_.rsplit("/", 1)[1])
            except ValueError:
                tam = None
        elif r.status_code == 200:
            tam = int(r.headers.get("content-length") or 0) or None
        return r.status_code, tam, r.headers.get("etag"), r.headers.get("last-modified")

    def baixar(self, url, destino, tamanho=None):
        parte = destino + ".part"
        ja = os.path.getsize(parte) if os.path.exists(parte) else 0
        headers = {"Range": "bytes=%d-" % ja} if ja else {}
        r = self.s.get(url, headers=headers, stream=True, timeout=120)
        if r.status_code == 403:
            r.close()
            raise PermissionError("403")
        if r.status_code not in (200, 206):
            r.close()
            raise IOError("HTTP %d" % r.status_code)
        modo = "ab" if r.status_code == 206 else "wb"
        feito = ja if modo == "ab" else 0
        t0 = time.time()
        ultimo = 0
        with open(parte, modo) as f:
            for bloco in r.iter_content(chunk_size=1 << 20):
                f.write(bloco)
                feito += len(bloco)
                if time.time() - ultimo > 1:
                    ultimo = time.time()
                    vel = (feito - ja) / max(0.1, time.time() - t0)
                    pct = (" %5.1f%%" % (100.0 * feito / tamanho)) if tamanho else ""
                    sys.stdout.write("\r    %s%s  %s/s   " % (humano(feito), pct, humano(vel)))
                    sys.stdout.flush()
        r.close()
        sys.stdout.write("\r" + " " * 60 + "\r")
        if tamanho and os.path.getsize(parte) != tamanho:
            raise IOError("tamanho diferente do esperado (%d x %d); rode de novo para continuar" % (os.path.getsize(parte), tamanho))
        os.replace(parte, destino)


class MotorEdge:
    """Controla o Microsoft Edge instalado (janela visivel) para baixar como um navegador comum."""
    nome = "edge"

    def __init__(self):
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        self._pw = sync_playwright().start()
        self._br = self._pw.chromium.launch(channel="msedge", headless=False)
        self._ctx = self._br.new_context(accept_downloads=True)
        self._pg = self._ctx.new_page()
        self._pg.goto("https://dadosabertos.tse.jus.br/", timeout=90000)

    def json(self, url):
        r = self._ctx.request.get(url, timeout=90000)
        if r.status != 200:
            raise IOError("HTTP %d" % r.status)
        return r.json()

    def info(self, url):
        return 200, None, None, None

    def baixar(self, url, destino, tamanho=None):
        with self._pg.expect_download(timeout=4 * 3600 * 1000) as dl:
            try:
                self._pg.goto(url, timeout=90000)
            except Exception:  # noqa: BLE001  - "Download is starting" e o comportamento normal
                pass
        d = dl.value
        if d.failure():
            raise IOError(d.failure())
        d.save_as(destino)

    def fechar(self):
        try:
            self._br.close()
            self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


def criar_motor(pref):
    if pref in ("auto", "cffi"):
        try:
            return MotorCffi()
        except ImportError:
            if pref == "cffi":
                sys.exit("curl_cffi nao instalado:  python -m pip install curl_cffi")
            print("curl_cffi nao instalado; usando o Edge.")
    try:
        return MotorEdge()
    except ImportError:
        sys.exit("playwright nao instalado:  python -m pip install playwright")


# ---------------------------------------------------------------- catalogo
def descobrir(motor, datasets):
    """Lista de (dataset, url) a partir da API CKAN; fallback para o catalogo fixo."""
    urls = []
    falhou = False
    for ds in datasets:
        try:
            j = motor.json(CKAN + ds)
            recursos = j["result"]["resources"]
            urls += [(ds, r["url"]) for r in recursos if r.get("url", "").startswith("http")]
            print("  %-60s %3d arquivos" % (ds, len(recursos)))
        except Exception as e:  # noqa: BLE001
            print("  %-60s falhou (%s)" % (ds, e))
            falhou = True
    if not urls or falhou:
        print("  usando catalogo fixo como complemento")
        vistos = {nome_arquivo(u) for _, u in urls}
        for c in CATALOGO:
            base = c if c.startswith("http") else CDN + c
            for u in ([base.replace("{UF}", x) for x in UFS + ["BR"]] if "{UF}" in base else [base]):
                if nome_arquivo(u) not in vistos:
                    urls.append(("catalogo", u))
    # remove duplicados mantendo ordem
    out, vistos = [], set()
    for ds, u in urls:
        if u not in vistos:
            vistos.add(u)
            out.append((ds, u))
    return out


def filtrar(urls, perfil, ufs, so):
    out = []
    for ds, u in urls:
        n = nome_arquivo(u)
        if not n.lower().endswith(".zip"):
            continue
        if perfil == "essencial" and not any(re.search(p, n) for p in ESSENCIAL):
            continue
        uf = uf_do_arquivo(n)
        if uf and ufs is not None and uf not in ufs:
            continue
        if so and not any(s.lower() in n.lower() for s in so):
            continue
        out.append((ds, u))
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Baixa dados abertos do TSE para raw/")
    ap.add_argument("--perfil", choices=("essencial", "tudo"), default="essencial")
    ap.add_argument("--ufs", default="RO,BR", help="UFs dos arquivos por estado (ex.: RO,MT,BR) ou 'todas'")
    ap.add_argument("--so", default="", help="baixa so arquivos cujo nome contem estes textos (virgula)")
    ap.add_argument("--listar", action="store_true", help="so lista, nao baixa")
    ap.add_argument("--forcar", action="store_true", help="ignora o registro e baixa de novo")
    ap.add_argument("--motor", choices=("auto", "cffi", "edge"), default="auto")
    ap.add_argument("--rebuild", action="store_true", help="roda scripts/build_data.py no fim")
    args = ap.parse_args()

    ufs = None if args.ufs.strip().lower() == "todas" else {u.strip().upper() for u in args.ufs.split(",") if u.strip()}
    so = [s.strip() for s in args.so.split(",") if s.strip()]
    os.makedirs(RAW, exist_ok=True)

    motor = criar_motor(args.motor)
    edge = motor if isinstance(motor, MotorEdge) else None
    print("Motor: %s\nConsultando o portal de dados abertos do TSE..." % motor.nome)
    alvos = filtrar(descobrir(motor, DATASETS_TUDO), args.perfil, ufs, so)
    print("\n%d arquivos no perfil '%s' (UFs: %s)\n" % (len(alvos), args.perfil, "todas" if ufs is None else ",".join(sorted(ufs))))

    reg = carregar_registro()
    baixados, pulados, erros, total = 0, 0, [], 0
    for i, (ds, url) in enumerate(alvos, 1):
        nome = nome_arquivo(url)
        destino = os.path.join(RAW, nome)
        try:
            status, tam, etag, lm = motor.info(url)
        except Exception as e:  # noqa: BLE001
            status, tam, etag, lm = None, None, None, None
            print("[%d/%d] %s  (info falhou: %s)" % (i, len(alvos), nome, e))
        if status == 403 and not edge and args.motor == "auto":
            print("  403 no curl_cffi -> trocando para o Edge")
            edge = criar_motor("edge")
        total += tam or 0
        antigo = reg.get(nome, {})
        existe = os.path.exists(destino)
        mudou = not existe or args.forcar or (etag and antigo.get("etag") != etag) or (tam and os.path.getsize(destino) != tam and antigo.get("tamanho") != tam)
        if existe and not antigo and tam and os.path.getsize(destino) == tam:
            mudou = False  # baixado antes a mao, mesmo tamanho
        marca = "BAIXAR" if mudou else "ok"
        aviso = "  (GRANDE)" if tam and tam > GRANDE else ""
        if status not in (None, 200, 206):
            aviso += "  (HTTP %s)" % status
        print("[%d/%d] %-6s %-58s %10s%s" % (i, len(alvos), marca, nome, humano(tam), aviso))
        if args.listar:
            continue
        if not mudou:
            pulados += 1
            if not antigo and tam:
                reg[nome] = {"url": url, "etag": etag, "tamanho": tam, "last_modified": lm, "baixado_em": None}
            continue
        m = edge if (edge and status == 403) else motor
        for tentativa in range(3):
            try:
                m.baixar(url, destino, tam)
                break
            except PermissionError:
                if edge is None:
                    print("    403 -> tentando pelo Edge")
                    edge = criar_motor("edge")
                m = edge
            except Exception as e:  # noqa: BLE001
                if tentativa == 2:
                    print("    ERRO:", e)
                    erros.append(nome)
                else:
                    print("    falhou (%s); tentando de novo..." % e)
                    time.sleep(3 * (tentativa + 1))
        else:
            continue
        if os.path.exists(destino) and nome not in erros:
            baixados += 1
            reg[nome] = {"url": url, "etag": etag, "tamanho": os.path.getsize(destino), "last_modified": lm,
                         "baixado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "motor": m.nome}
            salvar_registro(reg)

    salvar_registro(reg)
    if edge:
        edge.fechar()
    if args.listar:
        print("\nTotal aproximado: %s. Rode sem --listar para baixar." % humano(total))
        return
    print("\nBaixados: %d   ja atualizados: %d   erros: %d" % (baixados, pulados, len(erros)))
    for e in erros:
        print("  erro:", e)
    if args.rebuild:
        subprocess.call([sys.executable, os.path.join(ROOT, "scripts", "build_data.py")])
    elif baixados:
        print("Proximo passo:  python scripts/build_data.py")


if __name__ == "__main__":
    main()
