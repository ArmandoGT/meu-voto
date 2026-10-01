/* coligacoes.js — tela "Coligações": para onde vai o voto em cada candidato, sem juízo de valor. Modos:
   "cand":  escolhe um candidato e mostra com quem o voto dele é somado (deputado: partido/federação)
            ou a coligação da chapa (cargo majoritário: o voto não se transfere);
   "grupo": partidos isolados, federações e coligações de um cargo, com os candidatos de cada um. */
(function () {
  'use strict';
  const { norm, esc, titulo, icone, fmtNum, fmtData, Dados, Modal, montarTopo, cardCandidato, fotoHtml, perfil, agremiacao, ehProporcional, chaveSigla, CARGOS_ORDEM, sitClasse, sitCurta } = window.App;
  // "#coligacoes-<UF>-<sq>" (vindo da ficha em outra página) = abrir no candidato; lido antes de Telas.iniciar, que troca o hash
  const doHash = () => { const m = location.hash.match(/^#coligacoes-([A-Za-z]{2})-(\d+)/); return m ? { uf: m[1].toUpperCase(), sq: m[2] } : null; };
  const inicial = doHash();
  window.addEventListener('hashchange', () => { const h = doHash(); if (h) { window.App.coligacoesSq = h.sq; window.App.coligacoesUf = h.uf; document.dispatchEvent(new CustomEvent('tela:mudou', { detail: { id: 'tela-coligacoes' } })); } });
  montarTopo();
  window.App.Telas.iniciar('tela-coligacoes');
  const $ = (id) => document.getElementById(id);
  if (!$('tela-coligacoes')) return;

  // Conferido em 30/09/2026 na lista do TSE (federações registradas) e nos números de federação dos dados de candidatos.
  const VERIFICADO = '2026-09-30';
  const FEDERACOES = [
    { nr: '101', nome: 'Federação Brasil da Esperança (FE Brasil)', partidos: 'PT, PCdoB e PV', registro: '2022-05-24' },
    { nr: '100', nome: 'Federação PSDB Cidadania', partidos: 'PSDB e Cidadania', registro: '2022-05-26' },
    { nr: '102', nome: 'Federação PSOL Rede', partidos: 'PSOL e Rede', registro: '2022-05-26' },
    { nr: '103', nome: 'Federação Renovação Solidária', partidos: 'PRD e Solidariedade', registro: '2025-12-04' },
    { nr: '104', nome: 'Federação União Progressista', partidos: 'União Brasil e PP', registro: '2026-03-26' },
  ];
  const FONTES = [
    ['Emenda Constitucional 97/2017', 'https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc97.htm', 'Proíbe coligações nas eleições proporcionais (deputados e vereadores) a partir de 2020.'],
    ['Lei 9.504/1997 (Lei das Eleições)', 'https://www.planalto.gov.br/ccivil_03/leis/l9504.htm', 'Art. 2º (maioria absoluta e 2º turno), art. 5º (votos válidos), art. 6º (coligação só na eleição majoritária) e art. 6º-A (federações).'],
    ['Lei 14.208/2021 (federações partidárias)', 'https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14208.htm', 'Cria a federação: atua como um único partido, em todo o país, por no mínimo 4 anos.'],
    ['Código Eleitoral (Lei 4.737/1965)', 'https://www.planalto.gov.br/ccivil_03/leis/l4737compilado.htm', 'Arts. 106 a 109: quociente eleitoral, quociente partidário, regra dos 10% e sobras.'],
    ['STF — sobras eleitorais (ADIs 7228, 7263 e 7325)', 'https://portal.stf.jus.br/noticias/verNoticiaDetalhe.asp?idConteudo=528283&ori=1', 'Decisão de 28/02/2024: todos os partidos participam da última fase das sobras.'],
    ['STF — a decisão sobre sobras vale desde 2022', 'https://noticias.stf.jus.br/postsnoticias/decisao-do-stf-sobre-distribuicao-de-sobras-eleitorais-vale-desde-2022/', 'Julgamento dos recursos em 13/03/2025.'],
    ['STF — federações partidárias (ADI 7021)', 'https://noticias.stf.jus.br/postsnoticias/stf-valida-lei-que-permite-federacoes-partidarias/', 'O STF confirmou a lei das federações.'],
    ['TSE — federações registradas', 'https://www.tse.jus.br/partidos/federacoes-registradas-no-tse', 'Lista oficial das federações e dos partidos de cada uma.'],
    ['TSE — coligações só nas eleições majoritárias', 'https://www.tse.jus.br/comunicacao/noticias/2024/Junho/se-liga-coligacoes-partidarias-so-podem-ser-feitas-para-as-eleicoes-majoritarias', 'Explicação do TSE sobre coligações.'],
    ['TSE — cargos em disputa em 2026', 'https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/confira-quais-cargos-estarao-em-disputa-nas-eleicoes-2026', 'Presidente, governador, 2 vagas de senador por estado, deputados federais e estaduais.'],
    ['Senado — dois votos para senador', 'https://www12.senado.leg.br/radio/1/noticia/2026/08/04/eleitores-devem-votar-em-dois-candidatos-diferentes-para-o-senado-em-outubro', 'Em 2026 o eleitor vota em dois candidatos diferentes para o Senado.'],
    ['TSE — dados abertos de candidatos 2026', 'https://dadosabertos.tse.jus.br/dataset/candidatos-2026', 'Origem dos partidos, federações e coligações de cada candidato mostrados nesta tela.'],
  ];

  const st = { modo: 'cand', cargo: '', texto: '', sq: null, limite: 40 };
  let todos = [], porSq = {}, uf = '', ufVer = null;   // ufVer: UF de um candidato aberto pela ficha, quando não é a do perfil
  const naUrna = (c) => c.urnaOk !== false;
  const ordemNome = (a, b) => titulo(a.urna).localeCompare(titulo(b.urna), 'pt-BR');
  const local = (c) => c.uf === 'BR' ? 'no Brasil' : 'em ' + c.uf;
  const chaveGrupo = (c) => c.cargo + '|' + c.uf + '|' + agremiacao(c).chave;
  const vagasDe = (c) => ((Dados.manifest().vagas || {})[c.uf] || {})[c.cargo] || null;
  const tagTipo = (ag) => `<span class="tag ${ag.tipo === 'partido' ? 'plain' : 'cargo'}">${esc(ag.rotuloTipo)}</span>`;

  function grupos(cargo) {
    const g = {};
    todos.filter((c) => c.cargo === cargo && naUrna(c)).forEach((c) => {
      const k = chaveGrupo(c);
      (g[k] = g[k] || { ag: agremiacao(c), membros: [] }).membros.push(c);
    });
    return Object.values(g).sort((a, b) => b.membros.length - a.membros.length || a.ag.nome.localeCompare(b.ag.nome, 'pt-BR'));
  }
  const colegas = (c) => todos.filter((x) => x.sq !== c.sq && naUrna(x) && chaveGrupo(x) === chaveGrupo(c)).sort(ordemNome);
  const conjunto = (c) => agremiacao(c).partidos.map(chaveSigla).sort().join('|');

  const grade = (lista) => {
    const g = document.createElement('div'); g.className = 'grade';
    lista.forEach((c) => { const card = cardCandidato(c); card.onclick = () => Modal.abrir(c); g.appendChild(card); });
    return g;
  };
  const porPartido = (lista) => {
    const n = {}; lista.forEach((c) => { n[c.partido] = (n[c.partido] || 0) + 1; });
    return Object.entries(n).sort((a, b) => b[1] - a[1]).map(([p, q]) => `${esc(p)}: ${q}`).join(' · ');
  };

  // ---------- filtros ----------
  function preencherCargos() {
    const sel = $('cl-cargo');
    const cargos = CARGOS_ORDEM.filter((k) => todos.some((c) => c.cargo === k));
    if (st.modo === 'grupo' && !cargos.includes(st.cargo)) st.cargo = cargos.includes('Deputado Federal') ? 'Deputado Federal' : cargos[0] || '';
    sel.innerHTML = (st.modo === 'cand' ? '<option value="">Todos os cargos</option>' : '') + cargos.map((k) => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
    sel.value = st.cargo;
    document.querySelectorAll('#tela-coligacoes .cl-so-cand').forEach((x) => { x.hidden = st.modo !== 'cand'; });
  }
  function mudarModo(modo) {
    st.modo = modo; st.limite = 40;
    document.querySelectorAll('#tela-coligacoes .vt-modos button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === modo)));
    preencherCargos(); render();
  }
  document.querySelectorAll('#tela-coligacoes .vt-modos button').forEach((b) => { b.onclick = () => mudarModo(b.dataset.modo); });
  $('cl-cargo').onchange = (e) => { st.cargo = e.target.value; st.sq = null; st.limite = 40; render(); };
  $('cl-texto').oninput = (e) => { st.texto = e.target.value; st.sq = null; st.limite = 40; render(); };

  // ---------- render ----------
  const box = $('cl-conteudo');
  function render() {
    box.innerHTML = '';
    if (!todos.length) { box.innerHTML = '<div class="vazio" style="margin-top:16px">Carregando candidatos…</div>'; return; }
    if (st.modo === 'grupo') renderGrupos();
    else if (st.sq && porSq[st.sq]) renderCandidato(porSq[st.sq]);
    else renderBusca();
  }

  function renderBusca() {
    const q = norm(st.texto);
    let lista = todos.filter((c) => naUrna(c) && (!st.cargo || c.cargo === st.cargo));
    if (q) lista = /^\d+$/.test(q) ? lista.filter((c) => String(c.nr).startsWith(q)) : lista.filter((c) => [c.urna, c.nome, c.social].some((s) => norm(s).includes(q)));
    lista.sort((a, b) => CARGOS_ORDEM.indexOf(a.cargo) - CARGOS_ORDEM.indexOf(b.cargo) || ordemNome(a, b));
    if (!lista.length) { box.innerHTML = '<div class="vazio" style="margin-top:16px">Nenhum candidato encontrado.</div>'; return; }
    const ul = document.createElement('div');
    ul.innerHTML = `<p class="small muted">${fmtNum(lista.length)} candidato(s)${st.cargo ? ' a ' + esc(st.cargo) : ''} ${esc(uf ? 'em ' + uf : '')}${lista.some((c) => c.uf === 'BR') ? ' e no Brasil' : ''}. Toque em um para ver para onde vai o voto.</p>
      <ul class="cl-lista">${lista.slice(0, st.limite).map((c) => {
        const ag = agremiacao(c);
        return `<li><button type="button" class="cl-res" data-sq="${esc(c.sq)}">${fotoHtml(c, 'mini')}<span class="numero">${esc(c.nr)}</span>
          <span class="cl-res-txt"><b>${esc(titulo(c.urna))}</b><span class="small muted">${esc(c.cargo)} · ${esc(c.partido)}${ag.tipo !== 'partido' ? ' · ' + esc(ag.rotuloTipo.toLowerCase()) + ' ' + esc(ag.nome) : ''}</span></span>${icone('seta')}</button></li>`;
      }).join('')}</ul>
      ${lista.length > st.limite ? `<button type="button" class="btn cl-mais">Mostrar mais (${fmtNum(lista.length - st.limite)} restantes)</button>` : ''}`;
    box.appendChild(ul);
    box.querySelectorAll('.cl-res').forEach((b) => { b.onclick = () => abrirCandidato(b.dataset.sq); });
    const mais = box.querySelector('.cl-mais'); if (mais) mais.onclick = () => { st.limite += 80; render(); };
  }

  function abrirCandidato(sq, rolar = true) {
    st.sq = sq; render();
    if (rolar) box.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function renderCandidato(c) {
    const ag = agremiacao(c);
    const nomeC = esc(titulo(c.urna));
    const voltar = `<button type="button" class="btn mini cl-voltar">${icone('busca')}Escolher outro candidato</button>`;
    const topo = document.createElement('div');
    topo.className = 'cl-topo';
    topo.innerHTML = voltar;
    box.appendChild(topo);
    const g = document.createElement('div'); g.className = 'grade cl-escolhido';
    const card = cardCandidato(c); card.onclick = () => Modal.abrir(c); g.appendChild(card);
    box.appendChild(g);
    const fora = !naUrna(c) ? `<p class="bloco alerta small">Segundo o TSE, ${nomeC} não está apto na urna (${esc(sitCurta(c.sit))}).</p>` : '';

    if (ehProporcional(c)) {
      const outros = colegas(c);
      const grupoTxt = ag.tipo === 'federacao' ? `da <b>${esc(ag.nome)}</b> (${esc(ag.comp)})` : `do <b>${esc(c.partido)}</b>`;
      const vagas = vagasDe(c);
      const d = document.createElement('section');
      d.className = 'card cl-destino';
      d.innerHTML = `<h2>Para onde vai o voto em ${nomeC} (${esc(c.nr)})</h2>
        <p>${nomeC} concorre a ${esc(c.cargo)} ${esc(local(c))} ${ag.tipo === 'federacao' ? `pela <b>${esc(ag.nome)}</b>, que reúne ${esc(ag.comp)} e conta como um partido só` : `pelo <b>${esc(c.partido)}</b>, ${ag.tipo === 'partido' ? 'sem federação' : esc(ag.rotuloTipo.toLowerCase())}`}.</p>
        <ol class="cl-passos">
          <li>O voto em ${nomeC} é somado aos votos de todos os candidatos ${grupoTxt} e aos votos de legenda.</li>
          <li>Essa soma define quantas vagas o grupo ganha${vagas ? ` das ${vagas} vagas de ${esc(c.cargo)} ${esc(local(c))}` : ''} (quociente partidário e sobras).</li>
          <li>As vagas ficam com os mais votados do grupo que tenham pelo menos 10% do quociente eleitoral.</li>
          <li>Se ${nomeC} não ficar entre eles, o voto ainda ajuda a eleger alguém da lista abaixo. Ele <b>não vai para nenhum outro partido ou federação</b>.</li>
        </ol>${fora}`;
      box.appendChild(d);
      const h = document.createElement('div');
      h.innerHTML = `<h3 class="cl-sub">${outros.length ? `Os outros ${outros.length} candidatos ${grupoTxt} a ${esc(c.cargo)} ${esc(local(c))}` : `Nenhum outro candidato ${grupoTxt} a ${esc(c.cargo)} ${esc(local(c))}`}</h3>
        ${ag.tipo === 'federacao' && outros.length ? `<p class="small muted">Por partido, contando ${nomeC}: ${porPartido([c, ...outros])}</p>` : ''}`;
      box.appendChild(h);
      if (outros.length) box.appendChild(grade(outros));
    } else {
      const senado = c.cargo === 'Senador';
      const regra = senado
        ? 'Para senador, em 2026, vencem os dois mais votados do estado, sem segundo turno. Você vota em dois candidatos diferentes, e cada voto conta só para aquele candidato.'
        : `Para ${esc(c.cargo.toLowerCase())}, vence quem tiver a maioria absoluta dos votos válidos; se ninguém tiver, há segundo turno entre os dois mais votados. O voto conta só para ${nomeC} e a chapa dele.`;
      const chapa = (c.chapa || []).slice().sort((a, b) => a.cargo.localeCompare(b.cargo, 'pt-BR')).map((m) => `<div class="membro">${fotoHtml(m, 'mini')}<div><b>${esc(m.cargo)}</b> ${esc(titulo(m.nome))} · ${esc(m.partido)}${m.sit ? ` <span class="tag ${sitClasse(m.sit)}">${esc(sitCurta(m.sit))}</span>` : ''}</div></div>`).join('');
      const d = document.createElement('section');
      d.className = 'card cl-destino';
      d.innerHTML = `<h2>Para onde vai o voto em ${nomeC} (${esc(c.nr)})</h2>
        <p>${nomeC} concorre a ${esc(c.cargo)} ${esc(local(c))} ${ag.tipo === 'coligacao' ? `pela coligação <b>${esc(ag.nome)}</b> (${esc(c.compColigacao)})` : ag.tipo === 'federacao' ? `pela <b>${esc(ag.nome)}</b>, sem coligação` : `pelo <b>${esc(c.partido)}</b>, sem coligação`}.</p>
        <div class="bloco"><b>O voto não se transfere.</b> ${regra} Se ${nomeC} perder, o voto não vai para nenhum aliado${ag.tipo === 'coligacao' ? ' da coligação' : ''}.</div>
        ${chapa ? `<div class="bloco"><b>Chapa</b>${chapa}</div>` : ''}${fora}`;
      box.appendChild(d);
      // mesma aliança em outros cargos majoritários: só informação, os votos não se somam
      const k = conjunto(c);
      const aliados = todos.filter((x) => x.sq !== c.sq && naUrna(x) && !ehProporcional(x) && (x.cargo !== c.cargo || x.uf !== c.uf || chaveGrupo(x) === chaveGrupo(c)) && conjunto(x) === k && (ag.tipo === 'coligacao' || agremiacao(x).tipo === ag.tipo))
        .sort((a, b) => CARGOS_ORDEM.indexOf(a.cargo) - CARGOS_ORDEM.indexOf(b.cargo) || ordemNome(a, b));
      if (aliados.length) {
        const h = document.createElement('div');
        h.innerHTML = `<h3 class="cl-sub">Apoiados pelos mesmos partidos (${aliados.length})</h3>
          <p class="small muted">Candidatos majoritários com a mesma composição de partidos que ${nomeC}. É só informação: votar em um não soma votos para o outro.</p>`;
        box.appendChild(h);
        box.appendChild(grade(aliados));
      }
      if (ag.tipo === 'coligacao') {
        const deps = todos.filter((x) => naUrna(x) && ehProporcional(x) && agremiacao(x).partidos.some((p) => ag.partidos.map(chaveSigla).includes(chaveSigla(p))));
        if (deps.length) {
          const grp = {};
          deps.forEach((x) => { const a = agremiacao(x); const kk = x.cargo + '|' + a.chave; (grp[kk] = grp[kk] || { cargo: x.cargo, ag: a, n: 0 }).n++; });
          const linhas = Object.values(grp).sort((a, b) => CARGOS_ORDEM.indexOf(a.cargo) - CARGOS_ORDEM.indexOf(b.cargo) || b.n - a.n)
            .map((x) => `<li>${esc(x.cargo)}: ${x.ag.tipo === 'federacao' ? esc(x.ag.nome) + ' (' + esc(x.ag.comp) + ')' : esc(x.ag.comp)} — ${x.n} candidato(s)</li>`).join('');
          const h = document.createElement('details');
          h.className = 'secao cl-deps';
          h.innerHTML = `<summary>${icone('seta')}<span>Os partidos desta coligação na eleição para deputado</span></summary>
            <div class="conteudo small"><p class="muted">A coligação não vale para deputado. Lá, cada partido (ou federação) abaixo concorre separado, e os votos de um não somam para o outro.</p><ul>${linhas}</ul></div>`;
          box.appendChild(h);
        }
      }
    }
    topo.querySelector('.cl-voltar').onclick = () => { st.sq = null; render(); $('cl-texto').focus(); };
  }

  function renderGrupos() {
    const lista = grupos(st.cargo);
    if (!lista.length) { box.innerHTML = '<div class="vazio" style="margin-top:16px">Nenhum candidato para este cargo.</div>'; return; }
    const ex = lista[0].membros[0];
    const prop = ehProporcional(ex);
    const vagas = vagasDe(ex);
    const cab = document.createElement('p');
    cab.className = 'small muted';
    cab.innerHTML = prop
      ? `${lista.length} grupos disputam ${vagas ? `as ${vagas} vagas` : 'as vagas'} de ${esc(st.cargo)} ${esc(local(ex))}. Cada grupo soma os votos de todos os seus candidatos e da legenda; as vagas que ganhar vão para os mais votados do próprio grupo.`
      : `${lista.length} chapas para ${esc(st.cargo)} ${esc(local(ex))}. A coligação une partidos em torno da mesma chapa, mas o voto não passa de um candidato para outro.`;
    box.appendChild(cab);
    lista.forEach((gr) => {
      const det = document.createElement('details');
      det.className = 'secao cl-grupo';
      det.innerHTML = `<summary>${icone('seta')}<span class="cl-grupo-tit">${tagTipo(gr.ag)} <b>${esc(gr.ag.nome)}</b>
          <span class="small muted">${gr.ag.tipo !== 'partido' ? esc(gr.ag.comp) + ' · ' : ''}${gr.membros.length} candidato(s)</span></span></summary>
        <div class="conteudo">${gr.ag.tipo === 'federacao' ? `<p class="small muted">Por partido: ${porPartido(gr.membros)}</p>` : ''}${gr.ag.tipo === 'coligacao' ? `<p class="small muted">Composição registrada no TSE: ${esc(gr.ag.compTSE)}</p>` : ''}</div>`;
      det.addEventListener('toggle', () => {
        const ct = det.querySelector('.conteudo');
        if (det.open && !ct.querySelector('.grade')) ct.appendChild(grade(gr.membros.slice().sort(ordemNome)));
      });
      box.appendChild(det);
    });
  }

  function renderFixos() {
    const cont = {};
    todos.forEach((c) => { if (c.nrFederacao && naUrna(c)) cont[c.nrFederacao] = (cont[c.nrFederacao] || 0) + 1; });
    $('cl-federacoes').innerHTML = `<div style="overflow-x:auto"><table class="tabela"><thead><tr><th>Federação</th><th>Partidos</th><th>Registro no TSE</th><th class="r">Candidatos ${esc(uf ? 'em ' + uf : '')}</th></tr></thead><tbody>
      ${FEDERACOES.map((f) => `<tr><td>${esc(f.nome)}</td><td>${esc(f.partidos)}</td><td class="num">${fmtData(f.registro)}</td><td class="r num">${fmtNum(cont[f.nr] || 0)}</td></tr>`).join('')}</tbody></table></div>`;
    $('cl-fontes').innerHTML = FONTES.map(([n, u, d]) => `<div><b><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)} ${icone('externo')}</a></b>${esc(d)}</div>`).join('');
    const m = Dados.manifest();
    $('cl-rodape').textContent = `Regras conferidas nas fontes acima em ${fmtData(VERIFICADO)}. Partidos, federações e coligações de cada candidato: base oficial do TSE gerada em ${m.geradoEm ? fmtData(m.geradoEm.slice(0, 10)) + m.geradoEm.slice(10) : '—'}.`;
  }

  // vindo da ficha no mesmo documento (versão celular) ou de um hash novo: abre no candidato
  async function irPara(sq, ufC) {
    if (!porSq[sq] && ufC && ufC !== 'BR' && ufC !== uf) { ufVer = ufC; await carregar(); }
    if (!porSq[sq]) return;
    if (st.modo !== 'cand') mudarModo('cand');
    abrirCandidato(sq);
  }
  document.addEventListener('tela:mudou', (e) => {
    if (e.detail.id !== 'tela-coligacoes' || !window.App.coligacoesSq) return;
    const sq = window.App.coligacoesSq, ufC = window.App.coligacoesUf; window.App.coligacoesSq = null; window.App.coligacoesUf = null;
    irPara(sq, ufC);
  });

  function carregar() {
    uf = ufVer || perfil().uf;
    const ufs = [uf, 'BR'].filter((u) => (Dados.manifest().ufs || []).includes(u));
    return Dados.carregarVarias(ufs).then((lista) => {
      todos = lista; porSq = {};
      lista.forEach((c) => { porSq[c.sq] = c; });
      if (st.sq && !porSq[st.sq]) st.sq = null;
      preencherCargos(); renderFixos(); render();
    });
  }
  document.addEventListener('perfil:mudou', () => { ufVer = null; carregar(); });

  preencherCargos(); renderFixos(); render();
  carregar().then(() => { if (inicial) irPara(inicial.sq, inicial.uf); });
})();
