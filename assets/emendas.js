/* emendas.js — tela "Emendas": quem mandou recursos de emendas parlamentares para cada município */
(function () {
  'use strict';
  const { norm, normMun, esc, titulo, icone, fmtMoeda, fmtNum, fmtCurto, Dados, Modal, montarTopo, fotoHtml, perfil, munFoco } = window.App;
  montarTopo();
  window.App.Telas.iniciar('tela-emendas');
  const $ = (id) => document.getElementById(id);
  if (!$('tela-emendas')) return;
  const E = window.EMENDAS;
  const box = $('em-conteudo');
  if (!E) {
    box.innerHTML = '<div class="vazio" style="margin-top:16px">Dados de emendas ainda não gerados. Rode <code>python scripts/fetch_emendas.py</code> e recarregue a página.</div>';
    return;
  }

  const UF = (E.foco && E.foco.uf) || 'RO';
  const NIVEL_ROT = { fed: 'Federal', fav: 'Federal', est: 'Estadual' };
  const COLETIVA = /^(bancada|com\.|comissao|relator|sem informacao|lideranca)/;
  const coletiva = (autor) => COLETIVA.test(norm(autor));
  const destinadoItem = (x) => x.nv === 'est' ? Math.max(x.pv || 0, x.e || 0) : x.nv === 'fed' ? (x.e || 0) : 0;
  const pagoItem = (x) => x.nv === 'fav' ? (x.r || 0) : (x.p || 0);

  // candidatos 2026 (para foto, número e ficha)
  const candPorSq = {};
  const st = { mun: '', nivel: '', ano: '', soCand: false, coletivas: true, autor: null, limite: 60 };

  // ---------- filtros ----------
  const munKeys = Object.keys(E.porMun).filter((k) => k.startsWith(UF + '|'));
  const rotMun = (k) => { const n = k.split('|')[1]; return n ? titulo(n) : 'Nível estadual / sem município definido'; };
  // abre no município do Perfil (se for da UF que tem emendas por município)
  const chaveDoPerfil = () => (perfil().uf === UF && munKeys.find((k) => normMun(k.split('|')[1]) === normMun(munFoco()))) || null;
  const chaveFoco = chaveDoPerfil() || munKeys[0];
  const selMun = $('em-mun');
  selMun.innerHTML = munKeys.slice().sort((a, b) => (a === chaveFoco ? -1 : b === chaveFoco ? 1 : rotMun(a).localeCompare(rotMun(b), 'pt-BR')))
    .map((k) => `<option value="${esc(k)}">${esc(rotMun(k))} (${fmtNum(E.porMun[k].length)})</option>`).join('');
  st.mun = chaveFoco;
  selMun.value = st.mun;

  function preencherAnos() {
    const anos = [...new Set((E.porMun[st.mun] || []).map((x) => x.ano).filter(Boolean))].sort((a, b) => b - a);
    const sel = $('em-ano');
    sel.innerHTML = '<option value="">Todos os anos</option>' + anos.map((a) => `<option value="${a}">${a}</option>`).join('');
    if (st.ano && !anos.includes(+st.ano)) st.ano = '';
    sel.value = st.ano;
  }

  selMun.onchange = () => { st.mun = selMun.value; st.autor = null; st.limite = 60; preencherAnos(); render(); };
  $('em-nivel').onchange = (e) => { st.nivel = e.target.value; st.autor = null; render(); };
  $('em-ano').onchange = (e) => { st.ano = e.target.value; st.autor = null; render(); };
  $('em-so-cand').onchange = (e) => { st.soCand = e.target.checked; st.autor = null; render(); };
  $('em-com-coletivas').onchange = (e) => { st.coletivas = e.target.checked; st.autor = null; render(); };

  // ---------- dados filtrados ----------
  function itensFiltrados() {
    return (E.porMun[st.mun] || []).filter((x) => {
      if (st.nivel === 'fed' && x.nv === 'est') return false;
      if (st.nivel === 'est' && x.nv !== 'est') return false;
      if (st.ano && String(x.ano) !== st.ano) return false;
      if (st.soCand && !x.sq) return false;
      if (!st.coletivas && coletiva(x.a)) return false;
      return true;
    });
  }
  const chaveAutor = (x) => x.sq || 'a:' + norm(x.a);

  function agruparPorAutor(itens) {
    const g = {};
    for (const x of itens) {
      const k = chaveAutor(x);
      const a = g[k] || (g[k] = { k, sq: x.sq, nomes: new Set(), destFed: 0, pagoFed: 0, rec: 0, destEst: 0, pagoEst: 0, n: 0, niveis: new Set(), coletiva: coletiva(x.a) });
      a.nomes.add(x.a); a.n++; a.niveis.add(NIVEL_ROT[x.nv]);
      if (x.nv === 'fed') { a.destFed += x.e || 0; a.pagoFed += x.p || 0; }
      else if (x.nv === 'fav') a.rec += x.r || 0;
      else { a.destEst += destinadoItem(x); a.pagoEst += x.p || 0; }
    }
    return Object.values(g).map((a) => {
      // no federal, "empenhado para o município" e "recebido pelos favorecidos" são duas visões do mesmo dinheiro: vale o maior
      a.destinado = Math.max(a.destFed, a.rec) + a.destEst;
      a.pago = Math.max(a.pagoFed, a.rec) + a.pagoEst;
      return a;
    }).sort((a, b) => b.destinado - a.destinado || b.pago - a.pago);
  }

  // ---------- render ----------
  function nomeAutor(a) {
    const c = a.sq && candPorSq[a.sq];
    const nomes = [...new Set([...a.nomes].map((x) => x.replace(/\s*\(.*$/, '')))];
    if (c) return { titulo: titulo(c.urna), sub: `${c.cargo} · ${c.nr} · ${c.partido}${nomes.length && norm(nomes[0]) !== norm(c.urna) ? ' · na fonte: ' + nomes.map(titulo).join(', ') : ''}`, c };
    if (a.coletiva) return { titulo: titulo(nomes[0]), sub: 'Emenda coletiva (sem autor individual)' };
    return { titulo: titulo(nomes[0]), sub: a.sq ? 'Candidato em 2026 (outro estado)' : 'Não é candidato em 2026' };
  }

  function linhaItem(x, comAutor) {
    const c = x.sq && candPorSq[x.sq];
    const autor = c ? titulo(c.urna) : titulo(x.a);
    const detalhe = x.nv === 'fav'
      ? `Recebido por <b>${esc(titulo(x.fav))}</b>${x.npf ? ' (' + fmtNum(x.npf) + ' pagamentos)' : ''}`
      : `${x.f ? '<b>' + esc(titulo(x.f)) + '</b> · ' : ''}${esc(x.o || '')}${x.fav ? '<br><span class="muted">Beneficiário: ' + esc(x.fav) + '</span>' : ''}${x.inf ? ' <span class="tag warn">município pela descrição</span>' : ''}`;
    return `<tr><td class="num ano">${x.ano || ''}</td>
      <td class="origem"><span class="tag ${x.nv === 'est' ? 'cargo' : 'plain'} nv">${NIVEL_ROT[x.nv]}</span><span class="small muted"> ${esc(x.t || '')}</span></td>
      ${comAutor ? `<td class="autor">${esc(autor)}</td>` : ''}
      <td class="obj small">${detalhe}</td>
      <td class="r num valor" data-rot="Destinado">${destinadoItem(x) ? fmtMoeda(destinadoItem(x)) : '—'}</td>
      <td class="r num valor" data-rot="Pago">${pagoItem(x) ? fmtMoeda(pagoItem(x)) : '—'}</td></tr>`;
  }
  const cabecalho = (comAutor) => `<thead><tr><th>Ano</th><th>Origem</th>${comAutor ? '<th>Autor</th>' : ''}<th>Objeto / área / quem recebeu</th><th class="r">Destinado</th><th class="r">Pago</th></tr></thead>`;

  function render() {
    const itens = itensFiltrados();
    const autores = agruparPorAutor(itens);
    const nomeMun = rotMun(st.mun);
    const totDest = autores.reduce((s, a) => s + a.destinado, 0);
    const totPago = autores.reduce((s, a) => s + a.pago, 0);
    const nCand = autores.filter((a) => a.sq && candPorSq[a.sq]).length;
    const max = Math.max(1, ...autores.map((a) => Math.max(a.destinado, a.pago)));

    const rank = autores.map((a, i) => {
      const n = nomeAutor(a);
      return `<div class="em-autor ${a.sq ? '' : 'sem-cand'}" data-k="${esc(a.k)}" aria-pressed="${st.autor === a.k}">
        <div class="pos">${i + 1}</div>
        ${n.c ? fotoHtml(n.c, 'mini') : `<div class="foto vazia mini" aria-hidden="true">${icone(a.coletiva ? 'predio' : 'pessoa')}</div>`}
        <div style="min-width:0">
          <div class="nm">${esc(n.titulo)}${a.sq ? '<span class="tag local">Candidato 2026</span>' : ''}<span class="tag plain">${[...a.niveis].join(' + ')}</span></div>
          <div class="sub">${esc(n.sub)} · ${fmtNum(a.n)} registro(s)</div>
          <div class="barras" aria-hidden="true">
            <div class="barra"><i style="width:${Math.round(100 * a.destinado / max)}%"></i></div>
            <div class="barra"><i class="pago" style="width:${Math.round(100 * a.pago / max)}%"></i></div>
          </div>
          <div class="acoes-autor">
            <button type="button" class="btn mini ver-itens" aria-expanded="${st.autor === a.k}" aria-controls="em-det-${i}">${icone('lista')}${st.autor === a.k ? 'Ocultar emendas' : 'Ver emendas (' + fmtNum(a.n) + ')'}</button>
            ${n.c ? `<button type="button" class="btn mini abrir-ficha">${icone('pessoa')}Ficha</button>` : ''}
          </div>
        </div>
        <div class="val">${fmtCurto(a.destinado)}<small>destinado</small>${fmtCurto(a.pago)}<small>pago/recebido</small></div>
      </div>${st.autor === a.k ? `
      <div class="em-detalhe" id="em-det-${i}" role="region" aria-label="Emendas de ${esc(n.titulo)}">
        <div class="resumo" style="margin:0 0 8px"><b>Emendas de ${esc(n.titulo)} para ${esc(nomeMun)} <span class="muted small">(${fmtNum(a.n)})</span></b>
          <button type="button" class="btn mini fechar-det">${icone('fechar')}Fechar</button></div>
        <div style="overflow-x:auto"><table class="tabela em-itens">${cabecalho(false)}<tbody>${itens.filter((x) => chaveAutor(x) === a.k).map((x) => linhaItem(x, false)).join('')}</tbody></table></div>
      </div>` : ''}`;
    }).join('');

    const lista = itens;
    const linhas = lista.slice(0, st.limite).map((x) => linhaItem(x, true)).join('');

    box.innerHTML = `
      <div class="em-kpis">
        <div class="em-kpi"><b>${fmtCurto(totDest)}</b><span>destinados a ${esc(nomeMun)}</span></div>
        <div class="em-kpi"><b>${fmtCurto(totPago)}</b><span>pagos / recebidos</span></div>
        <div class="em-kpi"><b>${fmtNum(autores.length)}</b><span>autores (parlamentares e bancadas)</span></div>
        <div class="em-kpi"><b>${fmtNum(nCand)}</b><span>deles são candidatos em ${esc(UF)} em 2026</span></div>
      </div>
      ${autores.length ? `
      <div class="resumo"><h2 style="margin:0">Quem mandou recursos para ${esc(nomeMun)}</h2>
        <div class="legenda-barras"><span><i></i>destinado</span><span><i class="pago"></i>pago / recebido</span></div></div>
      <div class="em-rank">${rank}</div>
      <div class="resumo"><h2 style="margin:0">Todas as emendas para ${esc(nomeMun)} <span class="muted small">(${fmtNum(lista.length)})</span></h2></div>
      <div class="card" style="padding:0;overflow-x:auto"><table class="tabela em-itens">${cabecalho(true)}<tbody>${linhas}</tbody></table></div>
      ${lista.length > st.limite ? `<div class="linha" style="justify-content:center;margin-top:10px"><button type="button" class="btn" id="em-mais">Mostrar mais (${fmtNum(lista.length - st.limite)} restantes)</button></div>` : ''}`
      : '<div class="vazio" style="margin-top:16px">Nenhuma emenda com esses filtros.</div>'}
      <p class="small muted" style="margin-top:10px">Dados de ${esc(E.atualizado || '')}. Federal: Portal da Transparência (CGU), desde 2014. Estadual: Transparência RO, desde 2023.</p>`;

    box.querySelectorAll('.em-autor').forEach((it) => {
      const k = it.dataset.k;
      it.querySelector('.ver-itens').onclick = () => { alternarAutor(k); };
      const f = it.querySelector('.abrir-ficha');
      if (f) f.onclick = () => { const a = autores.find((x) => x.k === k); Modal.abrir(candPorSq[a.sq]); };
    });
    box.querySelectorAll('.fechar-det').forEach((b) => b.onclick = () => alternarAutor(st.autor));
    const mais = $('em-mais'); if (mais) mais.onclick = () => { st.limite += 100; render(); };
  }

  // abre/fecha as emendas do autor logo abaixo do card dele (sanfona) e mantem o card na tela
  function alternarAutor(k) {
    st.autor = st.autor === k ? null : k;
    render();
    const card = [...box.querySelectorAll('.em-autor')].find((e) => e.dataset.k === k);
    if (!card) return;
    const btn = card.querySelector('.ver-itens');
    if (btn) btn.focus({ preventScroll: true });
    card.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  // Perfil mudou (no celular tudo roda no mesmo documento): abre no novo município, se houver emendas para ele
  document.addEventListener('perfil:mudou', () => {
    const k = chaveDoPerfil(); if (!k) return;
    st.mun = k; selMun.value = k; st.autor = null; st.limite = 60; preencherAnos(); render();
  });

  preencherAnos();
  render();
  // carrega os candidatos (foto, número, ficha) e redesenha
  const m = Dados.manifest();
  Dados.carregarVarias([UF, 'BR'].filter((u) => m.ufs.includes(u))).then((lista) => {
    lista.forEach((c) => { candPorSq[c.sq] = c; });
    render();
  });
})();
