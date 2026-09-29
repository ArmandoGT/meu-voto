/* perfil.js — aba "Perfil": onde o eleitor vota (UF e município), resumo dos critérios e posições nas votações.
   Tudo fica no navegador (Store). Mudar o Perfil dispara 'perfil:mudou' e as outras telas se recalculam. */
(function () {
  'use strict';
  const { norm, normMun, esc, titulo, fmtData, nomeMateria, votoTag, Dados, Store, Telas, perfil, setPerfil, temEmendasMun, montarTopo } = window.App;
  montarTopo();
  const $ = (id) => document.getElementById(id);
  if (!$('tela-perfil')) return;
  const MUN = window.MUNICIPIOS || {};
  const m = Dados.manifest();

  // links internos (data-tela) desta página que não passam pela barra de navegação
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-tela]');
    if (!a || a.closest('.modal, .topbar, .bottom-nav') || !document.getElementById(a.dataset.tela)) return;
    e.preventDefault(); Telas.mostrar(a.dataset.tela);
  });

  // ---------- onde você vota ----------
  const selUF = $('pf-uf'), selMun = $('pf-mun');
  const ufs = [...new Set([...m.ufs.filter((u) => u !== 'BR'), ...Object.keys(MUN)])].sort();
  selUF.innerHTML = ufs.map((u) => `<option value="${u}">${u}</option>`).join('');
  function preencherMun() {
    const p = perfil();
    const lista = MUN[p.uf] || [];
    selMun.innerHTML = '<option value="">Escolha o município</option>' + lista.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join('');
    const atual = lista.find((x) => normMun(x) === normMun(p.mun));
    selMun.value = atual || '';
    selMun.disabled = !lista.length;
  }
  function status() {
    const p = perfil();
    const dadosUF = m.ufs.includes(p.uf);
    const partes = [];
    partes.push(p.mun ? `Seu perfil: <b>${esc(titulo(p.mun))}/${esc(p.uf)}</b>.` : `Seu perfil: <b>${esc(p.uf)}</b>, sem município. Os critérios locais ficam desligados até você escolher.`);
    if (!dadosUF) partes.push('Ainda não há candidatos desta UF na base.');
    if (p.mun) partes.push(temEmendasMun() ? 'Emendas por município: disponíveis.' : 'Emendas por município: ainda não disponíveis para esta UF (só RO por enquanto); o critério de emendas fica de fora do cálculo.');
    $('pf-status').innerHTML = partes.join(' ');
  }
  selUF.onchange = () => setPerfil({ uf: selUF.value, mun: '' });
  selMun.onchange = () => setPerfil({ mun: selMun.value });

  // ---------- resumo dos critérios (vem do Meu voto) ----------
  function criterios() {
    const box = $('pf-criterios');
    const lista = (window.App.criteriosResumo || (() => []))();
    const ligados = lista.filter((c) => c.ativo);
    box.innerHTML = ligados.length
      ? `<ul class="pf-lista">${ligados.map((c) => `<li><span>${esc(c.rotulo)}</span>${c.excluir ? '<span class="tag plain">exclusão</span>' : `<span class="tag plain">peso ${c.peso}</span>`}</li>`).join('')}</ul>`
      : '<p class="small muted">Nenhum critério ligado.</p>';
  }

  // ---------- posições nas votações ----------
  const NOME_CASA = { alero: 'ALE-RO', camara: 'Câmara', senado: 'Senado' };
  function posicoes() {
    const box = $('pf-posicoes');
    const itens = Object.entries(Store.posicoes()).map(([k, v]) => {
      const i = k.indexOf(':'); const casa = k.slice(0, i), id = k.slice(i + 1);
      return { k, v, casa, x: window.App.acharVotacao(casa, id) };
    }).sort((a, b) => ((b.x || {}).d || '').localeCompare((a.x || {}).d || ''));
    if (!itens.length) { box.innerHTML = '<p class="small">Você ainda não marcou nenhuma posição.</p>'; return; }
    box.innerHTML = `<p class="small"><b>${itens.length}</b> posição(ões) marcada(s).</p><ul class="pf-lista pf-pos">${itens.map((t) => `<li>
        <span><span class="muted small">${esc(NOME_CASA[t.casa] || t.casa)} · ${t.x ? fmtData(t.x.d) : ''}</span> ${t.x ? esc(t.x.ident || nomeMateria(t.x)) : 'votação não encontrada nos dados atuais'}${t.x && /^Veto/.test(t.x.t || '') ? ' <span class="small muted">(Sim = manter o veto)</span>' : ''}
          ${t.x ? `<span class="small muted pf-ementa">${esc((t.x.e || t.x.desc || '').slice(0, 140))}</span>` : ''}</span>
        <span class="pf-acao">Você: ${votoTag(t.v)} <button type="button" class="btn mini pf-remove" data-k="${esc(t.k)}">Remover</button></span></li>`).join('')}</ul>`;
    box.querySelectorAll('.pf-remove').forEach((b) => b.onclick = () => { Store.setPosicao(b.dataset.k, null); render(); });
  }

  function render() {
    const p = perfil();
    selUF.value = ufs.includes(p.uf) ? p.uf : ufs[0];
    preencherMun(); status(); criterios(); posicoes();
  }
  document.addEventListener('perfil:mudou', render);
  document.addEventListener('store:mudou', () => { criterios(); posicoes(); });
  document.addEventListener('tela:mudou', (e) => { if (e.detail.id === 'tela-perfil') render(); });
  render();
})();
