/* resultados.js — tela "Resultados": apuração de 2026 por estado e cargo, consulta de um candidato
   (votos por cidade, situação e por que não foi eleito) e estatísticas. Só números e regras, sem juízo de valor.
   Dados: data/resultados_XX.js (window.RES_XX, gerado por scripts/build_resultados.py) + data/cand_XX.js. */
(function () {
  'use strict';
  const { norm, normMun, esc, titulo, icone, fmtNum, fmtMoeda, Dados, Modal, montarTopo, fotoHtml, perfil, CARGOS_ORDEM,
    corPartido, pontoPartido, Res, situacaoRes, explicarRes, agrNome, ordinal, pct } = window.App;
  // "#resultados-<UF>-<sq>" (vindo da ficha em outra página) = abrir no candidato; lido antes de Telas.iniciar, que troca o hash
  const doHash = () => { const m = location.hash.match(/^#resultados-([A-Za-z]{2})-(\d+)/); return m ? { uf: m[1].toUpperCase(), sq: m[2] } : null; };
  const inicial = doHash();
  window.addEventListener('hashchange', () => { const h = doHash(); if (h) { window.App.resultadosSq = h.sq; window.App.resultadosUf = h.uf; document.dispatchEvent(new CustomEvent('tela:mudou', { detail: { id: 'tela-resultados' } })); } });
  montarTopo();
  window.App.Telas.iniciar('tela-resultados');
  const $ = (id) => document.getElementById(id);
  if (!$('tela-resultados')) return;

  const FONTES = [
    ['TSE — Resultados (divulgação oficial)', 'https://resultados.tse.jus.br/oficial/app/index.html', 'Totalização dos votos por cargo, estado e município; situação de cada candidato; quociente eleitoral e vagas por partido.'],
    ['TSE — dados abertos: resultados 2026', 'https://dadosabertos.tse.jus.br/dataset/resultados-2026', 'Votação de cada candidato por município e zona (votacao_candidato_munzona_2026).'],
    ['Código Eleitoral (Lei 4.737/1965)', 'https://www.planalto.gov.br/ccivil_03/leis/l4737compilado.htm', 'Arts. 106 a 109: quociente eleitoral, quociente partidário, 10% e 20% do QE e sobras.'],
    ['Lei 9.504/1997 (Lei das Eleições)', 'https://www.planalto.gov.br/ccivil_03/leis/l9504.htm', 'Art. 2º (maioria absoluta e 2º turno), art. 5º (votos válidos).'],
    ['STF — sobras eleitorais (ADIs 7228, 7263 e 7325)', 'https://portal.stf.jus.br/noticias/verNoticiaDetalhe.asp?idConteudo=528283&ori=1', 'Todas as listas participam da última fase das sobras, sem os mínimos de 80% e 20%.'],
  ];
  const LIM = 30;
  const st = { uf: '', cargo: '', texto: '', sq: null, ordem: 'desc', filtroMun: '', limMun: LIM, limRank: LIM, limMais: LIM, limCidades: LIM, ordCidades: 'abst' };
  let R = null, RB = null, cands = {}, ufVer = null;

  const PROP = (b) => b && [6, 7, 8].includes(b.cd);
  const blocoDe = (cargo) => cargo === 'Presidente' ? RB && RB.cargos.Presidente : R && R.cargos[cargo];
  const resDe = (cargo) => cargo === 'Presidente' ? RB : R;
  const nomeK = (k) => titulo(k.nome);
  const candBase = (sq) => cands[sq] || null;
  const fotoK = (sq) => { const c = candBase(sq); return c ? fotoHtml(c, 'mini') : '<span class="foto mini vazia" aria-hidden="true"></span>'; };
  const tagSit = (k) => { const s = situacaoRes(k); return `<span class="tag ${s.cls}">${esc(s.txt)}</span>`; };
  const pctTxt = (v, t) => pct(v, t, 2);
  // nome da cidade: "Ariquemes/RO" (Presidente usa a tabela do Brasil: [nome, uf])
  function cidade(cd, cargo) {
    const Rm = resDe(cargo);
    const m = Rm && Rm.muns[cd];
    if (!m) return cd;
    return cargo === 'Presidente' ? `${titulo(m[0])}/${m[1] === 'ZZ' ? 'Exterior' : m[1]}` : `${titulo(m[0])}/${Rm.meta.uf}`;
  }
  // código TSE do município do perfil (para destacar "a sua cidade")
  function munPerfil(cargo) {
    const p = perfil();
    const Rm = resDe(cargo);
    if (!p.mun || !Rm) return null;
    const alvo = normMun(p.mun);
    return Object.keys(Rm.muns).find((cd) => normMun(Rm.muns[cd][0]) === alvo && (cargo !== 'Presidente' || Rm.muns[cd][1] === p.uf)) || null;
  }

  // ---------- filtros ----------
  function preencherFiltros() {
    const ufs = (Dados.manifest().ufs || []).filter((u) => u !== 'BR');
    $('rs-uf').innerHTML = ufs.map((u) => `<option value="${u}">${u}</option>`).join('');
    $('rs-uf').value = st.uf;
    if (R === undefined) return;   // carregando outra UF: mantém o cargo escolhido
    const cargos = CARGOS_ORDEM.filter((c) => blocoDe(c));
    if (!cargos.includes(st.cargo)) st.cargo = cargos.includes('Deputado Federal') ? 'Deputado Federal' : cargos[0] || '';
    $('rs-cargo').innerHTML = cargos.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    $('rs-cargo').value = st.cargo;
  }
  $('rs-uf').onchange = (e) => { ufVer = e.target.value; st.sq = null; carregar(); };
  $('rs-cargo').onchange = (e) => { st.cargo = e.target.value; st.limRank = LIM; st.limMais = LIM; render(); };
  $('rs-texto').oninput = (e) => { st.texto = e.target.value; st.sq = null; renderConsulta(); };

  // ---------- consulta de candidato ----------
  function todosCands() {
    const out = [];
    CARGOS_ORDEM.forEach((cargo) => { const b = blocoDe(cargo); if (b) Object.entries(b.cand).forEach(([sq, k]) => out.push({ sq, k, b, cargo })); });
    return out;
  }
  function renderConsulta() {
    const box = $('rs-cand');
    if (!R && !RB) { box.innerHTML = ''; return; }
    if (st.sq) { renderCandidato(box); return; }
    const q = norm(st.texto);
    if (!q) { box.innerHTML = ''; return; }
    let lista = todosCands();
    lista = /^\d+$/.test(q) ? lista.filter((x) => String(x.k.n).startsWith(q)) : lista.filter((x) => norm(x.k.nome).includes(q) || norm((candBase(x.sq) || {}).nome).includes(q));
    lista.sort((a, b) => b.k.v - a.k.v);
    if (!lista.length) { box.innerHTML = '<div class="vazio">Nenhum candidato encontrado neste estado.</div>'; return; }
    box.innerHTML = `<ul class="cl-lista">${lista.slice(0, 20).map((x) => `<li><button type="button" class="cl-res" data-sq="${esc(x.sq)}" data-cargo="${esc(x.cargo)}">${fotoK(x.sq)}<span class="numero">${esc(x.k.n)}</span>
      <span class="cl-res-txt"><b>${esc(nomeK(x.k))}</b><span class="small muted">${esc(x.cargo)} · ${esc(x.k.sg)} · ${fmtNum(x.k.v)} votos</span></span>${tagSit(x.k)}${icone('seta')}</button></li>`).join('')}</ul>
      ${lista.length > 20 ? `<p class="small muted">Mostrando 20 de ${fmtNum(lista.length)}. Digite mais letras para filtrar.</p>` : ''}`;
    box.querySelectorAll('.cl-res').forEach((bt) => { bt.onclick = () => abrir(bt.dataset.sq, bt.dataset.cargo); });
  }
  function abrir(sq, cargo, rolar = true) {
    st.sq = sq; st.sqCargo = cargo; st.filtroMun = ''; st.limMun = LIM; st.ordem = 'desc';
    renderConsulta();
    if (rolar) $('rs-cand').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function renderCandidato(box) {
    const b = blocoDe(st.sqCargo);
    const k = b && b.cand[st.sq];
    if (!k) { st.sq = null; renderConsulta(); return; }
    const c = candBase(st.sq);
    const pres = b.cd === 1;
    const base = b.tot.baseMaioria || b.tot.validos;   // igual ao % do TSE (válidos + anulados sub judice)
    const nCands = Object.keys(b.cand).length;
    const mun = k.mun || [];
    const totalMun = mun.reduce((s, m) => s + m[1], 0);
    const meuMun = munPerfil(st.sqCargo);
    const Rm = resDe(st.sqCargo);
    // posição do candidato na cidade do perfil, entre todos os candidatos do cargo
    let naCidade = '';
    if (meuMun) {
      const vs = Object.values(b.cand).map((x) => ((x.mun || []).find((m) => m[0] === meuMun) || [0, 0])[1]).sort((a, b2) => b2 - a);
      const meu = (mun.find((m) => m[0] === meuMun) || [0, 0])[1];
      naCidade = `<div class="bloco"><b>Em ${esc(cidade(meuMun, st.sqCargo))} (a cidade do seu perfil)</b> ${fmtNum(meu)} votos${meu ? ` — ${ordinal(vs.indexOf(meu) + 1)} mais votado da cidade para ${esc(st.sqCargo.toLowerCase())}` : ''}.</div>`;
    }
    const expl = explicarRes(k, b);
    const projecao = k.pe || k.p2 || !b.oficial;
    const ag = PROP(b) ? b.agr[k.a] : null;
    box.innerHTML = `
      <div class="cl-topo"><button type="button" class="btn mini rs-voltar">${icone('busca')}Consultar outro candidato</button></div>
      <article class="rs-cand">
        <div class="rs-cand-cab">${c ? fotoHtml(c, 'grande') : ''}
          <div class="cresce"><div class="linha"><span class="numero">${esc(k.n)}</span><h3>${esc(nomeK(k))}</h3>${tagSit(k)}</div>
          <div class="muted small">${esc(st.sqCargo)} · ${esc(pres ? 'Brasil' : R.meta.uf)} · ${esc(k.sg)}${ag && ag.tipo === 'f' ? ' · ' + esc(agrNome(ag, false)) : ''}${k.vice ? ' · vice/suplentes: ' + esc(k.vice.map(titulo).join(', ')) : ''}</div></div></div>
        <div class="rs-kpis">
          <div><b>Votos</b><span class="num">${fmtNum(k.v)}</span></div>
          <div><b>dos votos válidos</b><span class="num">${pctTxt(k.v, base)}</span></div>
          ${k.pos ? `<div><b>Colocação</b><span class="num">${ordinal(k.pos)} de ${fmtNum(nCands)}</span></div>` : ''}
          ${PROP(b) && k.lst ? `<div><b>Na lista ${esc(ag.sigla)}</b><span class="num">${ordinal(k.lst)}</span></div>` : ''}
          ${mun.length ? `<div><b>Cidades com voto</b><span class="num">${fmtNum(mun.length)}</span></div>` : ''}
        </div>
        ${projecao ? `<p class="bloco small"><b>Resultado ainda não proclamado pelo TSE</b>${esc(b.aviso || '')}. A situação mostrada é uma projeção pelas regras da lei com os votos já totalizados.</p>` : ''}
        <div class="rs-expl">${expl.map((p) => `<p>${p}</p>`).join('')}</div>
        ${naCidade}
        ${pres ? porUfCand(st.sq, b) : ''}
        <h4 class="cl-sub">Votos por cidade${mun.length ? ` <span class="muted small">(${fmtNum(mun.length)} cidades)</span>` : ''}</h4>
        <div class="rs-mun"></div>
        ${c ? `<div class="links-doc"><button type="button" class="btn mini rs-ficha">${icone('pessoa')}Ficha completa do candidato</button></div>` : ''}
      </article>`;
    renderTabelaMun(box.querySelector('.rs-mun'), k, b, Rm, totalMun, meuMun);
    box.querySelector('.rs-voltar').onclick = () => { st.sq = null; renderConsulta(); $('rs-texto').focus(); };
    const f = box.querySelector('.rs-ficha'); if (f) f.onclick = () => Modal.abrir(c);
  }

  // tabela de cidades: ordem crescente/decrescente, filtro por nome e "mostrar todas"
  function renderTabelaMun(alvo, k, b, Rm, totalMun, meuMun) {
    const pres = b.cd === 1;
    const desenhar = () => {
      const q = normMun(st.filtroMun);
      let lista = (k.mun || []).slice();
      if (st.ordem === 'asc') lista.reverse();
      if (q) lista = lista.filter((m) => normMun(cidade(m[0], st.sqCargo)).includes(q));
      const vis = lista.slice(0, st.limMun);
      const comVoto = new Set((k.mun || []).map((m) => m[0]));
      const semVoto = pres ? [] : Object.keys(Rm.muns).filter((m) => !comVoto.has(m)).map((m) => titulo(Rm.muns[m][0])).sort((a, c) => a.localeCompare(c, 'pt-BR'));
      alvo.innerHTML = !(k.mun || []).length ? '<p class="small muted">Sem votos por cidade nos dados abertos do TSE para este candidato.</p>' : `
        <div class="linha rs-mun-ctl">
          <button type="button" class="btn mini rs-ord" aria-label="Inverter a ordem">${icone('lista')}${st.ordem === 'desc' ? 'Mais votos primeiro' : 'Menos votos primeiro'}</button>
          <input type="search" class="rs-filtro" aria-label="Filtrar cidade" placeholder="Filtrar cidade${pres ? ' ou UF' : ''}" value="${esc(st.filtroMun)}">
        </div>
        <div style="overflow-x:auto"><table class="tabela"><thead><tr><th class="r">#</th><th>Cidade/UF</th><th class="r">Votos</th><th class="r">% dos votos do candidato</th>${pres ? '' : '<th class="r" title="Votos do candidato a cada 100 eleitores que compareceram na cidade">A cada 100 que votaram</th>'}</tr></thead><tbody>
          ${vis.map((m) => {
            const pos = (k.mun.indexOf(m)) + 1;
            const comp = pres ? 0 : (Rm.muns[m[0]] || [])[2];
            return `<tr class="${m[0] === meuMun ? 'foco' : ''}"><td class="r num">${pos}</td><td>${esc(cidade(m[0], st.sqCargo))}</td><td class="r num">${fmtNum(m[1])}</td><td class="r num">${pctTxt(m[1], totalMun)}</td>${pres ? '' : `<td class="r num">${comp ? (100 * m[1] / comp).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) : ''}</td>`}</tr>`;
          }).join('')}
        </tbody></table></div>
        ${lista.length > vis.length ? `<button type="button" class="btn mini rs-todas">Mostrar todas (${fmtNum(lista.length)})</button>` : ''}
        ${semVoto.length ? `<p class="small muted">Nenhum voto em ${fmtNum(semVoto.length)} das ${fmtNum(Object.keys(Rm.muns).length)} cidades do estado${semVoto.length <= 30 ? ': ' + esc(semVoto.join(', ')) : ''}.</p>` : ''}
        <p class="small muted">Fonte: votação por município e zona dos dados abertos do TSE${resDe(st.sqCargo).meta.munzona ? ' (arquivo gerado em ' + esc(resDe(st.sqCargo).meta.munzona) + ')' : ''}.</p>`;
      const ord = alvo.querySelector('.rs-ord'); if (ord) ord.onclick = () => { st.ordem = st.ordem === 'desc' ? 'asc' : 'desc'; desenhar(); alvo.querySelector('.rs-ord').focus(); };
      const fi = alvo.querySelector('.rs-filtro'); if (fi) fi.oninput = (e) => { st.filtroMun = e.target.value; const pos = e.target.selectionStart; desenhar(); const n = alvo.querySelector('.rs-filtro'); n.focus(); n.setSelectionRange(pos, pos); };
      const to = alvo.querySelector('.rs-todas'); if (to) to.onclick = () => { st.limMun = Infinity; desenhar(); };
    };
    desenhar();
  }

  function porUfCand(sq, b) {
    const linhas = Object.entries(b.porUf || {}).map(([u, d]) => ({ u, v: d.v[sq] || 0, val: d.tot.validos })).sort((a, c) => c.v - a.v);
    if (!linhas.length) return '';
    return `<details class="secao"><summary>${icone('seta')}<span>Votos por estado</span></summary><div class="conteudo"><div style="overflow-x:auto"><table class="tabela"><thead><tr><th>UF</th><th class="r">Votos</th><th class="r">% dos válidos no estado</th></tr></thead><tbody>
      ${linhas.map((l) => `<tr class="${l.u === perfil().uf ? 'foco' : ''}"><td>${l.u === 'ZZ' ? 'Exterior' : l.u}</td><td class="r num">${fmtNum(l.v)}</td><td class="r num">${pctTxt(l.v, l.val)}</td></tr>`).join('')}</tbody></table></div></div></details>`;
  }

  // ---------- visão geral do cargo ----------
  const sec = (id, tit, corpo, extra = '') => `<section class="card rs-sec" aria-labelledby="rot-${id}" ${extra}><h2 id="rot-${id}">${tit}</h2>${corpo}</section>`;
  const linhaCand = (sq, k, extra = '') => `<tr data-sq="${esc(sq)}"><td class="r num">${k.pos ? ordinal(k.pos) : ''}</td><td><button type="button" class="link-btn rs-abrir" data-sq="${esc(sq)}"><span class="numero">${esc(k.n)}</span> ${esc(nomeK(k))}</button><span class="small muted rs-sm"> ${esc(k.sg)}</span></td><td class="rs-lg">${pontoPartido(k.sg)}${esc(k.sg)}</td><td class="r num">${fmtNum(k.v)}</td>${extra}<td>${tagSit(k)}</td></tr>`;

  function panorama(b, Rm) {
    const t = b.tot;
    const kpi = (rot, val, sub) => `<div><b>${rot}</b><span class="num">${val}</span>${sub ? `<span class="small muted">${sub}</span>` : ''}</div>`;
    const quando = Rm.meta.dt ? `Totalização de ${esc(Rm.meta.dt)} ${esc(Rm.meta.ht || '')}; divulgado em ${esc(Rm.meta.dg)} ${esc(Rm.meta.hg)}.` : '';
    return sec('rs-pan', `Panorama — ${esc(b.nome)}${b.cd === 1 ? ' (Brasil)' : ' em ' + esc(R.meta.uf)}`, `
      <div class="rs-kpis">
        ${kpi('Eleitores aptos', fmtNum(t.eleitores))}
        ${kpi('Compareceram', fmtNum(t.comp), pctTxt(t.comp, t.eleitores))}
        ${kpi('Abstenção', fmtNum(t.abst), pctTxt(t.abst, t.eleitores))}
        ${kpi('Votos válidos', fmtNum(t.validos), pctTxt(t.validos, t.votos) + ' dos votos')}
        ${kpi('Brancos', fmtNum(t.brancos), pctTxt(t.brancos, t.votos))}
        ${kpi('Nulos', fmtNum(t.nulos), pctTxt(t.nulos, t.votos))}
        ${t.anulados ? kpi('Anulados sub judice', fmtNum(t.anulados), pctTxt(t.anulados, t.votos)) : ''}
        ${PROP(b) ? kpi('Votos de legenda', fmtNum(t.legenda), pctTxt(t.legenda, t.validos) + ' dos válidos') : ''}
        ${PROP(b) ? kpi('Quociente eleitoral', fmtNum(b.qe), `${fmtNum(t.validos)} ÷ ${b.nv} vagas`) : kpi('Vagas', fmtNum(b.nv))}
        ${b.maioria ? kpi('Maioria absoluta', fmtNum(b.maioria), 'votos para vencer no 1º turno') : ''}
      </div>
      ${b.cd === 5 ? '<p class="small muted">Para senador cada eleitor dá dois votos: o total de votos é o dobro do comparecimento.</p>' : ''}
      <p class="small muted">${quando} Seções totalizadas: ${fmtNum(t.secoesTot)} de ${fmtNum(t.secoes)} (${pctTxt(t.secoesTot, t.secoes)}).</p>`);
  }

  // cargos majoritários: o 1º colocado em destaque e os demais em barras (cor do partido, sigla escrita)
  function corrida(b) {
    if (PROP(b)) return '';
    const base = b.tot.baseMaioria || b.tot.validos;
    const lista = Object.entries(b.cand).filter(([, k]) => k.v > 0).sort((a, c) => c[1].v - a[1].v);
    if (!lista.length || !base) return '';
    const [sq1, k1] = lista[0];
    const c1 = candBase(sq1);
    const maxP = lista[0][1].v / base;
    const barra = ([sq, k]) => {
      const p = k.v / base;
      return `<li><button type="button" class="rs-barra-linha rs-abrir" data-sq="${esc(sq)}">
        <span class="rs-barra-nome"><span class="numero">${esc(k.n)}</span> ${esc(nomeK(k))} <span class="small muted">${esc(k.sg)}</span></span>
        <span class="rs-barra-pct num">${pctTxt(k.v, base)}</span>
        <span class="rs-barra" aria-hidden="true"><span style="width:${(100 * p / maxP).toFixed(1)}%;background:${corPartido(k.sg)}"></span></span>
      </button></li>`;
    };
    return sec('rs-corrida', `${esc(b.nome)}${b.cd === 1 ? ' — Brasil' : ' — ' + esc(R.meta.uf)}: votos válidos`, `
      <div class="rs-lider">
        ${c1 ? fotoHtml(c1, 'grande') : ''}
        <div class="cresce">
          <div class="small muted">${b.cd === 5 ? 'Mais votado' : '1º colocado'}</div>
          <div class="linha"><span class="numero">${esc(k1.n)}</span><b class="rs-lider-nome">${esc(nomeK(k1))}</b>${tagSit(k1)}</div>
          <div class="small">${pontoPartido(k1.sg)}${esc(k1.sg)} · ${fmtNum(k1.v)} votos</div>
        </div>
        <div class="rs-lider-pct num">${pctTxt(k1.v, base)}</div>
      </div>
      <ol class="rs-barras">${lista.slice(1, 13).map(barra).join('')}</ol>
      ${lista.length > 13 ? `<p class="small muted">Os outros ${fmtNum(lista.length - 13)} candidatos estão na tabela abaixo.</p>` : ''}
      <p class="small muted">Percentual sobre os votos válidos${b.tot.anulados ? ' (com os anulados sub judice, como o TSE)' : ''}. A cor identifica o partido; a sigla está sempre escrita ao lado.</p>`);
  }

  function eleitos(b) {
    const lista = Object.entries(b.cand).sort((a, c) => c[1].v - a[1].v);
    const els = lista.filter(([, k]) => k.e || k.pe || (k.st && norm(k.st).includes('2')) || k.p2);
    const tit = PROP(b) ? `Eleitos (${els.length} de ${b.nv} vagas)` : (els.some(([, k]) => k.e || k.pe) ? 'Eleitos' : 'No 2º turno');
    const extraCab = '<th class="r rs-lg">% válidos</th>';
    const base = b.tot.baseMaioria || b.tot.validos;
    const ex = (k) => `<td class="r num rs-lg">${pctTxt(k.v, base)}</td>`;
    const vis = lista.slice(0, st.limRank);
    return sec('rs-el', tit, `
      ${!b.oficial ? `<p class="bloco small"><b>O TSE ainda não proclamou este resultado</b> (${esc(b.aviso || 'totalização em andamento')}). Os eleitos abaixo são uma projeção pelas regras da lei.</p>` : ''}
      <div style="overflow-x:auto"><table class="tabela rs-tab"><thead><tr><th class="r">Pos.</th><th>Candidato</th><th class="rs-lg">Partido</th><th class="r">Votos</th>${extraCab}<th>Situação</th></tr></thead><tbody>
        ${els.map(([sq, k]) => linhaCand(sq, k, ex(k))).join('')}</tbody></table></div>
      <details class="secao"><summary>${icone('seta')}<span>Todos os ${fmtNum(lista.length)} candidatos, do mais ao menos votado</span></summary><div class="conteudo">
        <div style="overflow-x:auto"><table class="tabela rs-tab"><thead><tr><th class="r">Pos.</th><th>Candidato</th><th class="rs-lg">Partido</th><th class="r">Votos</th>${extraCab}<th>Situação</th></tr></thead><tbody>
        ${vis.map(([sq, k]) => linhaCand(sq, k, ex(k))).join('')}</tbody></table></div>
        ${lista.length > vis.length ? `<button type="button" class="btn mini rs-mais-rank">Mostrar mais (${fmtNum(lista.length - vis.length)} restantes)</button>` : ''}
      </div></details>`);
  }

  function maisVotosNaoEleito(b) {
    if (!PROP(b)) return '';
    const lista = Object.entries(b.cand).filter(([, k]) => !(k.e || k.pe) && k.v > b.menorEleito && norm(k.dvt).startsWith('valido')).sort((a, c) => c[1].v - a[1].v);
    if (!lista.length) return '';
    const menor = Object.entries(b.cand).filter(([, k]) => k.e || k.pe).sort((a, c) => a[1].v - c[1].v)[0];
    const vis = lista.slice(0, st.limMais);
    return sec('rs-mais', `Tiveram mais votos que um eleito e não se elegeram (${fmtNum(lista.length)})`, `
      <p class="small">O eleito com menos votos foi ${esc(nomeK(menor[1]))} (${esc(menor[1].sg)}), com <b>${fmtNum(menor[1].v)}</b>. Os candidatos abaixo tiveram mais votos e ficaram de fora porque, na eleição para deputado, as vagas são divididas <b>primeiro entre os partidos e federações</b> (pelo total de votos de cada lista) e só depois entre os mais votados de cada lista.</p>
      <div style="overflow-x:auto"><table class="tabela rs-tab"><thead><tr><th class="r">Pos.</th><th>Candidato</th><th class="rs-lg">Partido</th><th class="r">Votos</th><th>O que aconteceu</th><th>Situação</th></tr></thead><tbody>
      ${vis.map(([sq, k]) => {
        const a = b.agr[k.a];
        const motivo = a.vag ? `${esc(a.sigla)} ganhou ${a.vag} vaga(s); ficou em ${ordinal(k.lst)} na lista` : `${esc(a.sigla)} não ganhou vaga (${pct(a.votos, b.qe, 0)} do QE)`;
        return linhaCand(sq, k, `<td class="small">${motivo}${k.x && k.x.falta ? `; faltaram ${fmtNum(k.x.falta)} votos` : ''}</td>`);
      }).join('')}</tbody></table></div>
      ${lista.length > vis.length ? `<button type="button" class="btn mini rs-mais-mais">Mostrar mais (${fmtNum(lista.length - vis.length)} restantes)</button>` : ''}`);
  }

  function distribuicao(b) {
    if (!PROP(b)) return '';
    const qe = b.qe;
    const agrs = b.agr.map((a, i) => ({ a, i })).filter((x) => x.a.votos > 0).sort((x, y) => y.a.votos - x.a.votos);
    const nomesEleitos = {};
    (b.vagas || []).forEach(([sq, , i]) => { (nomesEleitos[i] = nomesEleitos[i] || []).push(nomeK(b.cand[sq])); });
    const sobras = (b.vagas || []).filter((v) => v[1] !== 'qp');
    const temM3 = sobras.some((v) => v[1] === 'm3');
    return sec('rs-dist', 'Como as vagas foram distribuídas', `
      <ol class="cl-passos small">
        <li><b>Quociente eleitoral:</b> ${fmtNum(b.tot.validos)} votos válidos ÷ ${b.nv} vagas = <b>${fmtNum(qe)}</b> votos.</li>
        <li><b>Quociente partidário:</b> cada lista ganha uma vaga a cada ${fmtNum(qe)} votos (sem a fração), se tiver candidatos com pelo menos 10% do QE (${fmtNum(Math.ceil(qe / 10))} votos). Assim foram preenchidas ${(b.vagas || []).length - sobras.length} vagas.</li>
        <li><b>Sobras:</b> ${sobras.length ? `as ${sobras.length} vagas restantes foram para as maiores médias (votos da lista ÷ vagas já ganhas + 1), entre listas com 80% do QE (${fmtNum(Math.ceil(qe * 0.8))}) e candidatos com 20% do QE (${fmtNum(Math.ceil(qe / 5))})${temM3 ? '; as que ainda sobraram foram para todas as listas, sem mínimo' : ''}.` : 'não houve.'}</li>
      </ol>
      <div style="overflow-x:auto"><table class="tabela"><thead><tr><th>Partido ou federação</th><th class="r">Votos</th><th class="r">% do QE</th><th class="r">Por quociente</th><th class="r">Por média</th><th class="r">Vagas</th><th>Eleitos</th></tr></thead><tbody>
        ${agrs.map(({ a, i }) => `<tr><td>${a.tipo === 'f' ? '' : pontoPartido(a.sigla)}${esc(a.tipo === 'f' ? agrNome(a, false) : a.sigla)}<div class="small muted">${fmtNum(a.nom)} nominais + ${fmtNum(a.leg)} de legenda</div></td><td class="r num">${fmtNum(a.votos)}</td><td class="r num">${pct(a.votos, qe, 0)}</td><td class="r num">${a.vQP}</td><td class="r num">${a.vMed}</td><td class="r num"><b>${a.vag}</b></td><td class="small">${esc((nomesEleitos[i] || []).join(', '))}</td></tr>`).join('')}
      </tbody></table></div>
      ${sobras.length ? `<h3 class="cl-sub">Ordem das vagas das sobras</h3><div style="overflow-x:auto"><table class="tabela"><thead><tr><th class="r">Vaga</th><th>Lista</th><th class="r">Média</th><th>Fase</th><th>Eleito</th></tr></thead><tbody>
        ${sobras.map((v, n) => `<tr><td class="r num">${(b.vagas.length - sobras.length) + n + 1}ª</td><td>${esc(b.agr[v[2]].sigla)}</td><td class="r num">${fmtNum(Math.round(v[3]))}</td><td class="small">${v[1] === 'm2' ? '2ª fase (80% / 20%)' : 'última fase (todos)'}</td><td>${esc(nomeK(b.cand[v[0]]))}</td></tr>`).join('')}</tbody></table></div>` : ''}
      <p class="small muted">Cálculo refeito com as regras da lei e conferido com o resultado oficial do TSE (o mesmo quociente, as mesmas vagas por lista e os mesmos eleitos).</p>`);
  }

  // ---------- estatísticas ----------
  function estatisticas(b, Rm) {
    const els = Object.entries(b.cand).filter(([, k]) => k.e || k.pe);
    const partes = [];
    // perfil dos eleitos x candidatos (dados do registro de candidatura)
    const todos = Object.keys(b.cand).map(candBase).filter(Boolean);
    const eleitosC = els.map(([sq]) => candBase(sq)).filter(Boolean);
    if (eleitosC.length) {
      const conta = (lista, f) => lista.filter(f).length;
      const mulher = (c) => norm(c.genero).startsWith('femin');
      const idade = (l) => { const v = l.map((c) => c.idade).filter(Boolean); return v.length ? Math.round(v.reduce((s, x) => s + x, 0) / v.length) : null; };
      const reel = conta(eleitosC, (c) => c.reeleicao);
      partes.push(`<div class="rs-kpis">
        <div><b>Mulheres eleitas</b><span class="num">${conta(eleitosC, mulher)} de ${eleitosC.length}</span><span class="small muted">${pctTxt(conta(todos, mulher), todos.length)} das candidaturas eram de mulheres</span></div>
        <div><b>Reeleitos</b><span class="num">${reel} de ${eleitosC.length}</span><span class="small muted">disputavam a reeleição: ${conta(todos, (c) => c.reeleicao)}</span></div>
        <div><b>Idade média dos eleitos</b><span class="num">${idade(eleitosC) || '—'} anos</span><span class="small muted">dos candidatos: ${idade(todos) || '—'}</span></div>
      </div>`);
      const porPartido = {};
      eleitosC.forEach((c) => { porPartido[c.partido] = (porPartido[c.partido] || 0) + 1; });
      partes.push(`<p class="small"><b>Eleitos por partido:</b> ${Object.entries(porPartido).sort((a, c) => c[1] - a[1]).map(([p, n]) => `${esc(p)} ${n}`).join(' · ')}</p>`);
    }
    // gasto declarado por voto (prestação de contas da campanha)
    const comConta = Object.entries(b.cand).map(([sq, k]) => ({ sq, k, c: candBase(sq) })).filter((x) => x.c && x.c.contas && x.c.contas.desp && x.k.v > 0)
      .sort((a, c) => c.k.v - a.k.v).slice(0, PROP(b) ? Math.max(b.nv * 2, 10) : 12);
    if (comConta.length) {
      const datas = [...new Set(comConta.map((x) => x.c.contas.data).filter(Boolean))].sort();
      partes.push(`<h3 class="cl-sub">Gasto de campanha declarado por voto</h3>
        <p class="small muted">Despesas contratadas declaradas ao TSE ÷ votos recebidos, para os ${comConta.length} mais votados que já entregaram a prestação de contas. Até a prestação final (após a eleição), os valores são parciais${datas.length ? ` (entregas até ${esc(datas[datas.length - 1])})` : ''}.</p>
        <div style="overflow-x:auto"><table class="tabela"><thead><tr><th>Candidato</th><th class="r">Votos</th><th class="r">Gasto declarado</th><th class="r">Por voto</th><th>Situação</th></tr></thead><tbody>
        ${comConta.map((x) => `<tr><td><button type="button" class="link-btn rs-abrir" data-sq="${esc(x.sq)}">${esc(nomeK(x.k))}</button> <span class="small muted">${esc(x.k.sg)}</span></td><td class="r num">${fmtNum(x.k.v)}</td><td class="r num">${fmtMoeda(x.c.contas.desp)}</td><td class="r num">${fmtMoeda(x.c.contas.desp / x.k.v)}</td><td>${tagSit(x.k)}</td></tr>`).join('')}</tbody></table></div>`);
    }
    // puxadores e concentração dos eleitos
    if (PROP(b) && els.length) {
      const pux = els.filter(([, k]) => k.x && k.x.sobra).sort((a, c) => c[1].v - a[1].v);
      if (pux.length) partes.push(`<h3 class="cl-sub">Votos acima do quociente eleitoral</h3><p class="small">Quem teve mais votos que o quociente (${fmtNum(b.qe)}) ajudou a lista a ganhar outras vagas: ${pux.map(([, k]) => `${esc(nomeK(k))} (${esc(k.sg)}, ${fmtNum(k.v)} votos, ${fmtNum(k.x.sobra)} acima do QE)`).join('; ')}.</p>`);
    }
    if (els.length && els.some(([, k]) => (k.mun || []).length)) {
      const conc = els.filter(([, k]) => (k.mun || []).length).map(([sq, k]) => ({ sq, k, top: k.mun[0], p: k.mun[0][1] / k.mun.reduce((s, m) => s + m[1], 0) })).sort((a, c) => c.p - a.p);
      partes.push(`<h3 class="cl-sub">Onde os eleitos tiveram mais votos</h3><div style="overflow-x:auto"><table class="tabela"><thead><tr><th>Eleito</th><th>Cidade com mais votos</th><th class="r">Votos lá</th><th class="r">% do total do candidato</th><th class="r">Cidades com voto</th></tr></thead><tbody>
        ${conc.map((x) => `<tr><td><button type="button" class="link-btn rs-abrir" data-sq="${esc(x.sq)}">${esc(nomeK(x.k))}</button> <span class="small muted">${esc(x.k.sg)}</span></td><td>${esc(cidade(x.top[0], b.nome))}</td><td class="r num">${fmtNum(x.top[1])}</td><td class="r num">${(100 * x.p).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%</td><td class="r num">${fmtNum(x.k.mun.length)}</td></tr>`).join('')}</tbody></table></div>`);
    }
    // mais votado em cada cidade e participação por cidade
    partes.push('<div class="rs-cidades"></div>');
    return sec('rs-est', 'Estatísticas', partes.join(''));
  }

  // ---------- mapa: mais votado em cada cidade (malha do IBGE em data/mapa_XX.js) ----------
  const Mapa = {
    cache: {},
    carregar(uf) {
      if (!uf) return Promise.resolve(null);
      if (uf in this.cache) return Promise.resolve(this.cache[uf]);
      const pronto = (m) => (this.cache[uf] = m && m.m ? m : null);
      if (window['MAPA_' + uf]) return Promise.resolve(pronto(window['MAPA_' + uf]));
      const emb = document.getElementById('mapa-' + uf);   // versão celular: JSON embutido
      if (emb) { try { return Promise.resolve(pronto(JSON.parse(emb.textContent))); } catch (e) { return Promise.resolve(pronto(null)); } }
      if (Dados.manifest().mobile) return Promise.resolve(pronto(null));
      return new Promise((resolve) => {
        const sc = document.createElement('script');
        sc.src = 'data/mapa_' + uf + '.js';
        sc.onload = () => resolve(pronto(window['MAPA_' + uf]));
        sc.onerror = () => resolve(pronto(null));
        document.head.appendChild(sc);
      });
    },
  };

  function mapaCidades(b, top, muns, meu) {
    const uf = R && R.meta.uf;
    const M = uf && Mapa.cache[uf];
    if (!M || Object.keys(M.m).length < 2) return '';   // DF: um município só, o mapa não diz nada
    const lideres = {};
    const paths = Object.entries(M.m).map(([cd, d]) => {
      const t = top[cd];
      const k = t && t.sq && b.cand[t.sq];
      const nome = cidade(cd, b.nome);
      if (!k) return `<path d="${d}" class="sem"><title>${esc(nome)}: sem votos nos dados</title></path>`;
      const p = t.tot ? t.v / t.tot : 0;
      // quanto maior a fatia do mais votado na cidade, mais forte a cor
      const forca = Math.round(35 + 65 * Math.min(1, Math.max(0, (p - 0.15) / 0.55)));
      (lideres[t.sq] = lideres[t.sq] || { k, n: 0 }).n++;
      return `<path d="${d}" data-sq="${esc(t.sq)}" class="${cd === meu ? 'meu' : ''}" style="fill:color-mix(in srgb, ${corPartido(k.sg)} ${forca}%, var(--surface))"><title>${esc(nome)}: ${esc(nomeK(k))} (${esc(k.sg)}), ${fmtNum(t.v)} votos, ${pctTxt(t.v, t.tot)} dos nominais</title></path>`;
    }).join('');
    const leg = Object.entries(lideres).sort((a, c) => c[1].n - a[1].n);
    return `<h3 class="cl-sub">Mapa: mais votado em cada cidade${b.cd === 1 ? ` (${esc(uf)})` : ''}</h3>
      <div class="rs-mapa">
        <svg viewBox="${M.vb}" role="img" aria-label="Mapa de ${esc(uf)} com o mais votado para ${esc(b.nome.toLowerCase())} em cada cidade. A mesma informação está na tabela abaixo.">${paths}</svg>
        <ul class="rs-mapa-leg">${leg.map(([sq, x]) => `<li><button type="button" class="link-btn rs-abrir" data-sq="${esc(sq)}">${pontoPartido(x.k.sg)}${esc(nomeK(x.k))}</button> <span class="small muted">${esc(x.k.sg)} · ${x.n} ${x.n === 1 ? 'cidade' : 'cidades'}</span></li>`).join('')}</ul>
      </div>
      <p class="small muted">Cor do partido do mais votado; quanto mais forte, maior a fatia dele nos votos nominais da cidade. Passe o mouse ou toque numa cidade para ver os números; clique para abrir o candidato.${meu ? ' A cidade do seu perfil tem contorno destacado.' : ''} Contornos: malha municipal do IBGE.</p>`;
  }

  function renderCidades(alvo, b, Rm) {
    if (!alvo) return;
    const pres = b.cd === 1;
    const top = {};
    Object.entries(b.cand).forEach(([sq, k]) => (k.mun || []).forEach(([m, v]) => {
      const t = top[m] || (top[m] = { v: 0, sq: null, tot: 0 });
      t.tot += v;
      if (v > t.v) { t.v = v; t.sq = sq; }
    }));
    let muns = Object.keys(top).filter((m) => !pres || (Rm.muns[m] || [])[1] === (R ? R.meta.uf : ''));
    if (pres && !muns.length) muns = Object.keys(top);
    const meu = munPerfil(b.nome);
    const linhas = muns.map((m) => {
      const info = pres ? (R && R.muns[m]) : Rm.muns[m];
      return { m, t: top[m], el: info ? info[1] : 0, comp: info ? info[2] : 0, abst: info ? info[3] : 0 };
    });
    const ords = {
      abst: (a, c) => (c.abst / (c.el || 1)) - (a.abst / (a.el || 1)),
      absta: (a, c) => (a.abst / (a.el || 1)) - (c.abst / (c.el || 1)),
      nome: (a, c) => cidade(a.m, b.nome).localeCompare(cidade(c.m, b.nome), 'pt-BR'),
      el: (a, c) => c.el - a.el,
    };
    linhas.sort(ords[st.ordCidades] || ords.abst);
    if (meu) { const i = linhas.findIndex((l) => l.m === meu); if (i > 0) linhas.unshift(linhas.splice(i, 1)[0]); }
    const vis = linhas.slice(0, st.limCidades);
    alvo.innerHTML = mapaCidades(b, top, muns, meu) + `<h3 class="cl-sub">Cidade por cidade: participação e mais votado${pres ? ` (${esc(R ? R.meta.uf : '')})` : ''}</h3>
      <div class="linha rs-mun-ctl"><label class="small" for="rs-ord-cid">Ordenar por</label><select id="rs-ord-cid">
        <option value="abst">Maior abstenção</option><option value="absta">Menor abstenção</option><option value="el">Mais eleitores</option><option value="nome">Nome da cidade</option></select></div>
      <div style="overflow-x:auto"><table class="tabela"><thead><tr><th>Cidade</th><th class="r">Eleitores</th><th class="r">Compareceram</th><th class="r">Abstenção</th><th>Mais votado para ${esc(b.nome.toLowerCase())}</th><th class="r">Votos</th></tr></thead><tbody>
      ${vis.map((l) => { const k = b.cand[l.t.sq]; return `<tr class="${l.m === meu ? 'foco' : ''}"><td>${esc(cidade(l.m, b.nome))}</td><td class="r num">${fmtNum(l.el)}</td><td class="r num">${pctTxt(l.comp, l.el)}</td><td class="r num">${pctTxt(l.abst, l.el)}</td><td>${k ? `<button type="button" class="link-btn rs-abrir" data-sq="${esc(l.t.sq)}">${esc(nomeK(k))}</button> <span class="small muted">${esc(k.sg)}</span>` : ''}</td><td class="r num">${fmtNum(l.t.v)}${l.t.tot ? ` <span class="small muted">(${pctTxt(l.t.v, l.t.tot)})</span>` : ''}</td></tr>`; }).join('')}
      </tbody></table></div>
      ${linhas.length > vis.length ? `<button type="button" class="btn mini rs-todas-cid">Mostrar todas (${fmtNum(linhas.length)})</button>` : ''}
      <p class="small muted">Participação: comparecimento e abstenção sobre os eleitores aptos da cidade. "Votos" do mais votado: entre parênteses, a fatia dele nos votos nominais da cidade para este cargo.</p>`;
    alvo.querySelector('#rs-ord-cid').value = st.ordCidades;
    alvo.querySelector('#rs-ord-cid').onchange = (e) => { st.ordCidades = e.target.value; renderCidades(alvo, b, Rm); };
    const t = alvo.querySelector('.rs-todas-cid'); if (t) t.onclick = () => { st.limCidades = Infinity; renderCidades(alvo, b, Rm); };
    ligarAbrir(alvo, b.nome);
    alvo.querySelectorAll('.rs-mapa path[data-sq]').forEach((pt) => { pt.onclick = () => { $('rs-texto').value = ''; st.texto = ''; abrir(pt.dataset.sq, b.nome); }; });
  }

  function presPorUf(b) {
    if (b.cd !== 1 || !b.porUf) return '';
    const ordem = Object.entries(b.cand).sort((a, c) => c[1].v - a[1].v).slice(0, 2);
    return sec('rs-uf', 'Presidente por estado', `<div style="overflow-x:auto"><table class="tabela"><thead><tr><th>UF</th><th class="r">Votos válidos</th>${ordem.map(([, k]) => `<th class="r">${esc(nomeK(k))}</th>`).join('')}<th>Mais votado</th></tr></thead><tbody>
      ${Object.entries(b.porUf).sort((a, c) => a[0].localeCompare(c[0])).map(([u, d]) => {
        const mv = Object.entries(d.v).sort((a, c) => c[1] - a[1])[0];
        return `<tr class="${u === perfil().uf ? 'foco' : ''}"><td>${u === 'ZZ' ? 'Exterior' : u}</td><td class="r num">${fmtNum(d.tot.validos)}</td>${ordem.map(([sq]) => `<td class="r num">${pctTxt(d.v[sq] || 0, d.tot.validos)}</td>`).join('')}<td>${mv ? esc(nomeK(b.cand[mv[0]])) : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`);
  }

  function ligarAbrir(raiz, cargo) {
    raiz.querySelectorAll('.rs-abrir').forEach((bt) => { bt.onclick = () => { $('rs-texto').value = ''; st.texto = ''; abrir(bt.dataset.sq, cargo); }; });
  }

  function render() {
    preencherFiltros();
    renderConsulta();
    const box = $('rs-conteudo');
    const b = blocoDe(st.cargo);
    const Rm = resDe(st.cargo);
    if (!b) {
      box.innerHTML = `<div class="vazio" style="margin-top:16px">${R === undefined ? 'Carregando resultados…' : 'Resultados ainda não disponíveis para este estado. Rode <code>python scripts/fetch_resultados.py</code> e <code>python scripts/build_resultados.py</code>.'}</div>`;
      return;
    }
    box.innerHTML = panorama(b, Rm) + corrida(b) + eleitos(b) + maisVotosNaoEleito(b) + distribuicao(b) + presPorUf(b) + estatisticas(b, Rm);
    renderCidades(box.querySelector('.rs-cidades'), b, Rm);
    ligarAbrir(box, st.cargo);
    const mr = box.querySelector('.rs-mais-rank'); if (mr) mr.onclick = () => { st.limRank += 100; render(); box.querySelector('#rot-rs-el').closest('section').querySelector('details').open = true; };
    const mm = box.querySelector('.rs-mais-mais'); if (mm) mm.onclick = () => { st.limMais += 100; render(); };
  }

  function renderFixos() {
    $('rs-fontes').innerHTML = FONTES.map(([n, u, d]) => `<div><b><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)} ${icone('externo')}</a></b>${esc(d)}</div>`).join('');
    const m = (R || RB || {}).meta;
    $('rs-rodape').textContent = m && m.dg ? `Resultados divulgados pelo TSE em ${m.dg} ${m.hg}. Votos por cidade: dados abertos do TSE${m.munzona ? ' gerados em ' + m.munzona : ''}.` : '';
    $('rs-status').innerHTML = !R && !RB ? '' : `<div class="aviso rs-aviso">${icone('alerta')}<span><b>1º turno — 4/10/2026.</b> Números oficiais da totalização do TSE. Podem mudar se a Justiça Eleitoral julgar candidaturas sub judice ou recontar votos. Presidente e governadores sem maioria absoluta disputam o 2º turno em 25/10.</span></div>`;
  }

  // vindo da ficha no mesmo documento (versão celular) ou de um hash novo: abre no candidato
  async function irPara(sq, ufC) {
    if (ufC && ufC !== 'BR' && ufC !== st.uf) { ufVer = ufC; await carregar(); }
    const cargo = CARGOS_ORDEM.find((c) => { const b = blocoDe(c); return b && b.cand[sq]; });
    if (!cargo) return;
    $('rs-texto').value = ''; st.texto = '';
    abrir(sq, cargo);
  }
  document.addEventListener('tela:mudou', (e) => {
    if (e.detail.id !== 'tela-resultados' || !window.App.resultadosSq) return;
    const sq = window.App.resultadosSq, ufC = window.App.resultadosUf; window.App.resultadosSq = null; window.App.resultadosUf = null;
    irPara(sq, ufC);
  });

  async function carregar() {
    st.uf = ufVer || perfil().uf;
    if (st.uf === 'BR') st.uf = 'RO';
    R = undefined;
    render();
    const ufs = [st.uf, 'BR'].filter((u) => (Dados.manifest().ufs || []).includes(u));
    const [r, rb, lista] = await Promise.all([Res.carregar(st.uf), Res.carregar('BR'), Dados.carregarVarias(ufs), Mapa.carregar(st.uf)]);
    R = r; RB = rb; cands = {};
    lista.forEach((c) => { cands[c.sq] = c; });
    if (st.sq && !CARGOS_ORDEM.some((c) => { const b = blocoDe(c); return b && b.cand[st.sq]; })) st.sq = null;
    renderFixos(); render();
  }
  document.addEventListener('perfil:mudou', () => { ufVer = null; carregar(); });

  carregar().then(() => { if (inicial) irPara(inicial.sq, inicial.uf); });
})();
