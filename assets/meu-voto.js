/* meu-voto.js — motor de critérios + ranking + escolhas + cola + painéis de apoio */
(function () {
  'use strict';
  const { emendasFoco, pctFundoPublico, norm, normMun, esc, titulo, el, icone, fmtNum, Dados, Store, Modal, montarTopo, fotoHtml, fotoUrl, sitClasse, CARGOS_ORDEM, VAGAS, perfil, munFoco, setPerfil, temEmendasMun, concordancia, pctVotosEm, linkPje } = window.App;
  montarTopo();
  const $ = (id) => document.getElementById(id);
  window.App.Telas.iniciar('tela-voto');
  const atalho = $('atalho-colinha');
  if (atalho) atalho.onclick = (e) => { e.preventDefault(); window.App.Telas.mostrar('tela-cola'); };
  const trocaIcone = (classe, nome) => document.querySelectorAll('.' + classe).forEach((x) => x.outerHTML = icone(nome));
  trocaIcone('ico-baixar', 'baixar'); trocaIcone('ico-subir', 'subir'); trocaIcone('ico-imprimir', 'imprimir'); trocaIcone('ico-doc', 'doc'); trocaIcone('ico-externo', 'externo'); trocaIcone('ico-urna', 'urna'); trocaIcone('ico-voto', 'voto');
  const atalhoVoto = $('atalho-voto');
  if (atalhoVoto) atalhoVoto.onclick = (e) => { e.preventDefault(); window.App.Telas.mostrar('tela-voto'); };

  const NIVEIS_INSTR = ['ANALFABETO', 'LE E ESCREVE', 'ENSINO FUNDAMENTAL INCOMPLETO', 'ENSINO FUNDAMENTAL COMPLETO', 'ENSINO MEDIO INCOMPLETO', 'ENSINO MEDIO COMPLETO', 'SUPERIOR INCOMPLETO', 'SUPERIOR COMPLETO'];
  const nivelInstr = (s) => { const n = norm(s).toUpperCase(); const i = NIVEIS_INSTR.findIndex((x) => n.startsWith(norm(x).toUpperCase())); return i < 0 ? 0 : i; };
  const termos = (txt) => (txt || '').split(/[,;]/).map(norm).filter(Boolean);

  // =====================================================================
  //  CRITÉRIOS — para adicionar um novo, basta acrescentar um objeto aqui.
  //  avaliar(c, cfg, ctx) -> número de 0 a 1 (quanto o candidato atende)
  //  tipo: 'bool' | 'texto' | 'lista' | 'faixa' | 'select' | 'excluir'
  //  excluir: true -> em vez de pontuar, remove o candidato se avaliar() === 1
  // =====================================================================
  // Critérios locais usam o município e a UF do Perfil. Sem município no Perfil eles "não se aplicam" (null):
  // saem da média, em vez de zerar todo mundo.
  const MUN = () => titulo(munFoco()) || 'meu município (defina no Perfil)';
  const munsCfg = (cfg) => [munFoco(), ...termos(cfg.termos)].map(normMun).filter(Boolean);
  // já teve mandato (deputado estadual/federal, senador): só para esses faz sentido cobrar emendas
  const jaParlamentar = (c) => !!(Dados.emendas(c.sq) || Dados.camara(c.sq) || ((window.ALERO || {}).porCand || {})[c.sq]
    || ((((window.VOTFED || {}).senado) || {}).porCand || {})[c.sq]);
  const CRITERIOS = [
    {
      id: 'munHist', label: () => `Já disputou eleição em ${MUN()} (vereador/prefeito)`, tipo: 'texto', peso: 5, ativo: true,
      cfg: { termos: '' }, placeholder: 'outros municípios (opcional), separados por vírgula',
      desc: 'Histórico oficial do TSE: candidaturas municipais anteriores no seu município (Perfil) e nos que você acrescentar. Forte indicador de vínculo local.',
      avaliar: (c, cfg) => { const ms = munsCfg(cfg); if (!ms.length) return null; return ms.some((t) => (c.munHist || []).some((m) => normMun(m).includes(t))) ? 1 : 0; },
    },
    {
      id: 'votosFoco', label: () => `Votação concentrada em ${MUN()} na eleição anterior`, tipo: 'faixa', peso: 4, ativo: true,
      cfg: { min: 5, max: 30 },
      desc: '% dos votos que o candidato teve no seu município na última eleição estadual/federal que disputou (2022). Abaixo do mínimo = 0; no máximo ou acima = pontuação cheia; entre os dois, proporcional. Quem nunca disputou eleição estadual/federal fica de fora deste critério (sem informação não é zero). A base guarda os 12 municípios com mais votos de cada candidato; fora deles, conta como menos que o 12º.',
      avaliar: (c, cfg) => {
        if (!munFoco()) return null;
        const v = pctVotosEm(c, munFoco()); if (!v || v.pct == null) return null;
        if (v.pct <= cfg.min) return 0; if (v.pct >= cfg.max) return 1; return (v.pct - cfg.min) / Math.max(1, cfg.max - cfg.min);
      },
    },
    {
      id: 'emendasFoco', label: () => `Mandou emendas para ${MUN()}`, tipo: 'faixa', peso: 4, ativo: true,
      cfg: { min: 0, max: 2000 }, unidade: 'mil R$',
      desc: 'Valor de emendas parlamentares (federais e estaduais) destinado ao seu município por quem já teve mandato. Até o mínimo = 0; no máximo ou acima = pontuação cheia; entre os dois, proporcional. Quem nunca foi parlamentar fica de fora deste critério. Por enquanto só há emendas por município para RO.',
      avaliar: (c, cfg) => {
        if (!temEmendasMun() || !jaParlamentar(c)) return null;
        const ef = emendasFoco(c.sq); const v = ef ? ef.destinado / 1000 : 0;
        if (v <= cfg.min) return 0; if (v >= cfg.max) return 1; return (v - cfg.min) / Math.max(1, cfg.max - cfg.min);
      },
    },
    {
      id: 'munNasc', label: () => `Nasceu em ${MUN()}`, tipo: 'texto', peso: 3, ativo: true,
      cfg: { termos: '' }, placeholder: 'outros municípios (opcional), separados por vírgula',
      desc: 'Município de nascimento informado ao TSE: o seu (Perfil) e os que você acrescentar.',
      avaliar: (c, cfg) => { const ms = munsCfg(cfg); if (!ms.length) return null; return ms.some((t) => normMun(c.munNasc).includes(t)) ? 1 : 0; },
    },
    {
      id: 'tagLocal', label: () => `Tem minha tag "${MUN()}" (vínculo que eu conheço)`, tipo: 'texto', peso: 5, ativo: true,
      cfg: { tag: '' }, placeholder: 'outra tag (opcional)',
      desc: 'Você marca a tag na ficha do candidato (mora lá, atua lá, você conhece). O TSE não publica domicílio eleitoral.',
      avaliar: (c, cfg) => { const tag = cfg.tag || titulo(munFoco()); if (!tag) return null; return Store.temTag(c.sq, tag) ? 1 : 0; },
    },
    {
      id: 'ufNasc', label: () => `Nasceu em ${perfil().uf || 'meu estado'}`, tipo: 'select', peso: 3, ativo: true,
      cfg: { uf: '' }, opcoes: () => [['', 'O estado do meu Perfil'], ...['RO', 'AC', 'AM', 'MT', 'PR', 'SP', 'MG', 'RS', 'SC', 'GO', 'BA', 'CE', 'PE', 'MA', 'PA', 'RJ', 'ES', 'DF', 'MS', 'TO', 'PI', 'RN', 'PB', 'AL', 'SE', 'AP', 'RR'].map((u) => [u, u])],
      avaliar: (c, cfg) => c.ufNasc === (cfg.uf || perfil().uf) ? 1 : 0,
    },
    {
      id: 'posicoes', label: 'Vota como eu nas votações que marquei', tipo: 'bool', peso: 3, ativo: true,
      desc: 'Marque como você votaria na tela Votações (ALE-RO, Câmara e Senado). Nota = proporção das votações marcadas em que o candidato votou igual a você; só conta onde ele votou Sim ou Não. Quem não tem voto registrado nessas votações fica de fora deste critério, sem ganhar nem perder pontos.',
      avaliar: (c) => { const r = concordancia(c); return r.total ? r.iguais / r.total : null; },
      porque: (c) => { const r = concordancia(c); return `Vota como você em ${r.iguais} de ${r.total}`; },
    },
    {
      id: 'deferido', label: 'Registro deferido', tipo: 'bool', peso: 2, ativo: true,
      desc: 'Deferido = 1 · pendente = 0,5 · indeferido = 0.',
      avaliar: (c) => ({ ok: 1, warn: 0.5, bad: 0 }[sitClasse(c.sit)]),
    },
    {
      id: 'ocultarIndef', label: 'Ocultar indeferidos, renúncias e cancelados', tipo: 'excluir', excluir: true, ativo: true,
      avaliar: (c) => sitClasse(c.sit) === 'bad' ? 1 : 0,
    },
    {
      id: 'semMotivo', label: 'Sem motivo de indeferimento/cassação registrado', tipo: 'bool', peso: 1, ativo: true,
      desc: 'Base motivo_cassacao do TSE (ex.: falta de desincompatibilização, cota de gênero).',
      avaliar: (c) => (c.motivos && c.motivos.length) ? 0 : 1,
    },
    {
      id: 'jaEleito', label: 'Já foi eleito alguma vez', tipo: 'select', peso: 1, ativo: false,
      cfg: { modo: 'sim' }, opcoes: () => [['sim', 'Prefiro quem já venceu eleição'], ['nao', 'Prefiro quem nunca foi eleito']],
      avaliar: (c, cfg) => (cfg.modo === 'sim') === ((c.vezesEleito || 0) > 0) ? 1 : 0,
    },
    {
      id: 'planoGoverno', label: 'Tem plano de governo publicado (Gov./Pres.)', tipo: 'bool', peso: 1, ativo: false,
      avaliar: (c) => (c.propostas && c.propostas.length) ? 1 : 0,
    },
    {
      id: 'partidosPref', label: 'Partido entre os meus preferidos', tipo: 'lista', peso: 3, ativo: false,
      cfg: { valores: [] }, opcoes: (ctx) => ctx.partidos,
      avaliar: (c, cfg) => cfg.valores.includes(c.partido) ? 1 : 0,
    },
    {
      id: 'partidosVeto', label: 'Excluir partidos', tipo: 'lista', excluir: true, ativo: false, classe: 'veto',
      cfg: { valores: [] }, opcoes: (ctx) => ctx.partidos,
      avaliar: (c, cfg) => cfg.valores.includes(c.partido) ? 1 : 0,
    },
    {
      id: 'favorito', label: 'Está nos meus favoritos', tipo: 'bool', peso: 2, ativo: true,
      avaliar: (c) => Store.favorito(c.sq) ? 1 : 0,
    },
    {
      id: 'reeleicao', label: 'Tenta reeleição', tipo: 'select', peso: 1, ativo: false,
      desc: 'Derivado do histórico: eleito na eleição anterior para o mesmo cargo.',
      cfg: { modo: 'sim' }, opcoes: () => [['sim', 'Prefiro quem já tem mandato (experiência)'], ['nao', 'Prefiro renovação (sem mandato)']],
      avaliar: (c, cfg) => (cfg.modo === 'sim') === !!c.reeleicao ? 1 : 0,
    },
    {
      id: 'idade', label: 'Faixa etária', tipo: 'faixa', peso: 1, ativo: false,
      cfg: { min: 30, max: 65 }, unidade: 'anos',
      avaliar: (c, cfg) => c.idade == null ? 0.5 : (c.idade >= cfg.min && c.idade <= cfg.max ? 1 : 0),
    },
    {
      id: 'instrucao', label: 'Escolaridade mínima', tipo: 'select', peso: 1, ativo: false,
      cfg: { min: 'SUPERIOR COMPLETO' }, opcoes: () => NIVEIS_INSTR.map((n) => [n, titulo(n)]),
      avaliar: (c, cfg) => nivelInstr(c.instrucao) >= nivelInstr(cfg.min) ? 1 : 0,
    },
    {
      id: 'genero', label: 'Gênero', tipo: 'select', peso: 1, ativo: false,
      cfg: { valor: 'FEMININO' }, opcoes: () => [['FEMININO', 'Feminino'], ['MASCULINO', 'Masculino']],
      avaliar: (c, cfg) => norm(c.genero) === norm(cfg.valor) ? 1 : 0,
    },
    {
      id: 'ocupacao', label: 'Ocupação contém', tipo: 'texto', peso: 2, ativo: false,
      cfg: { termos: 'médico, professor' }, desc: 'Palavras separadas por vírgula; basta uma bater.',
      avaliar: (c, cfg) => termos(cfg.termos).some((t) => norm(c.ocupacao).includes(t)) ? 1 : 0,
    },
    {
      id: 'fundoPublico', label: 'Campanha pouco dependente de dinheiro público', tipo: 'faixa', peso: 1, ativo: false,
      cfg: { min: 50, max: 95 }, unidade: '% público',
      desc: 'Prestação de contas 2026 (TSE): % da arrecadação que veio do fundo eleitoral e do fundo partidário. Até o mínimo = pontuação cheia; no máximo ou acima = 0; entre os dois, proporcional. Sem prestação de contas = 0,5.',
      avaliar: (c, cfg) => { const p = pctFundoPublico(c.contas); if (p == null) return 0.5; if (p <= cfg.min) return 1; if (p >= cfg.max) return 0; return (cfg.max - p) / Math.max(1, cfg.max - cfg.min); },
    },
    {
      id: 'doadoresPF', label: 'Tem muitos doadores pessoas físicas', tipo: 'faixa', peso: 1, ativo: false,
      cfg: { min: 5, max: 50 }, unidade: 'doadores',
      desc: 'Quantidade de pessoas físicas que doaram para a campanha (sinal de apoio espontâneo). Abaixo do mínimo = 0; no máximo ou acima = pontuação cheia.',
      avaliar: (c, cfg) => { const ct = c.contas; if (!ct) return 0; const n = ct.nPF != null ? ct.nPF : (ct.doadores || []).filter((d) => d[1] === 'Pessoa física').length; if (n <= cfg.min) return 0; if (n >= cfg.max) return 1; return (n - cfg.min) / Math.max(1, cfg.max - cfg.min); },
    },
    {
      id: 'tagEvitar', label: 'Excluir quem tem minha tag "evitar"', tipo: 'texto', excluir: true, ativo: true, classe: 'veto',
      cfg: { tag: 'evitar' },
      avaliar: (c, cfg) => Store.temTag(c.sq, cfg.tag) ? 1 : 0,
    },
  ];

  const rot = (cr) => (typeof cr.label === 'function' ? cr.label() : cr.label);
  // resumo para a aba Perfil
  window.App.criteriosResumo = () => CRITERIOS.map((cr) => Object.assign({ rotulo: rot(cr), excluir: !!cr.excluir }, estadoCriterio(cr)));

  // estado persistido dos critérios: { id: {ativo, peso, cfg} }
  function estadoCriterio(cr) {
    const s = Store.ler().criterios[cr.id];
    return { ativo: s?.ativo ?? cr.ativo, peso: s?.peso ?? cr.peso ?? 0, cfg: Object.assign({}, cr.cfg || {}, s?.cfg || {}) };
  }
  function salvarCriterio(cr, patch) {
    const d = Store.ler(); const atual = estadoCriterio(cr);
    d.criterios[cr.id] = { ativo: atual.ativo, peso: atual.peso, ...patch, cfg: Object.assign({}, atual.cfg, patch.cfg || {}) };
    Store.salvar();
  }

  // ---------- pontuação ----------
  function pontuar(lista) {
    const ativos = CRITERIOS.map((cr) => ({ cr, st: estadoCriterio(cr) })).filter((x) => x.st.ativo);
    const pontuaveis = ativos.filter((x) => !x.cr.excluir && x.st.peso > 0);
    const out = [];
    for (const c of lista) {
      let excluido = false;
      for (const x of ativos) if (x.cr.excluir && x.cr.avaliar(c, x.st.cfg, ctx) >= 1) { excluido = true; break; }
      if (excluido) continue;
      let total = 0, soma = 0; const porque = [];
      for (const x of pontuaveis) {
        const v = x.cr.avaliar(c, x.st.cfg, ctx);
        if (v === null) continue;   // não se aplica a este candidato: sai da média dele (sem informação não é zero)
        soma += x.st.peso;
        if (v > 0) total += v * x.st.peso;
        // critério com explicação própria ("Vota como você em 0 de 2") aparece mesmo quando dá zero: transparência
        if (v > 0 || x.cr.porque) porque.push({ label: x.cr.porque ? x.cr.porque(c, x.st.cfg) : rot(x.cr), v, peso: x.st.peso });
      }
      out.push({ c, score: soma ? Math.round((total / soma) * 100) : 0, porque });
    }
    out.sort((a, b) => b.score - a.score || (Store.favorito(b.c.sq) - Store.favorito(a.c.sq)) || (a.c.urna || '').localeCompare(b.c.urna || '', 'pt-BR'));
    return out;
  }

  // ---------- estado da página ----------
  const m = Dados.manifest();
  const ctx = { partidos: [], uf: perfil().uf };
  let universo = [];
  let cargoAtual = null;
  let cargos = [];

  const selUF = $('uf-foco');
  selUF.innerHTML = m.ufs.filter((u) => u !== 'BR').map((u) => `<option value="${u}">${u}</option>`).join('');
  selUF.value = m.ufs.includes(ctx.uf) ? ctx.uf : (m.ufs.find((u) => u !== 'BR') || '');
  // trocar a UF aqui troca a UF do Perfil (o município só fica se for da mesma UF)
  selUF.onchange = () => setPerfil({ uf: selUF.value, mun: selUF.value === perfil().uf ? munFoco() : '' });
  document.addEventListener('perfil:mudou', () => { ctx.uf = perfil().uf; if (m.ufs.includes(ctx.uf)) selUF.value = ctx.uf; carregar(); });

  async function carregar() {
    universo = await Dados.carregarVarias([ctx.uf, 'BR'].filter((u) => m.ufs.includes(u)));
    ctx.partidos = [...new Set(universo.map((c) => c.partido).filter(Boolean))].sort();
    // o critério de votação só faz sentido se a base de votos por município foi cruzada
    const crVotos = CRITERIOS.find((x) => x.id === 'votosFoco');
    const temVotos = universo.some((c) => c.votosAnt && c.votosAnt.length);
    crVotos.ativo = temVotos;
    const crEm = CRITERIOS.find((x) => x.id === 'emendasFoco');
    if (!window.EMENDAS) { crEm.ativo = false; if (!crEm.desc.startsWith('SEM DADOS')) crEm.desc = 'SEM DADOS: rode python scripts/fetch_emendas.py. ' + crEm.desc; }
    const aviso = $('perfil-aviso');
    if (aviso) aviso.hidden = !!munFoco();
    if (!temVotos && !crVotos.desc.startsWith('SEM DADOS')) crVotos.desc = 'SEM DADOS: coloque votacao_candidato_munzona_2022_RO.zip (TSE) em raw/ e rode o script. ' + crVotos.desc;
    cargos = [...new Set(universo.map((c) => c.cargo))].sort((a, b) => CARGOS_ORDEM.indexOf(a) - CARGOS_ORDEM.indexOf(b));
    if (!cargos.includes(cargoAtual)) cargoAtual = cargos.includes('Deputado Federal') ? 'Deputado Federal' : cargos[0];
    renderAbas(); renderCriterios(); renderRank(); renderCola(); renderDenuncias(); renderFontes();
  }

  function renderAbas() {
    const box = $('abas'); box.innerHTML = '';
    cargos.forEach((cg) => {
      const n = universo.filter((c) => c.cargo === cg).length;
      const escolhidos = Store.escolhas(cg).length;
      const vg = ((m.vagas || {})[cg === 'Presidente' ? 'BR' : ctx.uf] || {})[cg];
      const b = el(`<button type="button" role="tab" aria-selected="${cg === cargoAtual}">${esc(cg)}<span class="cont">${n}${vg ? ' · ' + vg + (vg > 1 ? ' vagas' : ' vaga') : ''}</span>${escolhidos ? `<span class="marca-ok" title="Escolha feita">${icone('check')}</span>` : ''}</button>`);
      b.onclick = () => { cargoAtual = cg; renderAbas(); renderRank(); };
      box.appendChild(b);
    });
  }

  // ---------- painel de critérios ----------
  function renderCriterios() {
    const box = $('criterios'); box.innerHTML = '';
    CRITERIOS.forEach((cr) => {
      const st = estadoCriterio(cr);
      const div = el(`<div class="criterio ${st.ativo ? '' : 'desligado'}">
        <div class="cab"><input type="checkbox" id="cr-${cr.id}" ${st.ativo ? 'checked' : ''}><label for="cr-${cr.id}">${esc(rot(cr))}${cr.excluir ? '<span class="excl">exclusão</span>' : ''}</label></div>
        ${cr.desc ? `<div class="desc">${esc(cr.desc)}</div>` : ''}
        ${cr.excluir ? '' : `<div class="peso"><label for="peso-${cr.id}">Peso</label><input type="range" id="peso-${cr.id}" min="0" max="5" step="1" value="${st.peso}"><span class="val" aria-live="polite">${st.peso}</span></div>`}
        <div class="cfg"></div></div>`);
      div.querySelector('input[type=checkbox]').onchange = (e) => { salvarCriterio(cr, { ativo: e.target.checked }); div.classList.toggle('desligado', !e.target.checked); renderRank(); };
      const range = div.querySelector('input[type=range]');
      if (range) range.oninput = (e) => { div.querySelector('.val').textContent = e.target.value; salvarCriterio(cr, { peso: +e.target.value }); renderRank(); };
      const cfg = div.querySelector('.cfg');
      const upd = (patch) => { salvarCriterio(cr, { cfg: patch }); renderRank(); };
      switch (cr.tipo) {
        case 'texto': {
          const chave = 'termos' in (cr.cfg || {}) ? 'termos' : 'tag';
          const i = el(`<input type="text" value="${esc(st.cfg[chave])}" placeholder="${esc(cr.placeholder || '')}" aria-label="Valor para: ${esc(rot(cr))}">`);
          i.onchange = () => upd({ [chave]: i.value }); cfg.appendChild(i); break;
        }
        case 'select': {
          const chave = Object.keys(cr.cfg)[0];
          const s = el(`<select aria-label="Opção para: ${esc(rot(cr))}"></select>`);
          cr.opcoes(ctx).forEach((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; s.appendChild(el(`<option value="${esc(v)}" ${v === st.cfg[chave] ? 'selected' : ''}>${esc(l)}</option>`)); });
          s.onchange = () => upd({ [chave]: s.value }); cfg.appendChild(s); break;
        }
        case 'faixa': {
          const a = el(`<input type="number" value="${st.cfg.min}" aria-label="Mínimo" inputmode="numeric">`), b = el(`<input type="number" value="${st.cfg.max}" aria-label="Máximo" inputmode="numeric">`);
          a.onchange = () => upd({ min: +a.value }); b.onchange = () => upd({ max: +b.value });
          cfg.append(a, el('<span>a</span>'), b, el(`<span>${esc(cr.unidade || '%')}</span>`)); break;
        }
        case 'lista': {
          const chips = el('<div class="chips" role="group"></div>');
          cr.opcoes(ctx).forEach((v) => {
            const ch = el(`<button type="button" class="chip ${cr.classe || ''}" aria-pressed="${st.cfg.valores.includes(v)}">${esc(v)}</button>`);
            ch.onclick = () => { const cur = estadoCriterio(cr).cfg.valores; const i = cur.indexOf(v); if (i >= 0) cur.splice(i, 1); else cur.push(v); ch.setAttribute('aria-pressed', i < 0); upd({ valores: cur }); };
            chips.appendChild(ch);
          });
          cfg.appendChild(chips); break;
        }
      }
      box.appendChild(div);
    });
  }
  $('btn-criterios-padrao').onclick = () => { if (confirm('Voltar todos os critérios ao padrão?')) { Store.ler().criterios = {}; Store.salvar(); renderCriterios(); renderRank(); } };

  // ---------- ranking ----------
  function renderRank() {
    const box = $('rank'); box.innerHTML = '';
    if (!cargoAtual) return;
    const q = norm($('rank-q').value); const soFav = $('rank-so-fav').checked; const limite = +$('rank-limite').value;
    let lista = universo.filter((c) => c.cargo === cargoAtual);
    const totalCargo = lista.length;
    if (q) lista = lista.filter((c) => /^\d+$/.test(q) ? (c.nr || '').startsWith(q) : norm(c.urna).includes(q) || norm(c.nome).includes(q));
    if (soFav) lista = lista.filter((c) => Store.favorito(c.sq));
    const rank = pontuar(lista);
    const vagas = VAGAS[cargoAtual] || 1;
    $('rank-titulo').textContent = `${cargoAtual}: ${rank.length} candidato(s) após exclusões (de ${totalCargo}) · ${vagas} ${vagas > 1 ? 'votos' : 'voto'} · escolhido(s): ${Store.escolhas(cargoAtual).length}/${vagas}`;
    if (!rank.length) { box.innerHTML = '<div class="vazio">Nenhum candidato passa pelos critérios de exclusão / filtro.</div>'; return; }
    const frag = document.createDocumentFragment();
    (limite ? rank.slice(0, limite) : rank).forEach((r, i) => {
      const c = r.c; const escolhido = Store.escolhido(cargoAtual, c.sq);
      const mun = titulo(munFoco());
      const pv = mun ? pctVotosEm(c, mun) : null;
      const votosTxt = !pv ? '' : pv.municipal ? ` · ${pv.ano} (${pv.cargo}): ${fmtNum(pv.total)} votos${pv.votos ? ' em ' + mun : ''}` : ` · ${pv.ano} (${pv.cargo}): ${fmtNum(pv.total)} votos, ${pv.pct}% em ${mun}`;
      const item = el(`<div class="rank-item ${escolhido ? 'escolhido' : ''}">
        <div class="pos" aria-label="Posição ${i + 1}">${i + 1}</div>
        ${fotoHtml(c, 'mini')}
        <div class="info" role="button" tabindex="0" aria-label="Abrir ficha de ${esc(titulo(c.urna))}">
          <div class="urna">${esc(titulo(c.urna))} <span class="tag plain num">${esc(c.nr)}</span>${escolhido ? `<span class="tag ok">Escolhido</span>` : ''}</div>
          <div class="sub">${esc(titulo(c.nome))} · ${esc(c.partido)} · ${esc(titulo(c.ocupacao || '—'))}${c.idade ? ' · ' + c.idade + ' anos' : ''}${c.munNasc ? ' · nascido em ' + esc(titulo(c.munNasc)) + '/' + esc(c.ufNasc || '') : ''}${c.vezesCand ? ' · ' + c.vezesCand + ' candidatura(s), eleito ' + c.vezesEleito + 'x' : ' · 1ª candidatura'}${c.munHist && c.munHist.length ? ' · disputou em ' + esc(c.munHist.map(titulo).join(', ')) : ''}${esc(votosTxt)}</div>
          <div class="barra" aria-hidden="true"><i style="width:${r.score}%"></i></div>
          <div class="porque">${r.porque.map((p) => `<span class="tag ${p.v > 0 ? 'ok' : 'plain'}">${esc(p.label.split(' (')[0])}${p.v > 0 && p.v < 1 ? ' (parcial)' : ''}</span>`).join('') || '<span class="tag plain">nenhum critério atendido</span>'}${Store.tags(c.sq).map((t) => `<span class="tag user">${icone('etiqueta')}${esc(t)}</span>`).join('')}</div>
        </div>
        <div class="acoes">
          <div class="score" aria-label="Score ${r.score} de 100">${r.score}<small>/100</small></div>
          <button type="button" class="btn mini icone fav" aria-pressed="${Store.favorito(c.sq)}" aria-label="${Store.favorito(c.sq) ? 'Remover dos favoritos' : 'Favoritar'}">${icone('estrela', Store.favorito(c.sq))}</button>
          <button type="button" class="btn mini ${escolhido ? 'ok' : ''} esc" aria-pressed="${escolhido}">${escolhido ? 'Escolhido' : 'Escolher'}</button>
        </div></div>`);
      const abrir = () => Modal.abrir(c, { cargoEscolha: cargoAtual });
      item.querySelector('.info').onclick = abrir;
      item.querySelector('.info').onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); } };
      item.querySelector('.fav').onclick = () => { Store.alternarFavorito(c.sq); renderRank(); };
      item.querySelector('.esc').onclick = () => { Store.alternarEscolha(cargoAtual, c.sq); renderAbas(); renderRank(); renderCola(); };
      frag.appendChild(item);
    });
    box.appendChild(frag);
  }
  $('rank-q').oninput = renderRank; $('rank-so-fav').onchange = renderRank; $('rank-limite').onchange = renderRank;

  // ---------- cola (colinha desenhada, na tela) ----------
  function renderCola() {
    const box = $('colinha-inline'); if (!box) return;
    box.innerHTML = htmlColinha();
    box.querySelectorAll('.item').forEach((it) => {
      const sq = it.dataset.sq; const cargo = it.dataset.cargo;
      if (!sq) { it.onclick = () => window.App.Telas.mostrar('tela-voto'); it.setAttribute('role', 'button'); it.tabIndex = 0; it.title = 'Escolher na aba Meu voto'; return; }
      const c = universo.find((x) => x.sq === sq); if (!c) return;
      it.setAttribute('role', 'button'); it.tabIndex = 0; it.title = 'Abrir ficha de ' + titulo(c.urna);
      const abrir = () => Modal.abrir(c, { cargoEscolha: cargo });
      it.onclick = abrir; it.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); } };
    });
  }

  // ---------- colinha (impressão / PDF / compartilhar) ----------
  const ORDEM_URNA = ['Deputado Federal', 'Deputado Estadual', 'Deputado Distrital', 'Senador', 'Governador', 'Presidente'];
  // "Vice: Fulano · 1º supl. Beltrano · 2º supl. Sicrano" (ignora quem renunciou / foi indeferido)
  function chapaTexto(c) {
    const ordem = (x) => /vice/i.test(x.cargo) ? 0 : /1/.test(x.cargo) ? 1 : 2;
    return (c.chapa || []).filter((x) => sitClasse(x.sit) !== 'bad').sort((a, b) => ordem(a) - ordem(b))
      .map((x) => (/vice/i.test(x.cargo) ? 'Vice: ' : x.cargo.replace(/(\d)º Suplente.*/i, '$1º supl. ')) + titulo(x.nome)).join(' · ');
  }
  function escolhasOrdenadas() {
    const out = [];
    ORDEM_URNA.filter((cg) => cargos.includes(cg)).forEach((cg) => {
      const vagas = VAGAS[cg] || 1; const sqs = Store.escolhas(cg);
      for (let i = 0; i < vagas; i++) out.push({ cargo: cg, rotulo: cg + (vagas > 1 ? ` — ${i + 1}º voto` : ''), c: universo.find((x) => x.sq === sqs[i]) || null });
    });
    return out;
  }
  const nomeUFAtual = () => (universo.find((c) => c.uf === ctx.uf) || {}).ue || ctx.uf;
  const TAM_NUMERO = { 'Deputado Federal': 4, 'Deputado Estadual': 5, 'Deputado Distrital': 5, Senador: 3, Governador: 2, Presidente: 2 };
  function htmlColinha() {
    const m = Dados.manifest();
    const nomeUF = nomeUFAtual();
    const digitos = (nr) => `<div class="digitos" aria-label="Número ${esc(nr.trim())}">${[...nr].map((d) => `<span>${d}</span>`).join('')}</div>`;
    const itens = escolhasOrdenadas().map((it, i) => {
      const c = it.c;
      if (!c) {
        const tam = TAM_NUMERO[it.cargo] || 2;
        return `<div class="item nao-escolhido" data-cargo="${esc(it.cargo)}"><div class="ordem">${i + 1}</div><div class="rot">${esc(it.rotulo)}</div><div class="corpo">${digitos(' '.repeat(tam))}<div>Ainda não escolhido — defina na aba "${esc(it.cargo)}".</div></div></div>`;
      }
      const chapa = chapaTexto(c);
      return `<div class="item" data-sq="${esc(c.sq)}" data-cargo="${esc(it.cargo)}"><div class="ordem">${i + 1}</div><div class="rot">${esc(it.rotulo)}</div>
        <div class="corpo">${digitos(c.nr)}<div class="quem">${fotoUrl(c) ? `<img src="${fotoUrl(c)}" alt="">` : '<div class="sem-foto"></div>'}<div><div class="nm">${esc(titulo(c.urna))}</div><div class="pt">${esc(c.partido)}${c.nomePartido ? ' · ' + esc(titulo(c.nomePartido)) : ''}</div>${chapa ? `<div class="chapa">${esc(chapa)}</div>` : ''}</div></div></div></div>`;
    }).join('');
    const hoje = new Date().toLocaleDateString('pt-BR');
    return `<div class="colinha">
      <div class="cab"><div><div class="t1">Colinha para a urna</div><div class="t2">Meu Voto 2026 · números na ordem em que a urna pede</div></div>
        <div class="dir"><b>Eleições Gerais 2026</b>1º turno · 4 de outubro de 2026<br>${esc(titulo(nomeUF))}</div></div>
      ${itens}
      <div class="rodape"><div>Confira número, nome, partido e foto na tela da urna antes de confirmar cada voto. Levar anotação própria para a cabine é permitido.</div><div>Gerado em ${hoje} com dados oficiais do TSE${m.geradoEm ? ' (base de ' + esc(m.geradoEm.slice(0, 10)) + ')' : ''}.</div></div>
    </div>`;
  }
  function textoColinha() {
    const linhas = ['COLINHA — ELEIÇÕES 2026 (' + ctx.uf + ')'];
    escolhasOrdenadas().forEach((it, i) => linhas.push(`${i + 1}. ${it.rotulo}: ${it.c ? it.c.nr + ' — ' + titulo(it.c.urna) + ' (' + it.c.partido + ')' : 'não escolhido'}`));
    linhas.push('Gerado com Meu Voto 2026 a partir dos dados do TSE.');
    return linhas.join(String.fromCharCode(10));
  }
  function renderColinhaPrint() { const alvo = $('colinha-print'); if (alvo) alvo.innerHTML = htmlColinha(); }
  async function compartilharColinha() {
    const texto = textoColinha();
    try {
      if (navigator.share) { await navigator.share({ title: 'Colinha — Eleições 2026', text: texto }); return; }
      await navigator.clipboard.writeText(texto); alert('Colinha copiada como texto. Cole onde quiser (WhatsApp, notas...).');
    } catch (e) { if (!e || e.name !== 'AbortError') window.prompt('Copie o texto da colinha:', texto); }
  }

  // ---------- colinha em PNG (1080×1920, visual de urna eletrônica; Canvas 2D puro, funciona offline) ----------
  const carregarImg = (src) => new Promise((ok) => { if (!src) return ok(null); const im = new Image(); im.onload = () => ok(im); im.onerror = () => ok(null); im.src = src; });
  const iniciais = (nome) => titulo(nome || '').split(/\s+/).filter((p) => p.length > 2).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '?';
  function desenharColinha(cv, itens, fotos) {
    const W = 1080, H = 1920, M = 64, CW = W - 2 * M;
    cv.width = W; cv.height = H;
    const g = cv.getContext('2d');
    const css = getComputedStyle(document.documentElement);
    const SANS = css.getPropertyValue('--font').trim() || 'system-ui, sans-serif';
    const MONO = css.getPropertyValue('--mono').trim() || 'monospace';
    const fonte = (peso, px, fam = SANS) => { g.font = `${peso} ${px}px ${fam}`; };
    const esp = (px) => { if ('letterSpacing' in g) g.letterSpacing = px + 'px'; };
    const rrect = (x, y, w, h, r) => { g.beginPath(); g.roundRect ? g.roundRect(x, y, w, h, r) : g.rect(x, y, w, h); };
    const caber = (t, max) => { if (g.measureText(t).width <= max) return t; while (t.length > 1 && g.measureText(t + '…').width > max) t = t.slice(0, -1); return t.trimEnd() + '…'; };
    const texto = (t, x, y, max, cor) => { g.fillStyle = cor; g.fillText(max ? caber(t, max) : t, x, y); };
    // encolhe a fonte até `min` antes de recorrer às reticências
    const encolher = (t, max, peso, px, min) => { fonte(peso, px); while (px > min && g.measureText(t).width > max) fonte(peso, --px); };
    const sombra = (blur, dy, a) => { g.shadowColor = `rgba(40,30,10,${a})`; g.shadowBlur = blur; g.shadowOffsetY = dy; };
    const semSombra = () => { g.shadowColor = 'transparent'; g.shadowBlur = 0; g.shadowOffsetY = 0; };
    g.textBaseline = 'alphabetic';

    // fundo: carcaça creme da urna
    const fundo = g.createLinearGradient(0, 0, 0, H);
    fundo.addColorStop(0, '#F1ECE0'); fundo.addColorStop(1, '#E2DBCB');
    g.fillStyle = fundo; g.fillRect(0, 0, W, H);

    // cabeçalho: "tela" da urna
    const HY = M, HH = 316;
    sombra(30, 10, .25); rrect(M, HY, CW, HH, 32); g.fillStyle = '#1C2127'; g.fill(); semSombra();
    const tela = g.createLinearGradient(0, HY, 0, HY + HH);
    tela.addColorStop(0, 'rgba(255,255,255,.07)'); tela.addColorStop(1, 'rgba(255,255,255,0)');
    rrect(M + 14, HY + 14, CW - 28, HH - 28, 22); g.fillStyle = tela; g.fill();
    g.strokeStyle = 'rgba(255,255,255,.08)'; g.lineWidth = 2; g.stroke();
    fonte(800, 22); esp(3);
    const selo = 'MEU VOTO 2026', sw = g.measureText(selo).width + 36;
    rrect(M + 48, HY + 48, sw, 42, 21); g.fillStyle = '#1E9E4A'; g.fill();
    texto(selo, M + 66, HY + 77, 0, '#fff');
    fonte(800, 88); esp(4); texto('MINHA COLINHA', M + 46, HY + 186, CW - 92, '#fff');
    esp(0); fonte(600, 36); texto(`Eleições 2026 · ${titulo(nomeUFAtual())}`, M + 48, HY + 240, CW - 96, '#D5DCE4');
    fonte(400, 28); texto('1º turno · domingo, 4 de outubro · na ordem em que a urna pede', M + 48, HY + 282, CW - 96, '#9AA6B2');

    // rodapé: teclas BRANCO / CORRIGE / CONFIRMA + avisos
    const FY = H - M - 290;
    const teclas = [['BRANCO', 256, '#F8F6F0', '#1C2127'], ['CORRIGE', 256, '#E8792B', '#fff'], ['CONFIRMA', CW - 512 - 40, '#1E9E4A', '#fff']];
    let tx = M;
    teclas.forEach(([rot, w, bg, cor]) => {
      sombra(0, 8, .35); rrect(tx, FY, w, 108, 20); g.fillStyle = bg; g.fill(); semSombra();
      if (bg === '#F8F6F0') { g.strokeStyle = '#CFC6B3'; g.lineWidth = 2; g.stroke(); }
      fonte(800, rot === 'CONFIRMA' ? 40 : 32); esp(2); g.textAlign = 'center';
      texto(rot, tx + w / 2, FY + 68, 0, cor); g.textAlign = 'left'; esp(0);
      tx += w + 20;
    });
    g.textAlign = 'center';
    fonte(700, 28); texto('Confira número, nome e foto na urna antes de apertar CONFIRMA.', W / 2, FY + 170, CW, '#2A2F36');
    fonte(400, 26); texto('Celular não entra na cabine: imprima ou anote seus números.', W / 2, FY + 212, CW, '#4A515B');
    const m = Dados.manifest();
    fonte(400, 21); texto(`Gerado em ${new Date().toLocaleDateString('pt-BR')} com dados oficiais do TSE${m.geradoEm ? ' (base de ' + m.geradoEm.slice(0, 10) + ')' : ''} · Meu Voto 2026`, W / 2, FY + 262, CW, '#7A7466');
    g.textAlign = 'left';

    // votos: um cartão por voto, altura dividida para caber todos
    const IY = HY + HH + 32, GAP = 18, IH = Math.floor((FY - 36 - IY - GAP * (itens.length - 1)) / itens.length);
    const KW = 70, KH = Math.min(92, IH - 76), KG = 10;
    itens.forEach((it, i) => {
      const y = IY + i * (IH + GAP), c = it.c;
      sombra(18, 6, .12); rrect(M, y, CW, IH, 24); g.fillStyle = '#fff'; g.fill(); semSombra();
      // ordem + cargo
      g.beginPath(); g.arc(M + 46, y + 38, 20, 0, Math.PI * 2); g.fillStyle = c ? '#1C2127' : '#B9B09C'; g.fill();
      fonte(800, 22); g.textAlign = 'center'; texto(String(i + 1), M + 46, y + 46, 0, '#fff'); g.textAlign = 'left';
      fonte(800, 22); esp(2.5); texto(it.rotulo.toUpperCase(), M + 80, y + 46, CW - 110, '#6B6557'); esp(0);
      // teclas com os dígitos
      const nr = c ? String(c.nr).trim() : ' '.repeat(TAM_NUMERO[it.cargo] || 2);
      const ky = y + 62; let kx = M + 80;
      [...nr].forEach((d) => {
        if (c) {
          rrect(kx, ky + 5, KW, KH, 14); g.fillStyle = '#000'; g.fill();
          rrect(kx, ky, KW, KH, 14); g.fillStyle = '#23282F'; g.fill();
          fonte(800, Math.round(KH * .62), MONO); g.textAlign = 'center';
          texto(d, kx + KW / 2, ky + KH * .72, 0, '#fff'); g.textAlign = 'left';
        } else {
          rrect(kx, ky, KW, KH, 14); g.setLineDash([8, 7]); g.strokeStyle = '#C7BFAE'; g.lineWidth = 3; g.stroke(); g.setLineDash([]);
        }
        kx += KW + KG;
      });
      // quem: foto (ou iniciais) + nome, partido, chapa
      const FW = Math.round((IH - 40) * .75), FH = IH - 40, fx = M + CW - 22 - FW, fy = y + 20;
      const x0 = kx + 18, larg = fx - 22 - x0;
      if (!c) { fonte(600, 28); texto('Ainda não escolhido', x0, y + 118, larg, '#9A927F'); return; }
      g.save(); rrect(fx, fy, FW, FH, 14); g.clip();
      const foto = fotos && fotos.get(c.sq);
      if (foto) {
        const esc2 = Math.max(FW / foto.width, FH / foto.height), iw = foto.width * esc2, ih = foto.height * esc2;
        g.drawImage(foto, fx + (FW - iw) / 2, fy + (FH - ih) / 4, iw, ih);
      } else {
        g.fillStyle = '#E6E0D2'; g.fillRect(fx, fy, FW, FH);
        fonte(800, Math.round(FW * .36)); g.textAlign = 'center'; texto(iniciais(c.urna), fx + FW / 2, fy + FH / 2 + FW * .13, 0, '#8C846F'); g.textAlign = 'left';
      }
      g.restore();
      const chapa = chapaTexto(c);
      const ny = chapa ? y + 96 : y + 108;
      encolher(titulo(c.urna), larg, 800, 34, 26); texto(titulo(c.urna), x0, ny, larg, '#15191E');
      encolher(c.partido, larg, 600, 24, 20); texto(c.partido + (c.nomePartido ? ' · ' + titulo(c.nomePartido) : ''), x0, ny + 34, larg, '#4A515B');
      if (chapa) { fonte(400, 20); texto(chapa, x0, ny + 62, larg, '#7A7466'); }
    });
  }
  const paraBlob = (cv) => new Promise((ok, erro) => { try { cv.toBlob((b) => b ? ok(b) : erro(new Error('falha ao gerar a imagem')), 'image/png'); } catch (e) { erro(e); } });
  async function pngColinha() {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const itens = escolhasOrdenadas();
    const fotos = new Map();
    await Promise.all(itens.filter((it) => it.c && fotoUrl(it.c)).map(async (it) => { const im = await carregarImg(fotoUrl(it.c)); if (im) fotos.set(it.c.sq, im); }));
    const cv = document.createElement('canvas');
    desenharColinha(cv, itens, fotos);
    // em file:// as fotos locais "sujam" o canvas e o navegador bloqueia a exportação: refaz com as iniciais
    try { return await paraBlob(cv); } catch (e) { desenharColinha(cv, itens, null); return paraBlob(cv); }
  }
  async function salvarColinhaPNG() {
    const btn = $('btn-png'); const rot = btn.innerHTML;
    btn.disabled = true; btn.textContent = 'Gerando imagem…';
    try {
      const url = URL.createObjectURL(await pngColinha());
      const a = document.createElement('a');
      if ('download' in a) { a.href = url; a.download = `colinha-2026-${ctx.uf}.png`; document.body.appendChild(a); a.click(); a.remove(); }
      else window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { alert('Não foi possível gerar a imagem: ' + e.message); }
    finally { btn.disabled = false; btn.innerHTML = rot; }
  }

  // ---------- denúncias (Pardal) ----------
  function renderDenuncias() {
    const dados = Dados.denuncias();
    const sec = $('painel-denuncias');
    if (!dados || !dados[ctx.uf]) { sec.hidden = true; return; }
    sec.hidden = false;
    const anos = Object.keys(dados[ctx.uf]).sort((a, b) => b - a);
    const html = anos.map((ano, i) => {
      const d = dados[ctx.uf][ano];
      const linhas = (obj, n = 8) => Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => `<tr><td>${esc(titulo(k))}</td><td class="r num">${fmtNum(v)}</td></tr>`).join('');
      const MF = titulo(munFoco());
      const foco = MF ? Object.entries(d.porMunicipio).find(([k]) => normMun(k) === normMun(MF)) : null;
      const procs = MF ? (d.processos || []).filter((p) => normMun(p.municipio) === normMun(MF)) : [];
      return `<details class="secao" ${i === 0 ? 'open' : ''}><summary>${icone('seta')}<span>${ano} — ${fmtNum(d.total)} denúncias em ${ctx.uf}${foco ? ` · ${fmtNum(foco[1])} em ${MF}` : ''}</span></summary><div class="conteudo">
        <div class="detalhes">
          <div><b>Por cargo</b><table class="tabela">${linhas(d.porCargo)}</table></div>
          <div><b>Por tipo de irregularidade</b><table class="tabela">${linhas(d.porTipo)}</table></div>
          <div><b>Municípios com mais denúncias</b><table class="tabela">${linhas(d.porMunicipio)}</table></div>
        </div>
        ${procs.length ? `<b class="small">Processos no PJe originados em ${MF} (${procs.length})</b><table class="tabela"><thead><tr><th>Cargo</th><th>Tipo</th><th>Processo</th></tr></thead><tbody>${procs.map((p) => `<tr><td>${esc(titulo(p.cargo))}</td><td>${esc(p.tipo)}</td><td><a href="${linkPje(p.nr)}" target="_blank" rel="noopener">${esc(p.nr)}</a></td></tr>`).join('')}</tbody></table>` : MF ? `<p class="small muted">Nenhum processo no PJe originado em ${MF} neste ano.</p>` : ''}
      </div></details>`;
    }).join('');
    $('denuncias-conteudo').innerHTML = html;
  }

  // ---------- fontes externas ----------
  const FONTES = [
    ['Câmara dos Deputados — Dados Abertos', 'https://dadosabertos.camara.leg.br/', 'Votações, presença, proposições, gastos da cota parlamentar de cada deputado federal. Use scripts/fetch_camara.py para trazer um resumo para a ficha.'],
    ['Câmara — página do deputado', 'https://www.camara.leg.br/deputados/', 'Aba "Votações" mostra como votou em cada projeto; "Gastos" mostra a cota parlamentar.'],
    ['Senado Federal — Dados Abertos', 'https://www12.senado.leg.br/dados-abertos', 'Votações e matérias dos senadores (Acir Gurgacz, por exemplo).'],
    ['ALE-RO — Assembleia Legislativa de Rondônia', 'https://www.al.ro.leg.br/', 'Deputados estaduais: proposições, presença e transparência (Portal da Transparência da ALE).'],
    ['Portal da Transparência — emendas parlamentares', 'https://portaldatransparencia.gov.br/emendas', 'Emendas de deputados federais e senadores: valor, destino, área e quem recebeu. Resumo na ficha e na tela Emendas (scripts/fetch_emendas.py).'],
    ['Transparência RO — emendas estaduais', 'https://transparencia.ro.gov.br/emenda', 'Emendas dos deputados estaduais de Rondônia (desde 2023), com objeto e beneficiário.'],
    ['DivulgaCandContas (TSE)', 'https://divulgacandcontas.tse.jus.br/', 'Prestação de contas de campanha: quem doou, quanto gastou. Já linkado em cada ficha.'],
    ['Consulta unificada PJe (TSE)', 'https://consultaunificadapje.tse.jus.br/', 'Processos eleitorais (registro, AIJE, propaganda irregular) pelo nome do candidato ou número do processo.'],
    ['Portal da Transparência — sanções', 'https://portaldatransparencia.gov.br/sancoes', 'CEIS/CNEP/CEPIM: empresas e pessoas sancionadas pela administração pública.'],
    ['TCU — contas irregulares', 'https://contasirregulares.tcu.gov.br/', 'Lista de gestores com contas julgadas irregulares (inelegibilidade).'],
    ['TCE-RO', 'https://tcero.tc.br/', 'Julgamento de contas de prefeitos e gestores de Rondônia.'],
    ['Consulta processual — TJRO / TRF1', 'https://www.tjro.jus.br/', 'Ações cíveis e criminais em Rondônia (as certidões na ficha vêm daqui).'],
    ['Congresso em Foco / Ranking dos Políticos', 'https://congressoemfoco.uol.com.br/', 'Cobertura jornalística e avaliações do desempenho parlamentar (fontes privadas, leia com senso crítico).'],
    ['Diário Oficial de Rondônia', 'https://diof.ro.gov.br/', 'Nomeações, exonerações e atos administrativos ligados a cada nome.'],
  ];
  function renderFontes() {
    $('fontes-externas').innerHTML = FONTES.map(([n, u, d]) => `<div><b><a href="${u}" target="_blank" rel="noopener">${esc(n)} ${icone('externo')}</a></b>${esc(d)}</div>`).join('');
  }

  // ---------- exportar / importar / limpar / imprimir ----------
  $('btn-exportar').onclick = () => Store.exportar();
  $('arq-importar').onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { await Store.importar(f); alert('Importado com sucesso.'); location.reload(); } catch (err) { alert('Arquivo inválido: ' + err.message); }
  };
  $('btn-limpar').onclick = () => { if (confirm('Apagar favoritos, notas, tags, critérios e escolhas deste navegador?')) { Store.limpar(); location.reload(); } };
  $('btn-imprimir').onclick = () => { renderColinhaPrint(); window.print(); };
  $('btn-compartilhar').onclick = compartilharColinha;
  $('btn-png').onclick = salvarColinhaPNG;
  window.addEventListener('beforeprint', renderColinhaPrint);
  document.addEventListener('modal:fechou', () => { renderAbas(); renderRank(); renderCola(); });

  carregar();
})();
