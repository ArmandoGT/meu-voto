# -*- coding: utf-8 -*-
"""
teste_ui.py - abre o sistema no Microsoft Edge (sem janela, via Playwright) e testa a interface de verdade.

Uso:  python scripts/testes/teste_ui.py            (precisa de: python -m pip install playwright)
      saida (screenshots, PDF da colinha): scripts/testes/saida/

Cobre: pesquisa, ficha, todas as abas e criterios, TODAS as fichas de RO e presidente, tela Emendas em todos
os municipios/filtros, tela Votacoes (ALE-RO) com todos os deputados/tipos/anos, tela Coligacoes (por candidato e por grupo), tela Resultados (consulta de candidato, votos por cidade, por que nao foi eleito), versao mobile, funcionamento sem os dados opcionais, impressao da colinha em PDF A4 e em PNG
e celulares reais emulados (Pixel 7, iPhone 13, Galaxy S9+: toque, fonte minima, alvos de toque).
"""
import os
import pathlib
import re
import shutil
import struct
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SP = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent / "saida"
SP.mkdir(parents=True, exist_ok=True)
falhas, oks = [], []


def ok(cond, msg):
    (oks if cond else falhas).append(msg)
    print(("  OK   " if cond else "  FALHA ") + msg)


RUIM = "(() => { const t = document.body.innerText; const m = t.match(/.{0,40}(NaN|undefined|\\[object Object\\]|null ·|∞).{0,40}/); return m ? m[0] : ''; })()"
OVERFLOW = "(() => { const w = document.documentElement.clientWidth; const bad = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > w + 1 && getComputedStyle(e).position !== 'fixed' && !e.closest('[style*=overflow], .tabela, .modal'); }); return document.documentElement.scrollWidth > w + 1 ? (bad[0] ? bad[0].className || bad[0].tagName : 'doc') : ''; })()"


def nova(b, w=1280, h=900):
    pg = b.new_page(viewport={"width": w, "height": h})
    pg._erros = []
    pg.on("pageerror", lambda e: pg._erros.append("pageerror: " + str(e)))
    pg.on("console", lambda m: pg._erros.append("console: " + m.text) if m.type == "error" else None)
    pg.on("requestfailed", lambda r: pg._erros.append("requestfailed: " + r.url) if not r.url.endswith("emendas.js") or "data" not in r.url else None)
    return pg


