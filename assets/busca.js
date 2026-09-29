/* busca.js — página de pesquisa geral */
(function () {
  'use strict';
  const { norm, esc, titulo, icone, Dados, Store, Modal, cardCandidato, montarTopo, sitClasse, CARGOS_ORDEM, perfil, munFoco, pctVotosEm } = window.App;
  montarTopo();
  window.App.Telas.iniciar('tela-busca');

  const $ = (id) => document.getElementById(id);
  const PAGINA = 60;
  let universo = [];
  let resultado = [];
  let mostrados = 0;

  const m = Dados.manifest();
  $('fonte-info').textContent = m.amostra
    ? 'Base: amostra fictícia para desenvolvimento.'
    : `Base oficial do TSE gerada em ${m.geradoEm} · ${m.ufs.length} UFs · ${Object.values(m.contagens).reduce((a, c) => a + c.total, 0).toLocaleString('pt-BR')} candidatos.`;
  $('q').parentElement.querySelector('.ico-wrap').outerHTML = icone('busca');
  $('filtros-avancados').querySelector('.ico-seta').outerHTML = icone('seta').replace('class="ico"', 'class="ico seta"');

  // município e UF do Perfil
  const pctFoco = (c) => { if (!munFoco()) return -1; const v = pctVotosEm(c, munFoco()); return v && v.pct != null ? v.pct : -1; };
  function rotulosPerfil() {
    const mun = titulo(munFoco());
    $('o-pctfoco').textContent = mun ? `% de votos em ${mun} (eleição anterior)` : '% de votos no meu município (defina no Perfil)';
    $('rot-pctfoco').textContent = mun ? `Mín. % de votos em ${mun} (eleição anterior)` : 'Mín. % de votos no meu município (defina no Perfil)';
    $('f-pctfoco').disabled = !mun;
    const o = selUF.querySelector('option[value="PERFIL"]');
    if (o) o.textContent = `Meu estado (${perfil().uf}) + Presidente`;
  }
  const totalVotos = (c) => ((c.votosAnt || [])[0] || {}).total || 0;

  // ---- selects ----
  const ufs = m.ufs.filter((u) => u !== 'BR');
  const selUF = $('f-uf');
  selUF.innerHTML = `<option value="PERFIL">Meu estado + Presidente</option><option value="TODAS">Todas as UFs (Brasil)</option><option value="BR">Presidente (BR)</option>` +
    ufs.map((u) => `<option value="${u}">${u}${m.contagens[u] ? ' (' + m.contagens[u].total + ')' : ''}</option>`).join('');
  selUF.value = (Store.ler().ufBusca || 'PERFIL').replace('RO+BR', 'PERFIL');   // 'RO+BR' = valor antigo, antes do Perfil
  if (![...selUF.options].some((o) => o.value === selUF.value)) selUF.value = 'PERFIL';
  rotulosPerfil();

  const opcoes = (id, valores, fmt = (v) => v, primeira = 'Todos') => {
    const s = $(id); const atual = s.value;
    s.innerHTML = `<option value="">${primeira}</option>` + valores.map((v) => `<option value="${esc(v)}">${esc(fmt(v))}</option>`).join('');
    if ([...s.options].some((o) => o.value === atual)) s.value = atual;
  };
  const unicos = (lista, campo) => [...new Set(lista.map((c) => c[campo]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));

  function popularFiltros() {
    const cargos = unicos(universo, 'cargo').sort((a, b) => CARGOS_ORDEM.indexOf(a) - CARGOS_ORDEM.indexOf(b));
    const ufsNoUniverso = new Set(universo.map((c) => c.uf));
    const vagasDe = (cg) => { const v = m.vagas || {}; const l = [...ufsNoUniverso].filter((u) => v[u] && v[u][cg]); return l.length === 1 ? v[l[0]][cg] : null; };
    opcoes('f-cargo', cargos, (cg) => { const v = vagasDe(cg); return v ? `${cg} (${v} ${v > 1 ? 'vagas' : 'vaga'})` : cg; });
    opcoes('f-partido', unicos(universo, 'partido'));
    opcoes('f-genero', unicos(universo, 'genero'), titulo);
    opcoes('f-ufnasc', unicos(universo, 'ufNasc'), (v) => v, 'Todas');
    opcoes('f-instr', unicos(universo, 'instrucao'), titulo, 'Todas');
    $('lista-mun').innerHTML = unicos(universo, 'munNasc').map((v) => `<option value="${esc(titulo(v))}">`).join('');
    const munsHist = [...new Set(universo.flatMap((c) => c.munHist || []))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    $('lista-munhist').innerHTML = munsHist.map((v) => `<option value="${esc(titulo(v))}">`).join('');
    const tags = Store.todasTags();
    $('f-tag').innerHTML = tags.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join('') || '<option value="">(nenhuma tag ainda)</option>';
  }

  // ---- carga ----
  async function carregar() {
    const v = selUF.value;
    Store.ler().ufBusca = v; Store.salvar();
    $('status-carga').textContent = 'Carregando…';
    let lista;
    if (v === 'TODAS') lista = await Dados.carregarVarias(m.ufs);
    else if (v === 'PERFIL') lista = await Dados.carregarVarias([perfil().uf, 'BR'].filter((u) => m.ufs.includes(u)));
    else lista = await Dados.carregarUF(v);
    universo = lista;
    $('status-carga').textContent = `${universo.length.toLocaleString('pt-BR')} candidatos carregados.`;
    popularFiltros();
    filtrar();
  }

  // ---- filtro ----
  const IDS_TEXTO = ['f-mun', 'f-ocup', 'f-idmin', 'f-idmax', 'f-munhist', 'f-pctfoco'];
  const IDS_SELECT = ['f-cargo', 'f-partido', 'f-sit', 'f-reel', 'f-genero', 'f-ufnasc', 'f-instr', 'f-tag', 'f-eleito', 'f-motivo', 'f-meus'];

  function filtrar() {
    const q = norm($('q').value);
    const qDigitos = /^\d+$/.test(q);
    const f = {
      cargo: $('f-cargo').value, partido: $('f-partido').value, sit: $('f-sit').value, reel: $('f-reel').value,
      genero: $('f-genero').value, mun: norm($('f-mun').value), ufnasc: $('f-ufnasc').value,
      idmin: +$('f-idmin').value || 0, idmax: +$('f-idmax').value || 999, instr: $('f-instr').value,
      ocup: norm($('f-ocup').value), meus: $('f-meus').value, tag: $('f-tag').value,
      munhist: norm($('f-munhist').value), eleito: $('f-eleito').value, motivo: $('f-motivo').value,
      pctfoco: $('f-pctfoco').value === '' ? null : +$('f-pctfoco').value,
    };
    resultado = universo.filter((c) => {
      if (q) {
        if (qDigitos) { if (!(c.nr || '').startsWith(q)) return false; }
        else if (!norm(c.urna).includes(q) && !norm(c.nome).includes(q) && !norm(c.social).includes(q)) return false;
      }
      if (f.cargo && c.cargo !== f.cargo) return false;
      if (f.partido && c.partido !== f.partido) return false;
      if (f.sit && sitClasse(c.sit) !== f.sit) return false;
      if (f.reel && (c.reeleicao ? '1' : '0') !== f.reel) return false;
      if (f.genero && c.genero !== f.genero) return false;
      if (f.mun && !norm(c.munNasc).includes(f.mun)) return false;
      if (f.ufnasc && c.ufNasc !== f.ufnasc) return false;
      if (f.munhist && !(c.munHist || []).some((x) => norm(x).includes(f.munhist))) return false;
      if (f.eleito && ((c.vezesEleito || 0) > 0 ? '1' : '0') !== f.eleito) return false;
      if (f.motivo && ((c.motivos && c.motivos.length) ? '1' : '0') !== f.motivo) return false;
      if (f.pctfoco != null && pctFoco(c) < f.pctfoco) return false;
      if (c.idade != null && (c.idade < f.idmin || c.idade > f.idmax)) return false;
      if (f.instr && c.instrucao !== f.instr) return false;
      if (f.ocup && !norm(c.ocupacao).includes(f.ocup)) return false;
      if (f.meus === 'fav' && !Store.favorito(c.sq)) return false;
      if (f.meus === 'nota' && !Store.nota(c.sq)) return false;
      if (f.meus === 'tag' && !(f.tag ? Store.temTag(c.sq, f.tag) : Store.tags(c.sq).length)) return false;
      return true;
    });
    const ord = $('f-ord').value;
    const cmp = {
      urna: (a, b) => (a.urna || a.nome).localeCompare(b.urna || b.nome, 'pt-BR'),
      nr: (a, b) => (a.nr || '').localeCompare(b.nr || '', undefined, { numeric: true }),
      partido: (a, b) => (a.partido || '').localeCompare(b.partido || '') || (a.nr || '').localeCompare(b.nr || '', undefined, { numeric: true }),
      idade: (a, b) => (a.idade || 0) - (b.idade || 0),
      cargo: (a, b) => (CARGOS_ORDEM.indexOf(a.cargo) - CARGOS_ORDEM.indexOf(b.cargo)) || (a.urna || '').localeCompare(b.urna || '', 'pt-BR'),
      eleito: (a, b) => (b.vezesEleito || 0) - (a.vezesEleito || 0) || (b.vezesCand || 0) - (a.vezesCand || 0),
      bens: (a, b) => (b.bens || 0) - (a.bens || 0),
      pctfoco: (a, b) => pctFoco(b) - pctFoco(a) || totalVotos(b) - totalVotos(a),
      votos: (a, b) => totalVotos(b) - totalVotos(a),
    }[ord];
    resultado.sort(cmp);
    mostrados = 0;
    $('grade').innerHTML = '';
    $('contador').textContent = `${resultado.length.toLocaleString('pt-BR')} candidato(s)`;
    const ativos = IDS_TEXTO.filter((id) => $(id).value !== '').length + IDS_SELECT.filter((id) => $(id).value !== '' && !(id === 'f-tag' && $('f-meus').value !== 'tag')).length;
    $('filtros-ativos').textContent = ativos ? `· ${ativos} ativo(s)` : '';
    if (!resultado.length) $('grade').innerHTML = '<div class="vazio">Nenhum candidato com esses filtros.</div>';
    mais();
  }

  function mais() {
    const fatia = resultado.slice(mostrados, mostrados + PAGINA);
    const frag = document.createDocumentFragment();
    fatia.forEach((c) => { const card = cardCandidato(c); card.onclick = () => Modal.abrir(c); frag.appendChild(card); });
    $('grade').appendChild(frag);
    mostrados += fatia.length;
    $('btn-mais').style.display = mostrados < resultado.length ? '' : 'none';
    $('btn-mais').textContent = `Carregar mais (${(resultado.length - mostrados).toLocaleString('pt-BR')} restantes)`;
  }

  // ---- eventos ----
  let timer;
  const debounce = () => { clearTimeout(timer); timer = setTimeout(filtrar, 120); };
  ['q', ...IDS_TEXTO].forEach((id) => $(id).addEventListener('input', debounce));
  [...IDS_SELECT, 'f-ord'].forEach((id) => $(id).addEventListener('change', filtrar));
  $('f-meus').addEventListener('change', () => $('campo-tag').classList.toggle('hidden', $('f-meus').value !== 'tag'));
  selUF.addEventListener('change', carregar);
  $('btn-mais').onclick = mais;
  $('btn-limpar-filtros').onclick = () => {
    $('q').value = '';
    IDS_TEXTO.forEach((id) => $(id).value = '');
    IDS_SELECT.forEach((id) => $(id).value = '');
    $('campo-tag').classList.add('hidden');
    filtrar();
  };
  document.addEventListener('modal:fechou', () => { popularFiltros(); filtrar(); });
  document.addEventListener('perfil:mudou', () => { rotulosPerfil(); if (selUF.value === 'PERFIL') carregar(); else filtrar(); });

  carregar();
})();
