/* votacoes.js — tela "Votações", sem juízo de valor. Modos:
   "nominal" (ALE-RO): votações com o voto de cada deputado estadual;
   "leis"    (ALE-RO): leis decididas em plenário sem voto individual registrado (votação simbólica);
   "camara" / "senado": votações nominais dos candidatos de RO que são ou foram deputados federais / senadores. */
(function () {
  'use strict';
  const { norm, esc, titulo, icone, fmtNum, Dados, Store, Modal, montarTopo, VOTO_ROT, votoTag, votoTagTexto, CASAS, fmtData, nomeMateria, linkMateria, ehVeto, LEGENDA_VETO, avisoPlacar } = window.App;
  // "#votacoes-123" / "#votacoes-camara-123" (vindo da ficha em outra página) = abrir filtrado no parlamentar;
  // lido antes de Telas.iniciar, que troca o hash por "#votacoes"
  const doHash = () => { const m = location.hash.match(/^#votacoes-(?:(camara|senado)-)?(\d+)/); return m ? { casa: m[1] || 'alero', dep: m[2] } : null; };
  const inicial = doHash();
  window.addEventListener('hashchange', () => { const h = doHash(); if (h) { window.App.votacoesDep = h.dep; window.App.votacoesCasa = h.casa; document.dispatchEvent(new CustomEvent('tela:mudou', { detail: { id: 'tela-votacoes' } })); } });
  montarTopo();
  window.App.Telas.iniciar('tela-votacoes');
  const $ = (id) => document.getElementById(id);
  if (!$('tela-votacoes')) return;
  const A = window.ALERO, F = window.VOTFED;
  const box = $('vt-conteudo');
  if (!A && !F) {
    box.innerHTML = '<div class="vazio" style="margin-top:16px">Dados de votações ainda não gerados. Rode <code>python scripts/fetch_alero.py</code> e <code>python scripts/fetch_votacoes_federais.py</code> e recarregue a página.</div>';
    return;
  }
  const LEIS = (A && A.leis) || [];
  const candPorSq = {};

  // ---------- fontes de votações nominais ----------
  const ORDEM_ALERO = ['S', 'N', 'A', 'U', 'X', '?'];
  const FONTES = {};
  if (A) FONTES.nominal = {
    vot: A.vot, parl: A.parl, votoHtml: votoTag, rot: (v) => VOTO_ROT[v] || v, link: linkMateria, nome: nomeMateria,
    ordem: (cont) => ORDEM_ALERO.filter((k) => cont[k]), parcial: false,
    rotParl: 'deputados com voto registrado',
    rodape: () => `Dados do SAPL da ALE-RO, baixados em ${fmtData(A.atualizado)}. Última votação lançada: ${fmtData(A.ultimaVotacao)}.`,
  };
  ['camara', 'senado'].forEach((casa) => {
    const C = F && F[casa];
    if (!C || !C.vot.length) return;
    FONTES[casa] = {
      vot: C.vot, parl: C.parl, votoHtml: votoTagTexto, rot: (v) => v, link: CASAS[casa].link, nome: (x) => x.ident || nomeMateria(x) || 'Votação',
      ordem: (cont) => Object.keys(cont).sort((a, b) => (b === 'Sim') - (a === 'Sim') || (b === 'Não') - (a === 'Não') || cont[b] - cont[a]), parcial: true,
      rotParl: casa === 'camara' ? 'candidatos de RO que são ou foram deputados federais' : 'candidatos de RO que são ou foram senadores',
      rodape: () => `Dados abertos ${CASAS[casa].daCasa}, desde ${C.desde}, baixados em ${fmtData(F.atualizado)}. Última votação com candidato de RO: ${fmtData(C.ultimaVotacao)}. Só aparecem os votos dos candidatos de RO em 2026; o placar é o da votação inteira.`,
    };
  });
  const MODOS = [...Object.keys(FONTES), ...(LEIS.length ? ['leis'] : [])];
  document.querySelectorAll('.vt-modos button').forEach((b) => { if (!MODOS.includes(b.dataset.modo)) b.hidden = true; });

  const casaInicial = inicial && FONTES[inicial.casa === 'alero' ? 'nominal' : inicial.casa] ? (inicial.casa === 'alero' ? 'nominal' : inicial.casa) : MODOS[0];
  const st = { modo: casaInicial, texto: '', dep: '', tipo: '', ano: '', materia: null, aberta: null, limite: 40 };
  if (inicial && FONTES[st.modo] && FONTES[st.modo].parl[inicial.dep]) st.dep = inicial.dep;
  const fonte = () => FONTES[st.modo];
  const parlAtual = () => (st.modo === 'leis' ? (A ? A.parl : {}) : fonte().parl);
  const nomeParl = (pid, parl = parlAtual()) => titulo((parl[pid] || {}).n || pid);
  const reiniciar = () => { st.limite = 40; st.aberta = null; };

  // ---------- filtros ----------
  function preencherDeputados() {
    const parl = parlAtual();
    const pids = Object.keys(parl).sort((a, b) => nomeParl(a).localeCompare(nomeParl(b), 'pt-BR'));
    const rot = (pid) => { const c = candPorSq[parl[pid].sq]; return nomeParl(pid) + (c ? ` — ${c.cargo} ${c.nr}` : ''); };
    const cand = pids.filter((p) => parl[p].sq), outros = pids.filter((p) => !parl[p].sq);
    $('vt-dep').innerHTML = '<option value="">Todos</option>'
      + `<optgroup label="Candidatos em 2026 (${cand.length})">${cand.map((p) => `<option value="${p}">${esc(rot(p))}</option>`).join('')}</optgroup>`
      + (outros.length ? `<optgroup label="Outros deputados (${outros.length})">${outros.map((p) => `<option value="${p}">${esc(rot(p))}</option>`).join('')}</optgroup>` : '');
    if (!parl[st.dep]) st.dep = '';
    $('vt-dep').value = st.dep;
  }
  function preencherTiposAnos() {
    const base = st.modo === 'leis' ? LEIS : fonte().vot;
    const tipos = [...new Set(base.map((x) => x.t).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    const anos = [...new Set(base.map((x) => (x.d || '').slice(0, 4)).filter(Boolean))].sort((a, b) => b - a);
    if (!tipos.includes(st.tipo)) st.tipo = '';
    if (!anos.includes(st.ano)) st.ano = '';
    $('vt-tipo').innerHTML = '<option value="">Todos os tipos</option>' + tipos.map((t) => `<option>${esc(t)}</option>`).join('');
    $('vt-ano').innerHTML = '<option value="">Todos os anos</option>' + anos.map((a) => `<option>${a}</option>`).join('');
    $('vt-tipo').value = st.tipo; $('vt-ano').value = st.ano;
    $('vt-rot-ano').textContent = st.modo === 'leis' ? 'Ano da decisão' : 'Ano da votação';
    $('vt-rot-dep').textContent = st.modo === 'leis' ? 'Deputado (autor ou declaração)' : st.modo === 'senado' ? 'Senador' : 'Deputado';
  }
  function mudarModo(m, extra = {}) {
    st.modo = m; st.materia = null; Object.assign(st, extra); reiniciar();
    document.querySelectorAll('.vt-modos button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === m)));
    preencherDeputados(); preencherTiposAnos(); render();
  }
  document.querySelectorAll('.vt-modos button').forEach((b) => b.onclick = () => mudarModo(b.dataset.modo));

  let tDigita;
  $('vt-texto').oninput = (e) => { clearTimeout(tDigita); tDigita = setTimeout(() => { st.texto = e.target.value; reiniciar(); render(); }, 200); };
  $('vt-dep').onchange = (e) => { st.dep = e.target.value; reiniciar(); render(); };
  $('vt-tipo').onchange = (e) => { st.tipo = e.target.value; reiniciar(); render(); };
  $('vt-ano').onchange = (e) => { st.ano = e.target.value; reiniciar(); render(); };

  function filtradas() {
    const f = fonte(), q = norm(st.texto);
    return f.vot.filter((x) => {
      if (st.materia && x.m !== st.materia) return false;
      if (st.dep && !x.v[st.dep]) return false;
      if (st.tipo && x.t !== st.tipo) return false;
      if (st.ano && !(x.d || '').startsWith(st.ano)) return false;
      if (q && !norm(`${x.e} ${x.desc || ''} ${f.nome(x)} ${x.n || ''}/${x.a || ''} ${x.r}`).includes(q)) return false;
      return true;
    });
  }
  const autoresTexto = (l) => l.aut.map((a) => a.parl && A.parl[a.parl] ? nomeParl(a.parl, A.parl) : titulo(a.nome)).join(', ');
  function leisFiltradas() {
    const q = norm(st.texto);
    return LEIS.filter((l) => {
      if (st.dep && !l.aut.some((a) => a.parl === st.dep) && !(l.decl || []).some((d) => d.parlamentar === st.dep)) return false;
      if (st.tipo && l.t !== st.tipo) return false;
      if (st.ano && !(l.d || '').startsWith(st.ano)) return false;
      if (q && !norm(`${l.e} ${nomeMateria(l)} ${l.n}/${l.a} ${l.lei || ''} ${autoresTexto(l)} ${l.txt}`).includes(q)) return false;
      return true;
    });
  }
  const contar = (x) => { const c = {}; Object.values(x.v).forEach((v) => { c[v] = (c[v] || 0) + 1; }); return c; };
  const botaoFicha = (c) => c ? ` <button type="button" class="btn mini abrir-ficha" data-sq="${esc(c.sq)}" aria-label="Abrir ficha de ${esc(titulo(c.urna))}">${icone('pessoa')}${esc(c.cargo)} ${esc(c.nr)}</button>` : '';

  // ---------- render: votações nominais (ALE-RO, Câmara, Senado) ----------
  function detalheVotos(x, i) {
    const f = fonte(), cont = contar(x);
    const grupos = f.ordem(cont).map((cod) => {
      const pids = Object.keys(x.v).filter((p) => x.v[p] === cod).sort((a, b) => nomeParl(a).localeCompare(nomeParl(b), 'pt-BR'));
      return `<div class="vt-grupo"><div class="vt-grupo-cab">${f.votoHtml(cod)} <span class="muted small">${fmtNum(pids.length)}</span></div>
        <ul class="vt-nomes">${pids.map((p) => `<li${p === st.dep ? ' class="sel"' : ''}>${esc(nomeParl(p))}${botaoFicha(candPorSq[f.parl[p].sq])}</li>`).join('')}</ul></div>`;
    }).join('');
    return `<div class="em-detalhe vt-detalhe" id="vt-det-${i}" role="region" aria-label="Votos em ${esc(f.nome(x))}">${grupos}
      <p class="small muted" style="margin:8px 0 0">${f.parcial ? 'Só os candidatos de RO em 2026 que votaram nesta votação.' : 'Candidatos em 2026 têm o botão com o cargo e o número de urna.'}</p></div>`;
  }
  // "Como você votaria?": posição do eleitor, usada no critério "Vota como eu" do Meu voto. Os dois botões têm o
  // mesmo peso visual; clicar de novo desmarca.
  const chavePos = (x) => (st.modo === 'nominal' ? 'alero' : st.modo) + ':' + x.id;
  const botoesPosicao = (x) => {
    if (x.secreta) return '';
    const k = chavePos(x), atual = Store.posicao(k);
    return `<div class="vt-posicao" role="group" aria-label="Como você votaria nesta votação?"><span class="small">Como você votaria?</span>
      ${['S', 'N'].map((v) => `<button type="button" class="btn mini pos" data-k="${esc(k)}" data-v="${v}" aria-pressed="${atual === v}">${v === 'S' ? 'Sim' : 'Não'}</button>`).join('')}
      ${atual ? '<span class="small muted">marcado no seu Perfil</span>' : ''}</div>`;
  };
  const placarGeral = (x) => x.sim == null ? '' : `Placar da votação: Sim ${fmtNum(x.sim)} · Não ${fmtNum(x.nao)}${x.abs != null ? ' · Abstenção ' + fmtNum(x.abs) : ''}${x.outros ? ' · Outros ' + fmtNum(x.outros) : ''}`;

  function renderNominal() {
    const f = fonte(), lista = filtradas();
    let kpis;
    if (st.dep) {
      const cont = {};
      lista.forEach((x) => { const v = x.v[st.dep]; cont[v] = (cont[v] || 0) + 1; });
      const c = candPorSq[f.parl[st.dep].sq];
      kpis = `<div class="em-kpi"><b>${fmtNum(lista.length)}</b><span>votações de ${esc(nomeParl(st.dep))}${c ? ' (' + esc(c.cargo) + ' ' + esc(c.nr) + ' em 2026)' : ''}</span></div>`
        + f.ordem(cont).slice(0, 5).map((k) => `<div class="em-kpi"><b>${fmtNum(cont[k])}</b><span>${esc(f.rot(k))}</span></div>`).join('');
    } else {
      kpis = `<div class="em-kpi"><b>${fmtNum(lista.length)}</b><span>votações nominais</span></div>
        <div class="em-kpi"><b>${fmtNum(Object.keys(f.parl).length)}</b><span>${f.rotParl}</span></div>
        ${f.parcial ? '' : `<div class="em-kpi"><b>${fmtNum(Object.values(f.parl).filter((p) => p.sq).length)}</b><span>deles são candidatos em 2026</span></div>`}`;
    }
    const itens = lista.slice(0, st.limite).map((x, i) => {
      const cont = contar(x), lk = f.link(x), aberta = st.aberta === String(x.id);
      const pg = f.parcial ? placarGeral(x) : '';
      return `<article class="vt-item${aberta ? ' aberta' : ''}" data-id="${esc(x.id)}">
        <div class="vt-cab"><span class="num">${fmtData(x.d)}</span>
          ${lk ? `<a href="${lk}" target="_blank" rel="noopener"><b>${esc(f.nome(x))}</b></a>` : `<b>${esc(f.nome(x))}</b>`}
          ${x.r ? `<span class="tag plain">${esc(x.r)}</span>` : ''}${x.org && x.org !== 'PLEN' ? `<span class="tag plain">${esc(x.org)}</span>` : ''}${x.secreta ? '<span class="tag plain">Votação secreta</span>' : ''}</div>
        <p class="vt-ementa">${esc(x.e || x.desc || 'Sem ementa na fonte.')}</p>
        ${x.desc && x.e ? `<p class="small muted vt-desc">${esc(x.desc)}</p>` : ''}
        ${ehVeto(x) && st.modo === 'nominal' || x.confere === false ? `<div class="vt-nota small">${ehVeto(x) && st.modo === 'nominal' ? LEGENDA_VETO : ''} ${avisoPlacar(x)}</div>` : ''}
        ${st.dep ? `<div class="vt-meu"><span class="small">Voto de ${esc(nomeParl(st.dep))}:</span> ${f.votoHtml(x.v[st.dep])}</div>` : ''}
        ${botoesPosicao(x)}
        <div class="vt-rodape"><span class="small muted">${pg || f.ordem(cont).map((k) => `${esc(f.rot(k))} ${cont[k]}`).join(' · ')}</span>
          <button type="button" class="btn mini ver-votos" aria-expanded="${aberta}" aria-controls="vt-det-${i}">${icone('lista')}${aberta ? 'Ocultar votos' : f.parcial ? 'Ver votos dos candidatos de RO' : 'Ver quem votou como'}</button></div>
      </article>${aberta ? detalheVotos(x, i) : ''}`;
    }).join('');
    const materia = st.materia ? LEIS.find((l) => l.m === st.materia) || lista[0] : null;
    return { kpis, lista, itens, rodape: f.rodape(),
      filtroMateria: materia ? `<div class="bloco small vt-filtro-materia">Mostrando só as votações nominais de <b>${esc(nomeMateria(materia))}</b>. <button type="button" class="btn mini" id="vt-limpa-materia">Mostrar todas</button></div>` : '' };
  }

  // ---------- render: leis sem voto individual (ALE-RO) ----------
  function renderLeis() {
    const lista = leisFiltradas();
    const semInd = lista.filter((l) => !l.nominal).length;
    const nDecl = lista.reduce((s, l) => s + (l.decl || []).length, 0);
    const kpis = `<div class="em-kpi"><b>${fmtNum(lista.length)}</b><span>leis e PECs decididas em plenário desde ${fmtData(A.leisDesde)}</span></div>
      <div class="em-kpi"><b>${fmtNum(semInd)}</b><span>sem voto individual registrado</span></div>
      <div class="em-kpi"><b>${fmtNum(lista.length - semInd)}</b><span>com votação nominal (voto de cada um)</span></div>
      <div class="em-kpi"><b>${fmtNum(nDecl)}</b><span>posições declaradas em documento oficial</span></div>`;
    const itens = lista.slice(0, st.limite).map((l) => {
      const lk = linkMateria(l);
      const autores = l.aut.map((a) => {
        const p = a.parl && A.parl[a.parl];
        return p ? `${esc(nomeParl(a.parl, A.parl))}${botaoFicha(candPorSq[p.sq])}` : esc(titulo(a.nome));
      }).join(', ');
      const decl = (l.decl || []).map((d) => {
        const p = A.parl[d.parlamentar];
        return `<div class="vt-decl"><b>${esc(p ? nomeParl(d.parlamentar, A.parl) : 'Deputado ' + d.parlamentar)}</b>${p ? botaoFicha(candPorSq[p.sq]) : ''} <span class="muted small">(${fmtData(d.data)})</span>
          <div>${esc(d.texto)}</div>
          <div class="small muted">Fonte: <a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.fonte)}</a></div></div>`;
      }).join('');
      return `<article class="vt-item vt-lei" data-m="${l.m}">
        <div class="vt-cab"><span class="num">${fmtData(l.d)}</span>
          ${lk ? `<a href="${lk}" target="_blank" rel="noopener"><b>${esc(nomeMateria(l))}</b></a>` : `<b>${esc(nomeMateria(l))}</b>`}
          <span class="tag plain">${esc(l.res)}</span>
          ${l.nominal ? '<span class="tag cargo">Teve votação nominal</span>' : '<span class="voto voto-Q">Sem voto individual registrado</span>'}</div>
        <p class="vt-ementa">${esc(l.e || 'Sem ementa na fonte.')}</p>
        <div class="detalhes small vt-lei-det">
          ${autores ? `<div><b>Autoria</b>${autores}</div>` : ''}
          ${l.lei ? `<div><b>Virou</b>${esc(l.lei)}</div>` : ''}
          <div><b>Registro na tramitação</b>${esc(l.txt)}</div>
        </div>
        ${decl ? `<div class="vt-decls"><div class="small"><b>Posição declarada em documento oficial</b></div>${decl}</div>` : ''}
        ${l.nominal ? `<div class="vt-rodape"><span></span><button type="button" class="btn mini ver-nominal" data-m="${l.m}">${icone('plenario')}Ver a votação nominal (${l.nominal.length})</button></div>` : ''}
      </article>`;
    }).join('');
    return { kpis, lista, itens, filtroMateria: '',
      rodape: `Projetos de lei, leis complementares e PECs aprovados ou rejeitados em plenário desde ${fmtData(A.leisDesde)} (início da legislatura atual), pela tramitação no SAPL da ALE-RO, baixada em ${fmtData(A.leisAtualizado)}. "Sem voto individual" = não há voto de cada deputado registrado no SAPL (votação simbólica ou votos ainda não lançados).` };
  }

  function render() {
    const r = st.modo === 'leis' ? renderLeis() : renderNominal();
    const vazio = st.modo === 'leis' ? 'Nenhuma lei com esses filtros.' : 'Nenhuma votação com esses filtros.';
    box.innerHTML = `${st.modo === 'leis' ? '<div class="bloco small vt-aviso-simb">Nestas votações o presidente declara o resultado sem contar os votos um a um, e <b>não fica registrado como cada deputado votou</b>. Presença na sessão não é voto. Posições individuais só aparecem aqui quando constam de documento oficial da ALE-RO.</div>' : ''}
      ${r.filtroMateria}
      <div class="em-kpis">${r.kpis}</div>
      ${r.lista.length ? `<div class="vt-lista">${r.itens}</div>
        ${r.lista.length > st.limite ? `<div class="linha" style="justify-content:center;margin-top:10px"><button type="button" class="btn" id="vt-mais">Mostrar mais (${fmtNum(r.lista.length - st.limite)} restantes)</button></div>` : ''}`
      : `<div class="vazio" style="margin-top:16px">${vazio}</div>`}
      <p class="small muted" style="margin-top:10px">${r.rodape}</p>`;

    box.querySelectorAll('.vt-item[data-id]').forEach((it) => {
      it.querySelector('.ver-votos').onclick = () => alternar(it.dataset.id);
    });
    box.querySelectorAll('.ver-nominal').forEach((b) => b.onclick = () => { $('vt-texto').value = ''; mudarModo('nominal', { materia: +b.dataset.m, texto: '', tipo: '', ano: '' }); });
    const limpa = $('vt-limpa-materia'); if (limpa) limpa.onclick = () => { st.materia = null; reiniciar(); render(); };
    box.querySelectorAll('.abrir-ficha').forEach((b) => b.onclick = () => { const c = candPorSq[b.dataset.sq]; if (c) Modal.abrir(c); });
    box.querySelectorAll('.vt-posicao .pos').forEach((b) => b.onclick = () => {
      const k = b.dataset.k, v = b.dataset.v;
      Store.setPosicao(k, Store.posicao(k) === v ? null : v);
      const grupo = b.closest('.vt-posicao'); const atual = Store.posicao(k);
      grupo.querySelectorAll('.pos').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.v === atual)));
      const nota = grupo.querySelector('.muted'); if (nota) nota.remove();
      if (atual) grupo.insertAdjacentHTML('beforeend', '<span class="small muted">marcado no seu Perfil</span>');
    });
    const mais = $('vt-mais'); if (mais) mais.onclick = () => { st.limite += 60; render(); };
  }

  // abre/fecha os votos logo abaixo da votação (sanfona) e mantém o item na tela
  function alternar(id) {
    st.aberta = st.aberta === id ? null : id;
    render();
    const it = [...box.querySelectorAll('.vt-item[data-id]')].find((e) => e.dataset.id === id);
    if (!it) return;
    it.querySelector('.ver-votos').focus({ preventScroll: true });
    it.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  // vindo da ficha no mesmo documento (versão celular) ou de um hash novo: abre a Casa e filtra no parlamentar
  document.addEventListener('tela:mudou', (e) => {
    if (e.detail.id !== 'tela-votacoes' || !window.App.votacoesDep) return;
    const casa = window.App.votacoesCasa || 'alero', modo = casa === 'alero' ? 'nominal' : casa;
    const dep = window.App.votacoesDep; window.App.votacoesDep = null; window.App.votacoesCasa = null;
    if (!FONTES[modo] || !FONTES[modo].parl[dep]) return;
    $('vt-texto').value = '';
    mudarModo(modo, { dep, texto: '', tipo: '', ano: '' });
  });

  document.querySelectorAll('.vt-modos button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === st.modo)));
  preencherDeputados();
  preencherTiposAnos();
  render();
  Dados.carregarVarias(['RO'].filter((u) => Dados.manifest().ufs.includes(u))).then((lista) => {
    lista.forEach((c) => { candPorSq[c.sq] = c; });
    preencherDeputados();
    render();
  });
})();