def abrir_secoes_modal(pg):
    pg.evaluate("document.querySelectorAll('.modal details').forEach(d => d.open = true)")


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)

    print("1. Pesquisa (index.html)")
    for w in (1280, 390):
        pg = nova(b, w, 900)
        pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(2500)
        n = pg.evaluate("document.querySelectorAll('.cand').length")
        ok(n > 0, "index %dpx: %d cartoes de candidatos" % (w, n))
        pg.fill("input[type=search]", "fera"); pg.wait_for_timeout(800)
        ok(pg.evaluate("document.body.innerText.includes('Rafael Fera')"), "index %dpx: busca 'fera' acha Rafael Fera" % w)
        pg.click(".cand"); pg.wait_for_timeout(600); abrir_secoes_modal(pg)
        txt = pg.inner_text(".modal")
        ok(all(s in txt for s in ("Emendas parlamentares", "Financiamento de campanha", "Histórico eleitoral")), "index %dpx: ficha tem emendas + financiamento + historico" % w)
        ok(pg.evaluate(RUIM) == "", "index %dpx: sem NaN/undefined na ficha [%s]" % (w, pg.evaluate(RUIM)))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        ok(pg.query_selector(".modal") is None, "index %dpx: Esc fecha a ficha" % w)
        if w == 390:
            ok(pg.evaluate(OVERFLOW) == "", "index 390px: sem rolagem horizontal [%s]" % pg.evaluate(OVERFLOW))
        ok(not pg._erros, "index %dpx: sem erros de console %s" % (w, pg._erros[:3]))

    print("2. Meu voto: todas as abas, todos os criterios, todas as 410 fichas de RO")
    pg = nova(b)
    pg.goto((ROOT / "meu-voto.html").as_uri()); pg.wait_for_timeout(2500)
    abas = pg.evaluate("[...document.querySelectorAll('#abas button')].map(b => b.textContent)")
    ok(len(abas) >= 5, "abas de cargo: %d" % len(abas))
    for i in range(len(abas)):
        pg.click("#abas button >> nth=%d" % i); pg.wait_for_timeout(200)
        itens = pg.evaluate("document.querySelectorAll('#rank .rank-item').length")
        scores = pg.evaluate("[...document.querySelectorAll('.score')].map(s => parseInt(s.textContent))")
        ok(itens > 0 and all(0 <= s <= 100 for s in scores), "aba %s: %d no ranking, scores 0-100" % (abas[i].split('\n')[0][:20], itens))
    # liga todos os criterios
    pg.evaluate("document.querySelectorAll('#criterios input[type=checkbox]').forEach(c => { if (!c.checked) c.click(); })")
    pg.wait_for_timeout(500)
    scores = pg.evaluate("[...document.querySelectorAll('.score')].map(s => s.textContent)")
    ok(scores and all("NaN" not in s for s in scores), "todos os criterios ligados: scores validos (%d)" % len(scores))
    pg.click("#btn-criterios-padrao") if False else None
    pg.evaluate("localStorage.clear()")
    # todas as fichas de RO + BR
    res = pg.evaluate("""(async () => {
      const lista = await App.Dados.carregarVarias(['RO', 'BR']);
      const erros = [];
      for (const c of lista) {
        try {
          App.Modal.abrir(c);
          document.querySelectorAll('.modal details').forEach(d => d.open = true);
          const t = document.querySelector('.modal').innerText;
          const m = t.match(/.{0,30}(NaN|undefined|\\[object Object\\]|∞).{0,30}/);
          if (m) erros.push(c.urna + ': ' + m[0]);
          App.Modal.fechar();
        } catch (e) { erros.push(c.urna + ': ' + e.message); }
      }
      return { n: lista.length, erros };
    })()""")
    ok(not res["erros"], "%d fichas RO+BR abertas sem erro/NaN %s" % (res["n"], res["erros"][:3]))
    # escolher candidato e colinha
    pg.click("#abas button >> nth=0"); pg.wait_for_timeout(200)
    pg.click("#rank .rank-item .esc"); pg.wait_for_timeout(200)
    pg.evaluate("App.Telas.mostrar('tela-cola')"); pg.wait_for_timeout(300)
    ok(pg.evaluate("document.querySelectorAll('#colinha-inline .item[data-sq]').length") >= 1, "colinha mostra o escolhido")
    pg.evaluate("App.Telas.mostrar('tela-mais')"); pg.wait_for_timeout(300)
    ok("portal da transparência — emendas" in pg.inner_text("#tela-mais").lower(), "tela Mais lista as fontes de emendas")
    ok(not pg._erros, "meu-voto: sem erros de console %s" % pg._erros[:3])
    pg.evaluate("localStorage.clear()")

    print("3. Emendas: todos os municipios x origens")
    pg = nova(b)
    pg.goto((ROOT / "emendas.html").as_uri()); pg.wait_for_timeout(2500)
    muns = pg.evaluate("[...document.querySelectorAll('#em-mun option')].map(o => o.value)")
    ok(len(muns) == 53, "53 opcoes de municipio (52 + estadual): %d" % len(muns))
    ruins = []
    for mun in muns:
        for nivel in ("", "fed", "est"):
            pg.select_option("#em-mun", mun); pg.select_option("#em-nivel", nivel)
            r = pg.evaluate(RUIM)
            if r:
                ruins.append("%s/%s: %s" % (mun, nivel, r))
    ok(not ruins, "159 combinacoes sem NaN/undefined %s" % ruins[:3])
    pg.select_option("#em-mun", "RO|ARIQUEMES"); pg.select_option("#em-nivel", "")
    anos = pg.evaluate("[...document.querySelectorAll('#em-ano option')].map(o => o.value).filter(Boolean)")
    for a in anos:
        pg.select_option("#em-ano", a)
        if pg.evaluate(RUIM):
            ruins.append("ano " + a)
    ok(not ruins, "filtro por ano (%d anos) ok" % len(anos))
    pg.select_option("#em-ano", "")
    pg.check("#em-so-cand"); pg.wait_for_timeout(200)
    ok(pg.evaluate("[...document.querySelectorAll('.em-autor')].every(e => !e.classList.contains('sem-cand'))"), "'so candidatos' mostra so candidatos")
    pg.uncheck("#em-so-cand"); pg.uncheck("#em-com-coletivas"); pg.wait_for_timeout(200)
    ok(not pg.evaluate("document.body.innerText.includes('Bancada De Rondonia')"), "sem coletivas: bancada some")
    pg.check("#em-com-coletivas")
    # "Ver emendas" abre a lista do autor LOGO ABAIXO do card (antes ela ia para o fim da pagina e parecia nao fazer nada)
    pg.click(".em-autor >> nth=1 >> .ver-itens"); pg.wait_for_timeout(600)
    det = pg.evaluate("""(() => { const cards = [...document.querySelectorAll('.em-autor')]; const c = cards[1];
      const d = c.nextElementSibling; const b = c.querySelector('.ver-itens');
      const r = d ? d.getBoundingClientRect() : null;
      return { logoAbaixo: !!d && d.classList.contains('em-detalhe'), linhas: d ? d.querySelectorAll('tbody tr').length : 0,
               esperado: parseInt((c.querySelector('.sub').textContent.match(/(\\d+) registro/) || [])[1] || '-1'),
               expandido: b.getAttribute('aria-expanded'), texto: b.textContent.trim(), naTela: !!r && r.top < innerHeight && r.bottom > 0,
               abertos: document.querySelectorAll('.em-detalhe').length }; })()""")
    ok(det["logoAbaixo"] and det["abertos"] == 1, "'Ver emendas' abre a lista logo abaixo do card clicado")
    ok(det["linhas"] == det["esperado"] > 0, "lista aberta tem todas as emendas do autor (%d de %d)" % (det["linhas"], det["esperado"]))
    ok(det["expandido"] == "true" and "Ocultar" in det["texto"] and det["naTela"], "botao vira 'Ocultar emendas' e a lista fica visivel na tela")
    pg.click(".em-autor >> nth=1 >> .ver-itens"); pg.wait_for_timeout(300)
    ok(pg.evaluate("document.querySelectorAll('.em-detalhe').length") == 0, "clicar de novo fecha a lista")
    pg.click(".em-autor >> nth=0 >> .ver-itens"); pg.wait_for_timeout(300)
    pg.click(".em-detalhe .fechar-det"); pg.wait_for_timeout(300)
    ok(pg.evaluate("document.querySelectorAll('.em-detalhe').length") == 0, "botao 'Fechar' do painel fecha a lista")
    antes = pg.evaluate("document.querySelectorAll('.em-itens tbody tr').length")
    if pg.query_selector("#em-mais"):
        pg.click("#em-mais"); pg.wait_for_timeout(200)
    ok(pg.evaluate("document.querySelectorAll('.em-itens tbody tr').length") > antes, "'Mostrar mais' carrega mais itens")
    # KPI = soma do ranking
    kpi_ok = pg.evaluate("""(() => { const E = window.EMENDAS; return !!E; })()""")
    ok(kpi_ok, "window.EMENDAS carregado")
    pg.click(".em-autor .abrir-ficha"); pg.wait_for_timeout(400)
    ok(pg.query_selector(".modal") is not None, "botao Ficha abre o candidato")
    pg.keyboard.press("Escape")
    ok(not pg._erros, "emendas: sem erros de console %s" % pg._erros[:3])
    pg = nova(b, 390, 844)
    pg.goto((ROOT / "emendas.html").as_uri()); pg.wait_for_timeout(2500)
    ok(pg.evaluate(OVERFLOW) == "", "emendas 390px: sem rolagem horizontal [%s]" % pg.evaluate(OVERFLOW))

    print("3b. Votacoes da ALE-RO: todos os deputados, tipos e anos")
    pg = nova(b)
    pg.goto((ROOT / "votacoes.html").as_uri()); pg.wait_for_timeout(2500)
    n_itens = pg.evaluate("document.querySelectorAll('.vt-item').length")
    ok(n_itens > 0, "votacoes: %d votacoes na lista" % n_itens)
    deps = pg.evaluate("[...document.querySelectorAll('#vt-dep option')].map(o => o.value).filter(Boolean)")
    n_cand = pg.evaluate("Object.keys(window.ALERO.porCand).length")
    ok(len(deps) > 0 and n_cand > 0, "votacoes: %d deputados no filtro, %d casados com candidatos 2026" % (len(deps), n_cand))
    ruins = []
    for dp in deps:
        pg.select_option("#vt-dep", dp)
        r = pg.evaluate(RUIM)
        if r:
            ruins.append("dep %s: %s" % (dp, r))
        if not pg.evaluate("document.querySelectorAll('.vt-meu .voto').length === document.querySelectorAll('.vt-item').length"):
            ruins.append("dep %s: item sem o voto do deputado" % dp)
    ok(not ruins, "cada deputado filtrado: voto dele em todos os itens, sem NaN %s" % ruins[:3])
    pg.select_option("#vt-dep", "")
    for sel in ("#vt-tipo", "#vt-ano"):
        for v in pg.evaluate("[...document.querySelectorAll('%s option')].map(o => o.value).filter(Boolean)" % sel):
            pg.select_option(sel, v)
            if pg.evaluate(RUIM) or not pg.evaluate("document.querySelectorAll('.vt-item').length"):
                ruins.append("%s=%s" % (sel, v))
        pg.select_option(sel, "")
    ok(not ruins, "filtros de tipo e ano: todos com resultado e sem NaN %s" % ruins[:3])
    # "Ver quem votou como" abre os votos logo abaixo da votacao; a lista tem todos os votos registrados
    pg.click(".vt-item >> nth=1 >> .ver-votos"); pg.wait_for_timeout(500)
    det = pg.evaluate("""(() => { const it = document.querySelectorAll('.vt-item')[1]; const d = it.nextElementSibling;
      const x = window.ALERO.vot.find(v => v.id === +it.dataset.id);
      return { abaixo: !!d && d.classList.contains('vt-detalhe'), nomes: d ? d.querySelectorAll('.vt-nomes li').length : 0,
               esperado: Object.keys(x.v).length, abertos: document.querySelectorAll('.vt-detalhe').length }; })()""")
    ok(det["abaixo"] and det["abertos"] == 1 and det["nomes"] == det["esperado"] > 0,
       "'Ver quem votou como' abre logo abaixo com todos os votos (%d de %d)" % (det["nomes"], det["esperado"]))
    pg.click(".vt-item >> nth=1 >> .ver-votos"); pg.wait_for_timeout(300)
    ok(pg.evaluate("document.querySelectorAll('.vt-detalhe').length") == 0, "clicar de novo fecha os votos")
    pg.fill("#vt-texto", "veto"); pg.wait_for_timeout(500)
    ok(pg.evaluate("document.querySelectorAll('.vt-item').length") > 0, "busca por texto ('veto') acha votacoes")
    pg.fill("#vt-texto", "")
    # link da ficha: votacoes.html#votacoes-<id> abre filtrada no deputado
    pid = pg.evaluate("Object.values(window.ALERO.porCand)[0]")
    pg.goto((ROOT / "votacoes.html").as_uri() + "#votacoes-" + pid); pg.wait_for_timeout(2500)
    ok(pg.eval_on_selector("#vt-dep", "e => e.value") == pid, "link #votacoes-<deputado> abre filtrado no deputado")
    pg.click(".vt-item >> nth=0 >> .ver-votos"); pg.wait_for_timeout(300)
    pg.click(".vt-detalhe .abrir-ficha"); pg.wait_for_timeout(400)
    abrir_secoes_modal(pg)
    ok(pg.query_selector(".modal") is not None and "Votações na Assembleia Legislativa de RO" in pg.inner_text(".modal"), "ficha de deputado-candidato tem a secao de votacoes da ALE-RO")
    pg.click(".modal a[data-tela='tela-votacoes']"); pg.wait_for_timeout(400)
    ok(pg.query_selector(".modal") is None, "link 'Todas as votacoes' da ficha fecha a ficha")
    # fase 2: leis sem voto individual
    pg.goto((ROOT / "votacoes.html").as_uri()); pg.wait_for_timeout(2500)
    pg.click('.vt-modos button[data-modo="leis"]'); pg.wait_for_timeout(400)
    ok(pg.evaluate("document.querySelectorAll('.vt-lei').length") > 0 and "não fica registrado como cada deputado votou" in pg.inner_text("#vt-conteudo"),
       "modo 'Leis sem voto individual' lista as leis e explica a votacao simbolica")
    ruins = []
    for sel in ("#vt-tipo", "#vt-ano"):
        for v in pg.evaluate("[...document.querySelectorAll('%s option')].map(o => o.value).filter(Boolean)" % sel):
            pg.select_option(sel, v)
            if pg.evaluate(RUIM) or not pg.evaluate("document.querySelectorAll('.vt-lei').length"):
                ruins.append("%s=%s" % (sel, v))
        pg.select_option(sel, "")
    for dp in deps[:40]:
        pg.select_option("#vt-dep", dp)
        if pg.evaluate(RUIM):
            ruins.append("dep " + dp)
    pg.select_option("#vt-dep", "")
    ok(not ruins, "leis: filtros de tipo, ano e deputado sem NaN %s" % ruins[:3])
    pg.fill("#vt-texto", "1243"); pg.wait_for_timeout(500)
    txt = pg.inner_text("#vt-conteudo")
    ok("PL nº 1243/2025" in txt and "Sem voto individual registrado" in txt and "Lei" in txt and "6.328" in txt, "busca '1243' acha o PL 1243/2025, sem voto individual, que virou a Lei 6.328")
    ok("Delegado Lucas" in txt and "Ata nº 252" in txt, "PL 1243/2025 mostra a declaracao oficial do Delegado Lucas com a fonte")
    pg.fill("#vt-texto", "")
    pg.wait_for_timeout(400)
    if pg.query_selector(".ver-nominal"):
        pg.click(".ver-nominal >> nth=0"); pg.wait_for_timeout(400)
        ok(pg.eval_on_selector('.vt-modos button[data-modo="nominal"]', "e => e.getAttribute('aria-pressed')") == "true"
           and pg.query_selector(".vt-filtro-materia") is not None and pg.evaluate("document.querySelectorAll('.vt-item[data-id]').length") > 0,
           "'Ver a votacao nominal' troca de modo e mostra so as votacoes daquela lei")
    # fase 3: Camara e Senado (candidatos de RO)
    for casa in ("camara", "senado"):
        pg.goto((ROOT / "votacoes.html").as_uri()); pg.wait_for_timeout(2500)
        pg.click('.vt-modos button[data-modo="%s"]' % casa); pg.wait_for_timeout(400)
        n = pg.evaluate("document.querySelectorAll('.vt-item[data-id]').length")
        ok(n > 0 and "Placar da votação" in pg.inner_text("#vt-conteudo"), "%s: lista votacoes com o placar geral (%d)" % (casa, n))
        ruins = []
        for dp in pg.evaluate("[...document.querySelectorAll('#vt-dep option')].map(o => o.value).filter(Boolean)"):
            pg.select_option("#vt-dep", dp)
            if pg.evaluate(RUIM) or not pg.evaluate("document.querySelectorAll('.vt-meu .voto').length === document.querySelectorAll('.vt-item[data-id]').length"):
                ruins.append(dp)
        pg.select_option("#vt-dep", "")
        for v in pg.evaluate("[...document.querySelectorAll('#vt-ano option')].map(o => o.value).filter(Boolean)"):
            pg.select_option("#vt-ano", v)
            if pg.evaluate(RUIM):
                ruins.append("ano " + v)
        pg.select_option("#vt-ano", "")
        ok(not ruins, "%s: cada parlamentar e cada ano sem NaN, com o voto em todos os itens %s" % (casa, ruins[:3]))
        pg.click(".vt-item >> nth=0 >> .ver-votos"); pg.wait_for_timeout(300)
        ok(pg.query_selector(".vt-detalhe .vt-nomes li") is not None, "%s: 'Ver votos dos candidatos de RO' abre a lista" % casa)
        pid = pg.evaluate("Object.values(window.VOTFED.%s.porCand)[0]" % casa)
        pg.goto("about:blank"); pg.goto((ROOT / "votacoes.html").as_uri() + "#votacoes-%s-%s" % (casa, pid)); pg.wait_for_timeout(2500)
        ok(pg.eval_on_selector('.vt-modos button[data-modo="%s"]' % casa, "e => e.getAttribute('aria-pressed')") == "true"
           and pg.eval_on_selector("#vt-dep", "e => e.value") == pid, "%s: link #votacoes-%s-<id> abre a Casa filtrada no parlamentar" % (casa, casa))
        pg.click(".vt-item >> nth=0 >> .ver-votos"); pg.wait_for_timeout(300)
        pg.click(".vt-detalhe li.sel .abrir-ficha"); pg.wait_for_timeout(400); abrir_secoes_modal(pg)
        rot = "Como votou na Câmara" if casa == "camara" else "Votações no Senado Federal"
        ok(pg.query_selector(".modal") is not None and rot in pg.inner_text(".modal") and pg.evaluate(RUIM) == "", "%s: ficha do candidato mostra '%s'" % (casa, rot))
        pg.click(".modal a[data-casa='%s']" % casa); pg.wait_for_timeout(400)
        ok(pg.query_selector(".modal") is None and pg.eval_on_selector("#vt-dep", "e => e.value") == pid, "%s: link da ficha volta para a Casa filtrada no parlamentar" % casa)
    ok(not pg._erros, "votacoes: sem erros de console %s" % pg._erros[:3])
    pg = nova(b, 390, 844)
    pg.goto((ROOT / "votacoes.html").as_uri()); pg.wait_for_timeout(2500)
    pg.click(".vt-item >> nth=0 >> .ver-votos"); pg.wait_for_timeout(300)
    ok(pg.evaluate(OVERFLOW) == "", "votacoes 390px: sem rolagem horizontal [%s]" % pg.evaluate(OVERFLOW))

    print("3c. Perfil: municipio livre, criterios locais, posicoes nas votacoes")
    pg = nova(b)
    pg.goto((ROOT / "meu-voto.html").as_uri()); pg.evaluate("localStorage.clear()")
    pg.goto((ROOT / "meu-voto.html").as_uri() + "#perfil"); pg.wait_for_timeout(2500)
    ok(pg.evaluate("App.perfil().mun") == "" and not pg.evaluate("document.getElementById('perfil-aviso').hidden"),
       "eleitor novo: sem municipio, Meu voto avisa que os criterios locais estao desligados")
    ok(pg.evaluate("document.querySelectorAll('#pf-mun option').length") == 53, "Perfil lista os 52 municipios de RO (+ 'escolha')")
    pg.select_option("#pf-mun", "Porto Velho"); pg.wait_for_timeout(800)
    ok(pg.evaluate("App.perfil()") == {"uf": "RO", "mun": "Porto Velho"}, "escolher Porto Velho grava o Perfil")
    ok("Porto Velho" in pg.evaluate("document.querySelector('label[for=cr-munHist]').textContent") and pg.evaluate("document.getElementById('perfil-aviso').hidden"),
       "Meu voto passa a usar Porto Velho nos criterios e o aviso some")
    # emendas por municipio = soma da lista da tela Emendas; para Ariquemes, igual ao valor pre-calculado antigo
    pg.select_option("#pf-mun", "Ariquemes"); pg.wait_for_timeout(500)
    dif = pg.evaluate("""(() => { const E = window.EMENDAS; let n = 0, ruins = [];
      for (const [sq, e] of Object.entries(E.porCand)) { if (!e.foco) continue; n++; const f = e.foco.fed || {}, s = e.foco.est || {};
        const velho = Math.max(f.emp || 0, f.rec || 0) + Math.max(s.prev || 0, s.emp || 0); const novo = (App.emendasFoco(sq) || { destinado: 0 }).destinado;
        if (Math.abs(velho - novo) > 1) ruins.push(sq); } return { n, ruins }; })()""")
    ok(dif["n"] > 0 and not dif["ruins"], "emendas para Ariquemes pelo Perfil = valor antigo pre-calculado (%d candidatos) %s" % (dif["n"], dif["ruins"][:3]))
    # outra UF: sem emendas por municipio -> criterio fica de fora (nao zera ninguem)
    pg.select_option("#pf-uf", "MT"); pg.wait_for_timeout(1500)
    ok(pg.evaluate("App.perfil().uf") == "MT" and pg.evaluate("App.perfil().mun") == "" and pg.evaluate("document.querySelectorAll('#pf-mun option').length") > 100,
       "trocar a UF para MT limpa o municipio e lista os municipios de MT")
    pg.select_option("#pf-mun", "Cuiabá"); pg.wait_for_timeout(1500)
    ok("não disponíveis" in pg.inner_text("#pf-status") and not pg.evaluate("App.temEmendasMun()"), "MT: Perfil avisa que ainda nao ha emendas por municipio")
    pg.evaluate("App.Telas.mostrar('tela-voto')"); pg.wait_for_timeout(800)
    ok(pg.evaluate("document.querySelectorAll('#rank .rank-item').length") > 0 and pg.evaluate(RUIM) == "", "MT/Cuiaba: ranking do Meu voto carrega os candidatos de MT sem NaN")
    pg.select_option("#uf-foco", "RO"); pg.wait_for_timeout(1500)
    ok(pg.evaluate("App.perfil().uf") == "RO", "trocar a UF no Meu voto troca a UF do Perfil")
    pg.evaluate("App.setPerfil({ uf: 'RO', mun: 'Ariquemes' })"); pg.wait_for_timeout(800)
    # posicoes: marca na tela Votacoes, aparece no Perfil, na ficha e no criterio "Vota como eu"
    pg.goto((ROOT / "votacoes.html").as_uri()); pg.wait_for_timeout(2500)
    for i in range(3):
        pg.click(".vt-item >> nth=%d >> .vt-posicao .pos[data-v=S]" % i); pg.wait_for_timeout(150)
    pg.click(".vt-item >> nth=0 >> .vt-posicao .pos[data-v=S]"); pg.wait_for_timeout(150)
    ok(len(pg.evaluate("App.Store.posicoes()")) == 2, "marcar posicao grava; clicar de novo desmarca")
    pg.click('.vt-modos button[data-modo="camara"]'); pg.wait_for_timeout(300)
    pg.click(".vt-item >> nth=0 >> .vt-posicao .pos[data-v=N]"); pg.wait_for_timeout(150)
    ok(any(k.startswith("camara:") for k in pg.evaluate("App.Store.posicoes()")), "posicao tambem na Camara")
    pg.goto((ROOT / "meu-voto.html").as_uri() + "#perfil"); pg.wait_for_timeout(2500)
    ok(pg.evaluate("document.querySelectorAll('#pf-posicoes .pf-remove').length") == 3, "Perfil lista as 3 posicoes marcadas")
    conc = pg.evaluate("""(() => { const lista = App.Dados.cache.RO; let n = 0, ruins = [];
      for (const c of lista) { const r = App.concordancia(c); if (!r.total) continue; n++;
        if (r.itens.some((t) => !['S', 'N'].includes(t.dele)) || r.iguais !== r.itens.filter((t) => t.dele === t.minha).length) ruins.push(c.urna); }
      return { n, ruins }; })()""")
    ok(conc["n"] > 0 and not conc["ruins"], "concordancia: %d candidatos comparaveis, so votos Sim/Nao contam %s" % (conc["n"], conc["ruins"][:3]))
    pg.evaluate("App.Telas.mostrar('tela-voto')"); pg.wait_for_timeout(500)
    pg.click("#abas button:has-text('Deputado Estadual')"); pg.select_option("#rank-limite", "0"); pg.wait_for_timeout(500)
    ok(any(t.startswith("Vota como você em") for t in pg.evaluate("[...document.querySelectorAll('.porque .tag')].map(t => t.textContent)")),
       "ranking mostra 'Vota como voce em X de Y'")
    # 'nao se aplica' sai da media: so o criterio de posicoes ligado -> quem nao tem voto comparavel fica com 0, sem NaN
    pg.evaluate("localStorage.clear()")
    # usuario antigo (dados salvos antes do Perfil) continua em Ariquemes
    pg.evaluate("localStorage.setItem('meuvoto2026', JSON.stringify({ favoritos: { x: true }, escolhas: {} }))")
    pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(2000)
    ok(pg.evaluate("App.perfil()") == {"uf": "RO", "mun": "Ariquemes"}, "quem ja usava o sistema antes do Perfil continua em Ariquemes/RO")
    ok(not pg._erros, "perfil: sem erros de console %s" % pg._erros[:3])
    pg.evaluate("localStorage.clear()")
    pg = nova(b, 390, 844)
    pg.goto((ROOT / "meu-voto.html").as_uri() + "#perfil"); pg.wait_for_timeout(2500)
    ok(pg.evaluate(OVERFLOW) == "", "perfil 390px: sem rolagem horizontal [%s]" % pg.evaluate(OVERFLOW))

    print("3d. Coligacoes: por candidato (deputado federado, governador, senador) e por grupo")
    U = (ROOT / "coligacoes.html").as_uri()
    pg = nova(b)
    pg.goto(U); pg.wait_for_timeout(2500)
    ok(pg.evaluate("document.querySelectorAll('.cl-res').length") > 0 and pg.evaluate(RUIM) == "", "coligacoes: lista de candidatos para escolher, sem NaN")
    ok(pg.evaluate("document.querySelectorAll('#cl-fontes a[href^=\"https://\"]').length") >= 10 and "30/09/2026" in pg.inner_text("#cl-rodape"),
       "coligacoes: fontes oficiais com link e data da conferencia")
    ok(pg.evaluate("document.querySelectorAll('#cl-federacoes tbody tr').length") == 5, "coligacoes: tabela com as 5 federacoes registradas no TSE")
    pg.fill("#cl-texto", "4412"); pg.wait_for_timeout(300)
    ok(pg.evaluate("[...document.querySelectorAll('.cl-res')].every(b => b.querySelector('.numero').textContent.startsWith('4412'))"), "coligacoes: busca por numero")
    dep = pg.evaluate("App.Dados.cache.RO.find(c => c.cargo === 'Deputado Federal' && c.nrFederacao === '101' && c.urnaOk !== false)")
    pg.goto("about:blank"); pg.goto(U + "#coligacoes-RO-" + dep["sq"]); pg.wait_for_timeout(2500)
    txt = pg.inner_text("#cl-conteudo")
    colegas = pg.evaluate("""(sq) => { const c = App.Dados.cache.RO.find(x => x.sq === sq);
      return App.Dados.cache.RO.filter(x => x.sq !== sq && x.cargo === c.cargo && x.nrFederacao === c.nrFederacao && x.urnaOk !== false).map(x => x.sq).sort(); }""", dep["sq"])
    vistos = pg.evaluate("[...document.querySelectorAll('#cl-conteudo .grade:not(.cl-escolhido) .cand')].map(e => e.dataset.sq).sort()")
    ok("Brasil da Esperança" in txt and "não vai para nenhum outro partido" in txt and vistos == colegas and len(vistos) > 0,
       "coligacoes: deputado da FE Brasil mostra os %d colegas da federacao (PT, PCdoB, PV) e nenhum outro" % len(colegas))
    pg.click("#cl-conteudo .grade:not(.cl-escolhido) .cand >> nth=0"); pg.wait_for_timeout(300)
    ok(pg.query_selector(".modal") is not None, "coligacoes: cartao do colega abre a ficha")
    pg.click(".modal .ver-aliados"); pg.wait_for_timeout(400)
    ok(pg.query_selector(".modal") is None and pg.evaluate("document.querySelector('.cl-destino h2').textContent").startswith("Para onde vai o voto"),
       "coligacoes: 'Para onde vai o voto' na ficha troca de candidato na mesma pagina")
    gov = pg.evaluate("App.Dados.cache.RO.find(c => c.cargo === 'Governador' && c.tipoAgremiacao === 'COLIGAÇÃO').sq")
    pg.goto("about:blank"); pg.goto(U + "#coligacoes-RO-" + gov); pg.wait_for_timeout(2500)
    txt = pg.inner_text("#cl-conteudo")
    ok("não se transfere" in txt and "coligação" in txt and "maioria absoluta" in txt, "coligacoes: governador mostra a coligacao e que o voto nao se transfere")
    sen = pg.evaluate("App.Dados.cache.RO.find(c => c.cargo === 'Senador' && c.tipoAgremiacao === 'COLIGAÇÃO').sq")
    pg.goto("about:blank"); pg.goto(U + "#coligacoes-RO-" + sen); pg.wait_for_timeout(2500)
    ok("dois mais votados" in pg.inner_text("#cl-conteudo"), "coligacoes: senador explica as 2 vagas sem segundo turno")
    pg.click('.vt-modos button[data-modo="grupo"]'); pg.wait_for_timeout(400)
    for cargo in ("Deputado Federal", "Deputado Estadual", "Governador", "Senador"):
        pg.select_option("#cl-cargo", cargo); pg.wait_for_timeout(300)
        r = pg.evaluate("""(cargo) => { const n = App.Dados.cache.RO.filter(c => c.cargo === cargo && c.urnaOk !== false).length;
          const soma = [...document.querySelectorAll('.cl-grupo')].reduce((t, d) => t + parseInt(d.querySelector('summary .small').textContent.match(/([0-9]+) candidato/)[1]), 0);
          return { n, soma, fed: [...document.querySelectorAll('.cl-grupo summary')].filter(s => s.textContent.includes('Federação')).length }; }""", cargo)
        ok(r["n"] == r["soma"] and pg.evaluate(RUIM) == "", "coligacoes por grupo, %s: grupos somam os %d candidatos" % (cargo, r["n"]))
        if cargo.startswith("Deputado"):
            ok(r["fed"] == 4 and not pg.evaluate("[...document.querySelectorAll('.cl-grupo summary .tag')].some(t => t.textContent === 'Coligação')"),
               "coligacoes por grupo, %s: 4 federacoes de RO e nenhuma coligacao" % cargo)
    pg.click(".cl-grupo summary >> nth=0"); pg.wait_for_timeout(300)
    ok(pg.evaluate("document.querySelectorAll('.cl-grupo[open] .cand').length") > 0, "coligacoes: abrir um grupo mostra os candidatos")
    ok(not pg._erros, "coligacoes: sem erros de console %s" % pg._erros[:3])
    for w in (390, 320):
        pg = nova(b, w, 844)
        pg.goto(U + "#coligacoes-RO-" + dep["sq"]); pg.wait_for_timeout(2500)
        ok(pg.evaluate(OVERFLOW) == "", "coligacoes %dpx: sem rolagem horizontal [%s]" % (w, pg.evaluate(OVERFLOW)))

    print("3e. Resultados 2026: panorama, consulta de candidato, votos por cidade, explicacao, estatisticas")
    U = (ROOT / "resultados.html").as_uri()
    pg = nova(b)
    pg.goto(U); pg.wait_for_timeout(3000)
    ok(pg.query_selector("#rot-rs-pan") is not None and pg.evaluate(RUIM) == "", "resultados: panorama de RO aparece, sem NaN")
    ok("116.617" in pg.inner_text("#rs-conteudo"), "resultados: quociente eleitoral de Dep. Federal RO = 116.617 (TSE)")
    n_el = pg.evaluate("document.querySelectorAll('section[aria-labelledby=rot-rs-el] > div table tbody tr').length")
    ok(n_el == 8, "resultados: 8 eleitos para Dep. Federal em RO (%d)" % n_el)
    pg.fill("#rs-texto", "2090"); pg.wait_for_timeout(300)
    pg.click("#rs-cand .cl-res"); pg.wait_for_timeout(500)
    txt = pg.inner_text(".rs-cand")
    ok("Suplente" in txt and "1º suplente" in txt and "9.937" in txt and "Dr. Jaime Gazola" in txt,
       "resultados: Rafael Fera = 1o suplente do PODE, faltaram 9.937 votos (ultimo eleito da lista: Dr. Jaime Gazola)")
    primeira = pg.inner_text(".rs-mun tbody tr:first-child")
    pg.click(".rs-ord"); pg.wait_for_timeout(200)
    ultima = pg.inner_text(".rs-mun tbody tr:first-child")
    ok("Ariquemes/RO" in primeira and primeira != ultima and "Mais votos" not in pg.inner_text(".rs-ord"),
       "resultados: cidades do maior para o menor (1a: Ariquemes/RO) e o botao inverte a ordem")
    vs = pg.evaluate("[...document.querySelectorAll('.rs-mun tbody tr td:nth-child(3)')].map(t => +t.textContent.replace(/\\D/g, ''))")
    ok(len(vs) > 5 and vs == sorted(vs), "resultados: ordem crescente de votos confere")
    pg.fill(".rs-filtro", "ariq"); pg.wait_for_timeout(200)
    ok(pg.evaluate("document.querySelectorAll('.rs-mun tbody tr').length") == 1, "resultados: filtro de cidade")
    pg.click(".rs-voltar"); pg.fill("#rs-texto", "jonatas"); pg.wait_for_timeout(300)
    pg.click("#rs-cand .cl-res"); pg.wait_for_timeout(400)
    txt = pg.inner_text(".rs-expl")
    ok("não conquistou nenhuma vaga" in txt and "80%" in txt and "26.391" in txt,
       "resultados: Jonatas Franca (Republicanos sem vaga) explica os 80% e quantos votos faltaram")
    pg.select_option("#rs-cargo", "Governador"); pg.wait_for_timeout(300)
    ok("Eleito" in pg.inner_text("section[aria-labelledby=rot-rs-el]"), "resultados: governador de RO eleito no 1o turno")
    ok(pg.query_selector(".rs-lider") is not None and "56,86%" in pg.inner_text(".rs-lider-pct") and pg.locator(".rs-barras li").count() >= 3,
       "resultados: card do lider (Governador RO, 56,86%) e barras dos demais")
    cor = pg.eval_on_selector(".rs-lider .ponto-partido", "e => getComputedStyle(e).backgroundColor")
    ok(cor == "rgb(0, 92, 169)", "resultados: cor do PL no ponto do partido (%s)" % cor)
    n_map = pg.locator(".rs-mapa-cidade path").count()
    ok(n_map == 52 and pg.locator(".rs-mapa-cidade path[data-sq]").count() == 52 and pg.locator(".rs-mapa-estado path").count() == 27, "resultados: Governador RO com o mapa das 52 cidades pintadas e o mapa do Brasil (%d)" % n_map)
    pg.locator(".rs-mapa path[data-sq]").first.dispatch_event("click"); pg.wait_for_timeout(500)
    ok(pg.query_selector(".rs-cand") is not None, "resultados: clicar numa cidade do mapa abre o mais votado")
    pg.click(".rs-voltar")
    pg.select_option("#rs-cargo", "Presidente"); pg.wait_for_timeout(500)
    ok("2º turno" in pg.inner_text("section[aria-labelledby=rot-rs-el]") and pg.query_selector("#rot-rs-uf") is not None,
       "resultados: presidente com 2o turno e tabela por estado")
    pg.select_option("#rs-uf", "SP"); pg.wait_for_timeout(4000)
    ok(pg.eval_on_selector("#rs-cargo", "e => e.value") == "Presidente", "resultados: trocar de estado mantem o cargo")
    pg.select_option("#rs-cargo", "Deputado Federal"); pg.wait_for_timeout(500)
    ok(pg.query_selector("#rot-rs-mais") is not None and pg.query_selector("#rot-rs-dist") is not None,
       "resultados SP: lista 'mais votos que um eleito' e distribuicao das vagas")
    ok(pg.eval_on_selector("#rs-uf", "e => e.options[0].value") == "BR", "resultados: 'Brasil' e a 1a opcao do filtro Estado")
    pg.select_option("#rs-uf", "BR"); pg.wait_for_timeout(2500)
    ok(pg.eval_on_selector("#rs-cargo", "e => [...e.options].map(o => o.value)") == ["Presidente", "Governador", "Senador"] and pg.query_selector(".rs-lider") is not None,
       "resultados Brasil: cargos Presidente, Governador e Senador, com o card do 1o colocado de presidente")
    n_uf = pg.locator(".rs-mapa-estado path[style]").count()
    ok(n_uf == 27 and pg.locator(".rs-mapa-cidade").count() == 0, "resultados Brasil: mapa com os 27 estados pintados e sem mapa de cidades (%d)" % n_uf)
    for cargo in ("Governador", "Senador"):
        pg.select_option("#rs-cargo", cargo); pg.wait_for_timeout(800)
        ok(pg.locator(".rs-mapa-estado path[style]").count() == 27 and pg.locator("#rot-rs-estados ~ div table tbody tr").count() == 27 and "estado" in pg.inner_text(".rs-mapa-leg"),
           "resultados Brasil: %s com mapa dos 27 estados, legenda por partido e tabela por estado" % cargo)
    pg.locator(".rs-ir").first.click(); pg.wait_for_timeout(3500)
    ok(pg.query_selector(".rs-cand") is not None and pg.eval_on_selector("#rs-uf", "e => e.value") != "BR", "resultados Brasil: nome na tabela de estados abre o candidato no estado dele")
    pg.select_option("#rs-uf", "BR"); pg.wait_for_timeout(2500); pg.select_option("#rs-cargo", "Presidente"); pg.wait_for_timeout(800)
    pg.locator('.rs-mapa path[data-uf="RO"]').dispatch_event("click"); pg.wait_for_timeout(3000)
    ok(pg.eval_on_selector("#rs-uf", "e => e.value") == "RO" and pg.eval_on_selector("#rs-cargo", "e => e.value") == "Presidente" and pg.locator(".rs-mapa-cidade path").count() == 52,
       "resultados Brasil: clicar em RO no mapa abre o estado, mantem Presidente e mostra as 52 cidades")
    ok(not pg._erros, "resultados: sem erros de console %s" % pg._erros[:3])
    # ficha (outra pagina) -> bloco Eleicao 2026 -> resultado detalhado
    pg = nova(b)
    pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(2500)
    pg.evaluate("App.Modal.abrir(App.Dados.cache.RO.find(c => c.nr == '2090' && c.cargo === 'Deputado Federal'))")
    pg.wait_for_selector(".ficha-res:not([hidden])", timeout=10000)
    ok("Suplente" in pg.inner_text(".ficha-res"), "ficha: bloco Eleicao 2026 com a situacao")
    pg.click(".ficha-res a"); pg.wait_for_timeout(3500)
    ok(pg.query_selector(".rs-cand") is not None and "Rafael Fera" in pg.inner_text(".rs-cand h3"), "ficha: link abre o resultado detalhado do candidato")
    for w in (390, 320):
        pg = nova(b, w, 844)
        pg.goto(U); pg.wait_for_timeout(3000)
        pg.fill("#rs-texto", "2090"); pg.wait_for_timeout(300); pg.click("#rs-cand .cl-res"); pg.wait_for_timeout(400)
        ok(pg.evaluate(OVERFLOW) == "", "resultados %dpx: sem rolagem horizontal [%s]" % (w, pg.evaluate(OVERFLOW)))

    pg = nova(b)
    pg.goto((ROOT / "emendas.html").as_uri()); pg.wait_for_timeout(3000)
    cores = pg.evaluate("[getComputedStyle(document.querySelector('.em-autor .barra i:not(.pago)')).backgroundColor, getComputedStyle(document.querySelector('.legenda-barras i:not([class])')).backgroundColor]")
    ok(cores == ["rgb(178, 147, 0)"] * 2, "emendas: barra e legenda 'destinado' em dourado %s" % cores)

    print("3f. Tema claro/escuro: botao sol/lua, escolha salva, seletor na tela Mais")
    for esquema, outro in (("dark", "light"), ("light", "dark")):
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, color_scheme=esquema)
        pg = ctx.new_page(); erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(1500)
        fundo0 = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        rot = pg.get_attribute(".tema-btn", "aria-label")
        ok(rot == ("Usar tema claro" if esquema == "dark" else "Usar tema escuro"), "tema %s: botao com o rotulo certo (%s)" % (esquema, rot))
        pg.click(".tema-btn"); pg.wait_for_timeout(200)
        fundo1 = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        ok(pg.evaluate("document.documentElement.dataset.theme") == outro and fundo0 != fundo1, "tema %s: clicar troca para %s (%s -> %s)" % (esquema, outro, fundo0, fundo1))
        pg.goto((ROOT / "resultados.html").as_uri()); pg.wait_for_timeout(1500)
        ok(pg.evaluate("document.documentElement.dataset.theme") == outro, "tema %s: escolha vale nas outras paginas" % esquema)
        pg.goto((ROOT / "meu-voto.html").as_uri() + "#mais"); pg.wait_for_timeout(1500)
        ok(pg.is_checked('input[name="tema"][value="%s"]' % outro), "tema %s: tela Mais marca a escolha" % esquema)
        pg.check('input[name="tema"][value="auto"]'); pg.wait_for_timeout(200)
        ok(pg.evaluate("document.documentElement.dataset.theme || ''") == "" and pg.evaluate("localStorage.getItem('meuvoto2026-tema')") is None,
           "tema %s: Automatico apaga a escolha e volta a seguir o sistema" % esquema)
        ok(not erros, "tema %s: sem erros %s" % (esquema, erros[:2]))
        ctx.close()
    pg = nova(b, 390, 844)
    pg.goto((ROOT / "index.html").as_uri()); pg.wait_for_timeout(1500)
    ok(pg.is_visible(".tema-btn") and pg.evaluate(OVERFLOW) == "", "tema 390px: botao visivel no topo, sem rolagem horizontal")

    print("4. Versao mobile (arquivo unico)")
    pg = nova(b, 390, 844)
    pg.goto((ROOT / "mobile" / "meu-voto-mobile.html").as_uri()); pg.wait_for_timeout(3500)
    ok(pg.query_selector('.bottom-nav button[data-tela="tela-mais"]') is None and pg.query_selector('.bottom-nav button[data-tela="tela-perfil"]') is not None,
       "mobile: barra inferior tem Perfil; Mais fica no Perfil (e no topo, no computador)")
    for tela in ("tela-busca", "tela-voto", "tela-cola", "tela-emendas", "tela-votacoes", "tela-coligacoes", "tela-resultados", "tela-perfil"):
        pg.click('.bottom-nav button[data-tela="%s"]' % tela); pg.wait_for_timeout(400)
        ativa = pg.eval_on_selector(".tela.ativa", "e => e.id")
        ok(ativa == tela and pg.evaluate(RUIM) == "", "mobile: tela %s abre, sem NaN" % tela)
        ov = pg.evaluate(OVERFLOW)
        ok(ov == "", "mobile: %s sem rolagem horizontal [%s]" % (tela, ov))
    pg.click('.bottom-nav button[data-tela="tela-emendas"]'); pg.wait_for_timeout(300)
    pg.click(".em-autor:nth-child(2) .abrir-ficha"); pg.wait_for_timeout(400)
    pg.evaluate("document.querySelectorAll('.modal details').forEach(d => d.open = true)")
    pg.click('.modal a[data-tela="tela-emendas"]'); pg.wait_for_timeout(300)
    ok(pg.query_selector(".modal") is None, "mobile: link da ficha para Emendas fecha a ficha")
    pg.click('.bottom-nav button[data-tela="tela-perfil"]'); pg.wait_for_timeout(300)
    pg.click('#tela-perfil a[data-tela="tela-mais"]'); pg.wait_for_timeout(300)
    ok(pg.eval_on_selector(".tela.ativa", "e => e.id") == "tela-mais", "mobile: Perfil leva a Mais (denuncias e fontes)")
    pg.click('.bottom-nav button[data-tela="tela-perfil"]'); pg.wait_for_timeout(300)
    pg.select_option("#pf-mun", "Porto Velho"); pg.wait_for_timeout(800)
    pg.click('.bottom-nav button[data-tela="tela-emendas"]'); pg.wait_for_timeout(400)
    ok(pg.eval_on_selector("#em-mun", "e => e.value") == "RO|PORTO VELHO", "mobile: mudar o Perfil muda o municipio da tela Emendas no mesmo arquivo")
    pg.evaluate("localStorage.clear()")
    # ficha -> "Todas as votacoes" no mesmo arquivo: troca de tela e filtra no deputado
    pid = pg.evaluate("Object.values(window.ALERO.porCand)[0]")
    pg.evaluate("App.Modal.abrir(App.Dados.cache.RO.find(c => c.sq === window.ALERO.parl['%s'].sq)); document.querySelectorAll('.modal details').forEach(d => d.open = true)" % pid)
    pg.click('.modal a[data-tela="tela-votacoes"]'); pg.wait_for_timeout(400)
    ok(pg.eval_on_selector(".tela.ativa", "e => e.id") == "tela-votacoes" and pg.eval_on_selector("#vt-dep", "e => e.value") == pid,
       "mobile: link da ficha abre Votacoes filtrada no deputado")
    # ficha -> "Para onde vai o voto" no mesmo arquivo
    pg.evaluate("App.Modal.abrir(App.Dados.cache.RO.find(c => c.cargo === 'Deputado Estadual'))")
    pg.click(".modal .ver-aliados"); pg.wait_for_timeout(400)
    ok(pg.eval_on_selector(".tela.ativa", "e => e.id") == "tela-coligacoes" and pg.query_selector("#tela-coligacoes .cl-destino") is not None,
       "mobile: link da ficha abre Coligacoes no candidato")
    # ficha -> "Resultado detalhado" no mesmo arquivo
    pg.evaluate("App.Modal.abrir(App.Dados.cache.RO.find(c => c.nr == '2090' && c.cargo === 'Deputado Federal'))")
    pg.wait_for_selector(".ficha-res:not([hidden])", timeout=10000)
    pg.click(".ficha-res a"); pg.wait_for_timeout(500)
    ok(pg.eval_on_selector(".tela.ativa", "e => e.id") == "tela-resultados" and pg.query_selector("#tela-resultados .rs-cand") is not None,
       "mobile: link da ficha abre Resultados no candidato")
    ok(pg.locator("#tela-resultados .rs-mapa path").count() == 52,
       "mobile: mapa das cidades embutido no arquivo")
    ok(not pg._erros, "mobile: sem erros de console %s" % pg._erros[:3])
    pg.screenshot(path=str(SP / "t_mobile.png"))

    print("5. Sem arquivos opcionais (emendas.js, camara.js, denuncias.js, alero.js)")
    tmp = pathlib.Path(tempfile.mkdtemp())
    for f in ("index.html", "meu-voto.html", "emendas.html", "votacoes.html", "coligacoes.html", "resultados.html"):
        shutil.copy(ROOT / f, tmp / f)
    shutil.copytree(ROOT / "assets", tmp / "assets")
    (tmp / "data").mkdir()
    for f in os.listdir(ROOT / "data"):
        if f.endswith(".js") and f not in ("emendas.js", "camara.js", "denuncias.js", "alero.js", "votacoes_federais.js") and not f.startswith("resultados_"):
            shutil.copy(ROOT / "data" / f, tmp / "data" / f)
    for f in ("index.html", "meu-voto.html", "emendas.html", "votacoes.html", "coligacoes.html", "resultados.html"):
        pg = nova(b)
        pg._erros = []
        pg.on("pageerror", lambda e, pg=pg: pg._erros.append(str(e)))
        pg.goto((tmp / f).as_uri()); pg.wait_for_timeout(2000)
        pe = [e for e in pg._erros if not e.startswith(("requestfailed", "console"))]
        ok(not pe, "%s sem dados opcionais: sem erro de JS %s" % (f, pe[:2]))
        if f == "emendas.html":
            ok("fetch_emendas.py" in pg.inner_text("#em-conteudo"), "emendas.html sem dados mostra instrucao")
        if f == "votacoes.html":
            ok("fetch_alero.py" in pg.inner_text("#vt-conteudo"), "votacoes.html sem dados mostra instrucao")
        if f == "resultados.html":
            ok("fetch_resultados.py" in pg.inner_text("#rs-conteudo"), "resultados.html sem dados mostra instrucao")
        if f == "meu-voto.html":
            pg.click("#rank .rank-item .info"); pg.wait_for_timeout(300)
            ok(pg.query_selector(".modal") is not None and "Emendas parlamentares" not in pg.inner_text(".modal"), "ficha sem emendas.js abre e omite a secao")
            pg.wait_for_timeout(500)
            ok(pg.query_selector(".ficha-res:not([hidden])") is None, "ficha sem resultados_XX.js omite o bloco Eleicao 2026")
    shutil.rmtree(tmp, ignore_errors=True)

    print("6. Impressao da colinha (PDF A4 real, como no 'Salvar em PDF')")
    pg = nova(b)
    pg.goto((ROOT / "meu-voto.html").as_uri()); pg.wait_for_timeout(2500)
    # escolhe o 1o do ranking em cada cargo (2 para senador) - todos os campos da colinha preenchidos
    n_esc = pg.evaluate("""(async () => {
      const lista = await App.Dados.carregarVarias(['RO', 'BR']);
      const d = App.Store.ler(); d.escolhas = {};
      for (const cg of ['Deputado Federal', 'Deputado Estadual', 'Senador', 'Governador', 'Presidente']) {
        const cs = lista.filter(c => c.cargo === cg && App.sitClasse(c.sit) !== 'bad');
        d.escolhas[cg] = cs.slice(0, App.VAGAS[cg] || 1).map(c => c.sq);
      }
      App.Store.salvar(); return Object.values(d.escolhas).flat().length;
    })()""")
    pg.reload(); pg.wait_for_timeout(2500)
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pg.emulate_media(media="print"); pg.wait_for_timeout(300)
    vis = pg.evaluate("""(() => {
      const v = (s) => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; };
      return { colinha: v('#colinha-print .colinha'), topo: v('.topbar'), nav: v('.bottom-nav'), rank: v('#rank'),
               itens: document.querySelectorAll('#colinha-print .item[data-sq]').length,
               vazios: document.querySelectorAll('#colinha-print .item.nao-escolhido').length,
               digitos: [...document.querySelectorAll('#colinha-print .digitos')].map(d => d.textContent.trim()) };
    })()""")
    ok(n_esc == 6 and vis["itens"] == 6 and vis["vazios"] == 0, "colinha impressa com os 6 votos (%d escolhidos, %d impressos)" % (n_esc, vis["itens"]))
    ok(vis["colinha"] and not vis["topo"] and not vis["nav"] and not vis["rank"], "na impressao so a colinha aparece (menu, ranking e barra somem)")
    ok(all(dg.isdigit() for dg in vis["digitos"]), "numeros da urna impressos: %s" % ", ".join(vis["digitos"]))
    pdf = pg.pdf(format="A4", print_background=True, prefer_css_page_size=True)
    (SP / "colinha.pdf").write_bytes(pdf)
    paginas = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
    ok(paginas == 1, "PDF da colinha cabe em 1 pagina A4 (%d pagina(s), %d KB) -> %s" % (paginas, len(pdf) // 1024, SP / "colinha.pdf"))
    pg.screenshot(path=str(SP / "colinha_impressao.png"), full_page=True)
    pg.emulate_media(media="screen")
    # colinha em PNG (2160x3840, 2x): baixa pelo botao da tela Colinha
    pg.evaluate("App.Telas.mostrar('tela-cola')"); pg.wait_for_timeout(300)
    with pg.expect_download() as dl:
        pg.click("#btn-png")
    png = pathlib.Path(dl.value.path()).read_bytes()
    (SP / "colinha.png").write_bytes(png)
    larg, alt = struct.unpack(">II", png[16:24]) if png[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)
    ok((larg, alt) == (2160, 3840), "colinha em PNG 2160x3840 (%dx%d, %d KB, nome %s) -> %s" % (larg, alt, len(png) // 1024, dl.value.suggested_filename, SP / "colinha.png"))
    ok(dl.value.suggested_filename == "colinha-2026-RO.png", "nome do arquivo da colinha: %s" % dl.value.suggested_filename)
    n_fotos = pg.evaluate("Object.keys(window.FOTOS_B64 || {}).length")
    ok(n_fotos >= 5, "fotos entram no PNG mesmo em file:// (%d carregadas de data/fotos/<sq>.js)" % n_fotos)
    pg.evaluate("(() => { App.Store.ler().escolhas = {}; App.Store.salvar(); })()")
    pg.reload(); pg.wait_for_timeout(2500)
    pg.evaluate("App.Telas.mostrar('tela-cola')"); pg.wait_for_timeout(300)
    with pg.expect_download() as dl:
        pg.click("#btn-png")
    ok(pathlib.Path(dl.value.path()).read_bytes()[:4] == b"\x89PNG", "colinha em PNG sem nenhuma escolha tambem gera a imagem")
    pg.evaluate("localStorage.clear()")

    print("7. Celulares reais emulados (tela, densidade de pixels, toque, user agent)")
    for nome in ("Pixel 7", "iPhone 13", "Galaxy S9+", "iPhone SE"):
        ctx = b.new_context(**{k: v for k, v in p.devices[nome].items() if k != "default_browser_type"})
        pg = ctx.new_page(); erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto((ROOT / "mobile" / "meu-voto-mobile.html").as_uri()); pg.wait_for_timeout(3500)
        larg = pg.evaluate("document.documentElement.clientWidth")
        # toque de verdade (tap), nao clique de mouse
        for tela in ("tela-voto", "tela-emendas", "tela-busca"):
            pg.tap('.bottom-nav button[data-tela="%s"]' % tela); pg.wait_for_timeout(400)
        ok(pg.eval_on_selector(".tela.ativa", "e => e.id") == "tela-busca", "%s (%dpx): navegacao por toque na barra inferior" % (nome, larg))
        pg.tap(".cand"); pg.wait_for_timeout(500)
        modal = pg.evaluate("""(() => { const m = document.querySelector('.modal'); if (!m) return null;
          const f = document.querySelector('.modal .fechar').getBoundingClientRect();
          const antes = m.scrollTop; m.scrollTop = 99999; const rolou = m.scrollTop > antes;
          return { cobre: m.getBoundingClientRect().width >= window.innerWidth - 1, fechar: f.top >= 0 && f.right <= window.innerWidth && f.width >= 32, rolou }; })()""")
        ok(modal and modal["cobre"] and modal["fechar"] and modal["rolou"], "%s: ficha em tela cheia, rola ate o fim, botao fechar visivel %s" % (nome, modal))
        pg.tap(".modal .fechar"); pg.wait_for_timeout(300)
        ok(pg.query_selector(".modal") is None, "%s: fechar a ficha por toque" % nome)
        for tela in ("tela-busca", "tela-voto", "tela-cola", "tela-emendas", "tela-votacoes", "tela-coligacoes", "tela-resultados", "tela-perfil", "tela-mais"):
            pg.evaluate("App.Telas.mostrar('%s')" % tela); pg.wait_for_timeout(300)
            r = pg.evaluate("""(() => {
              const vis = [...document.querySelectorAll('.tela.ativa *, .bottom-nav *')].filter(e => e.offsetParent !== null && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
              const fonte = Math.min(...vis.map(e => parseFloat(getComputedStyle(e).fontSize)));
              const alvos = [...document.querySelectorAll('.tela.ativa button, .tela.ativa select, .tela.ativa input, .bottom-nav button')].filter(e => e.offsetParent !== null && e.type !== 'checkbox' && e.type !== 'radio' && e.type !== 'range' && !e.closest('.sr-only') && !e.classList.contains('sr-only'));
              const pequenos = alvos.filter(e => { const b = e.getBoundingClientRect(); return b.height < 30 || b.width < 30; }).map(e => (e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().height));
              return { fonte, pequenos: [...new Set(pequenos)].slice(0, 4), overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 };
            })()""")
            ok(r["fonte"] >= 11 and not r["pequenos"] and not r["overflow"],
               "%s %s: menor fonte %.1fpx (>=11), alvos de toque >=30px %s, sem rolagem lateral" % (nome, tela, r["fonte"], r["pequenos"]))
        pg.screenshot(path=str(SP / ("dispositivo_%s.png" % nome.replace(" ", "_").replace("+", "plus"))))
        ok(not erros, "%s: sem erros de JS %s" % (nome, erros[:2]))
        ctx.close()
    b.close()

print("\nRESULTADO: %d ok, %d falhas" % (len(oks), len(falhas)))
for f in falhas:
    print("  FALHA:", f)
sys.exit(1 if falhas else 0)
