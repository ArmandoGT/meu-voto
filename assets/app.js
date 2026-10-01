/* app.js — utilitários compartilhados: dados por UF, storage local, ícones, ficha do candidato (modal) */
(function () {
  'use strict';

  // ---------- helpers ----------
  const norm = (s) => (s || '').toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  // municípios: as bases escrevem o mesmo nome de jeitos diferentes ("Alvorada D'Oeste" no TSE/emendas,
  // "Alvorada do Oeste" na tabela de municípios, "MACHADINHO DO OESTE" no histórico): compara sem pontuação e com d'/do iguais
  const normMun = (s) => norm(s).replace(/[^a-z0-9]+/g, ' ').replace(/\bd oeste\b/g, 'do oeste').replace(/\s+/g, ' ').trim();
  const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const titulo = (s) => (s || '').toLowerCase().replace(/(^|\s|-|\(|')([a-zà-ú])/g, (m, p, l) => p + l.toUpperCase())
    .replace(/\b(Da|De|Do|Das|Dos|E)\b/g, (m) => m.toLowerCase()).replace(/\bQp\b/g, 'QP').replace(/\bTse\b/g, 'TSE').replace(/\bPje\b/g, 'PJe');
  const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
  const fmtMoeda = (v) => (v == null ? '' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));
  const fmtNum = (v) => (v == null ? '' : Number(v).toLocaleString('pt-BR'));
  // valores grandes em forma curta: R$ 12,3 mi / R$ 350 mil / R$ 800
  const fmtCurto = (v) => {
    if (v == null) return '';
    const a = Math.abs(v);
    if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' bi';
    if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (a >= 1e3) return 'R$ ' + Math.round(v / 1e3).toLocaleString('pt-BR') + ' mil';
    return 'R$ ' + Math.round(v).toLocaleString('pt-BR');
  };

  const CARGOS_ORDEM = ['Presidente', 'Governador', 'Senador', 'Deputado Federal', 'Deputado Estadual', 'Deputado Distrital'];
  const VAGAS = { Senador: 2 };   // quantos votos o eleitor dá por cargo

  // ---------- ícones (SVG inline, sem emoji) ----------
  const ICONES = {
    busca: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    voto: '<path d="M9 12l2 2 4-4"/><path d="M5 20h14a1 1 0 0 0 1-1v-7H4v7a1 1 0 0 0 1 1z"/><path d="M4 12l2.5-5h11L20 12"/>',
    estrela: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.9L12 17l-5.3 2.7 1.1-5.9L3.5 9.7l5.9-.8z"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    fechar: '<path d="M6 6l12 12M18 6L6 18"/>',
    seta: '<path d="m9 6 6 6-6 6"/>',
    doc: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
    balanca: '<path d="M12 4v16M4 20h16M6 8h12M6 8l-3 6h6zM18 8l-3 6h6z"/>',
    externo: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
    etiqueta: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.5"/>',
    nota: '<path d="M4 20h4l11-11-4-4L4 16z"/>',
    alerta: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
    pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    filtro: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
    imprimir: '<path d="M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M6 14h12v7H6z"/>',
    baixar: '<path d="M12 4v11M7 10l5 5 5-5M4 20h16"/>',
    subir: '<path d="M12 15V4M7 9l5-5 5 5M4 20h16"/>',
    lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.5M3 12h.5M3 18h.5"/>',
    predio: '<path d="M4 21V5l8-2v18M12 21h8V9h-8M7 8h2M7 12h2M7 16h2M15 12h2M15 16h2"/>',
    urna: '<path d="M4 10h16v10H4zM8 10V5h8v5M10 7h4"/>',
    dinheiro: '<rect x="3" y="6" width="18" height="12" rx="1.5"/><circle cx="12" cy="12" r="2.5"/><path d="M6.5 9v.01M17.5 15v.01"/>',
    plenario: '<path d="M3 6h9M3 12h9M3 18h9"/><path d="m15 11 2.5 2.5L22 9"/>',
    rede: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.3 10.9l7.4-3.7M8.3 13.1l7.4 3.7"/>',
  };
  const icone = (nome, cheio = false) => `<svg class="ico${cheio ? ' cheio' : ''}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONES[nome] || ''}</svg>`;

  const sitClasse = (sit) => {
    const s = norm(sit);
    if (s.startsWith('deferido')) return 'ok';
    if (s.includes('indeferido') || s.includes('cassad') || s.includes('cancelad') || s.includes('renunc') || s.includes('falec') || s.includes('negado')) return 'bad';
    return 'warn'; // pendente de julgamento, aguardando, sem informação
  };
  const sitCurta = (sit) => titulo(sit || 'sem situação').replace(' Em Prazo Recursal Ou Com Recurso', ' (com recurso)').replace('Pendente De Julgamento', 'Pendente de julgamento');

  // ---------- dados ----------
  const Dados = {
    cache: {},
    manifest: () => window.MANIFEST || { ufs: [], contagens: {}, cargos: [], partidos: [], vagas: {} },
    carregarUF(uf) {
      if (this.cache[uf]) return Promise.resolve(this.cache[uf]);
      if (window['CAND_' + uf]) { this.cache[uf] = window['CAND_' + uf]; return Promise.resolve(this.cache[uf]); }
      // versão mobile: dados embutidos como JSON em <script type="application/json" id="cand-XX">, parseados sob demanda
      const emb = document.getElementById('cand-' + uf);
      if (emb) { try { this.cache[uf] = JSON.parse(emb.textContent); } catch (e) { this.cache[uf] = []; } return Promise.resolve(this.cache[uf]); }
      if (this.manifest().mobile) { this.cache[uf] = []; return Promise.resolve([]); }
      return new Promise((resolve) => {
        const s = document.createElement('script');
        s.src = 'data/cand_' + uf + '.js';
        s.onload = () => { this.cache[uf] = window['CAND_' + uf] || []; resolve(this.cache[uf]); };
        s.onerror = () => { console.warn('Arquivo não encontrado: data/cand_' + uf + '.js'); this.cache[uf] = []; resolve([]); };
        document.head.appendChild(s);
      });
    },
    async carregarVarias(ufs) {
      const listas = await Promise.all(ufs.map((u) => this.carregarUF(u)));
      return listas.flat();
    },
    camara: (sq) => (window.CAMARA || {})[sq] || null,
    denuncias: () => window.DENUNCIAS || null,
    emendas: (sq) => ((window.EMENDAS || {}).porCand || {})[sq] || null,
    alero: () => window.ALERO || null,
    // votações nominais na Câmara ou no Senado de um candidato de RO que é/foi deputado federal ou senador
    votosFed(casa, sq) {
      const C = (window.VOTFED || {})[casa];
      const pid = C && C.porCand[sq];
      if (!pid) return null;
      return { pid, parl: C.parl[pid], vot: C.vot.filter((x) => x.v[pid]), C };
    },
    // votações nominais da ALE-RO em que o candidato (quando foi deputado estadual) tem voto registrado
    aleroCand(sq) {
      const A = window.ALERO;
      const pid = A && A.porCand[sq];
      if (!pid) return null;
      return { pid, parl: A.parl[pid], vot: A.vot.filter((x) => x.v[pid]) };
    },
  };

  // ---------- partido, federação e coligação ----------
  // No TSE, NM_COLIGACAO vale "FEDERAÇÃO" ou "PARTIDO ISOLADO" quando não há coligação de verdade: o tipo vem de TP_AGREMIACAO.
  // Deputado (proporcional): o voto conta para o partido ou a federação. Cargo majoritário: coligação, sem transferência de voto.
  const PROPORCIONAIS = ['Deputado Federal', 'Deputado Estadual', 'Deputado Distrital'];
  const ehProporcional = (c) => PROPORCIONAIS.includes(c.cargo);
  // "FEDERAÇÃO PSOL REDE (50-PSOL / 18-REDE)" ou "13-PT/65-PC do B/43-PV" -> ['PSOL','REDE'] / ['PT','PC do B','PV']
  const siglasDe = (txt) => (txt || '').replace(/FEDERA[ÇC][ÃA]O[^(/]*\(([^)]*)\)/gi, '$1').split('/')
    .map((s) => s.trim().replace(/^\d+\s*-\s*/, '')).filter(Boolean);
  const chaveSigla = (s) => norm(s).replace(/[^a-z0-9]/g, '');
  // nome em título, mantendo em maiúsculas as siglas que não são palavras ("FE Brasil", "PSOL Rede", mas "União Progressista")
  const nomeComSiglas = (s, siglas = []) => {
    const ks = new Set([...siglas, 'FE'].map((x) => x.toUpperCase().replace(/\s+/g, '')).filter((k) => k.length <= 4 && !['REDE', 'PODE', 'NOVO', 'AGIR'].includes(k)));
    return titulo(s).replace(/[A-Za-zÀ-ú]+/g, (w) => ks.has(w.toUpperCase()) ? w.toUpperCase() : w);
  };
  function agremiacao(c) {
    const tipo = norm(c.tipoAgremiacao).startsWith('federa') ? 'federacao' : norm(c.tipoAgremiacao).startsWith('colig') ? 'coligacao' : 'partido';
    if (tipo === 'federacao') {
      const partidos = siglasDe(c.compFederacao);
      return { tipo, chave: 'F' + (c.nrFederacao || c.federacao), partidos, rotuloTipo: 'Federação',
        nome: nomeComSiglas(c.nomeFederacao || c.federacao, partidos), comp: partidos.join(' · ') };
    }
    if (tipo === 'coligacao') {
      const partidos = siglasDe(c.compColigacao);
      return { tipo, chave: 'C' + (c.sqColigacao || c.coligacao), partidos, rotuloTipo: 'Coligação',
        nome: nomeComSiglas(c.coligacao, partidos), comp: partidos.join(' · '), compTSE: c.compColigacao };
    }
    return { tipo, chave: 'P' + c.partido, partidos: [c.partido], rotuloTipo: 'Partido isolado',
      nome: c.partido + (c.nomePartido ? ' — ' + titulo(c.nomePartido) : ''), comp: c.partido };
  }

  // ---------- votações (ALE-RO) ----------
  // Rótulos neutros: nenhum voto é "bom" ou "ruim"; as cores só distinguem um do outro.
  const VOTO_ROT = { S: 'Sim', N: 'Não', A: 'Abstenção', U: 'Ausente', X: 'Não votou', '?': 'Sem registro' };
  const votoTag = (cod) => `<span class="voto voto-${cod === '?' ? 'Q' : cod}">${VOTO_ROT[cod] || cod}</span>`;
  const fmtData = (iso) => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '';
  const nomeMateria = (x) => [x.t, x.n ? 'nº ' + x.n + (x.a ? '/' + x.a : '') : ''].filter(Boolean).join(' ');
  const linkMateria = (x) => x.m ? `https://sapl.al.ro.leg.br/materia/${x.m}` : null;
  // Vetos: nos placares da ALE-RO, Sim = manter o veto do governador e Não = derrubá-lo (confere em 710 de 712 vetos).
  const ehVeto = (x) => /^Veto/.test(x.t || '');
  const LEGENDA_VETO = 'Em vetos: Sim = manter o veto do governador · Não = derrubar o veto';
  // votos com o rótulo oficial da Casa (Câmara/Senado): a cor só distingue Sim, Não e Abstenção do resto
  const votoTagTexto = (rot) => { const n = norm(rot); const c = n === 'sim' ? 'S' : n === 'nao' ? 'N' : n.startsWith('abstenc') ? 'A' : 'Q'; return `<span class="voto voto-${c}">${esc(rot)}</span>`; };
  const CASAS = {
    camara: { nome: 'Câmara dos Deputados', daCasa: 'da Câmara dos Deputados', link: (x) => x.m ? `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${x.m}` : null },
    senado: { nome: 'Senado Federal', daCasa: 'do Senado Federal', link: (x) => x.m ? `https://www25.senado.leg.br/web/atividade/materias/-/materia/${x.m}` : null },
  };
  const avisoPlacar = (x) => x.confere === false ? '<span class="tag warn">Placar registrado não confere com o resultado — confira na fonte</span>' : '';

  // Emendas destinadas ao município do Perfil (federal + estadual RO), somadas a partir da lista por município
  // (a mesma da tela Emendas). destinado = empenhado federal (ou recebido pelos favorecidos, se maior) + previsto/
  // empenhado estadual; pago = pago federal (ou recebido, se maior) + pago estadual.
  // null = sem dados de emendas para o município do Perfil (hoje a lista por município só existe para RO).
  let emCache = { chave: null, porSq: null };
  const emendasPorMun = () => {
    const E = window.EMENDAS; const p = perfil();
    if (!E || !E.porMun || !p.mun) return null;
    const chave = Object.keys(E.porMun).find((k) => k.split('|')[0] === p.uf && normMun(k.split('|')[1]) === normMun(p.mun));
    if (!chave) return null;
    if (emCache.chave !== chave) {
      const porSq = {};
      for (const x of E.porMun[chave]) {
        if (!x.sq) continue;
        const a = porSq[x.sq] || (porSq[x.sq] = { empFed: 0, pagoFed: 0, rec: 0, destEst: 0, pagoEst: 0, n: 0 });
        a.n++;
        if (x.nv === 'fed') { a.empFed += x.e || 0; a.pagoFed += x.p || 0; }
        else if (x.nv === 'fav') a.rec += x.r || 0;
        else { a.destEst += Math.max(x.pv || 0, x.e || 0); a.pagoEst += x.p || 0; }
      }
      emCache = { chave, porSq };
    }
    return emCache.porSq;
  };
  const temEmendasMun = () => !!emendasPorMun();
  const emendasFoco = (sq) => {
    const porSq = emendasPorMun(); const a = porSq && porSq[sq];
    if (!a) return null;
    const destinado = Math.max(a.empFed, a.rec) + a.destEst, pago = Math.max(a.pagoFed, a.rec) + a.pagoEst;
    return destinado > 0 || pago > 0 ? { destinado, pago, n: a.n, fed: { rec: a.rec } } : null;
  };

  // ---------- storage ----------
  const CHAVE = 'meuvoto2026';
  const padrao = () => ({ favoritos: {}, notas: {}, tags: {}, criterios: {}, escolhas: {}, posicoes: {}, ufFoco: 'RO', ufBusca: 'RO+BR', versao: 1 });
  const Store = {
    dados: null,
    ler() {
      if (this.dados) return this.dados;
      let bruto = null;
      try { bruto = localStorage.getItem(CHAVE); this.dados = Object.assign(padrao(), JSON.parse(bruto || '{}')); }
      catch (e) { this.dados = padrao(); }
      // quem já usava o sistema antes do Perfil tinha tudo calculado para Ariquemes/RO: mantém
      if (!this.dados.perfil) this.dados.perfil = bruto ? { uf: 'RO', mun: 'Ariquemes' } : { uf: this.dados.ufFoco || 'RO', mun: '' };
      return this.dados;
    },
    salvar() { try { localStorage.setItem(CHAVE, JSON.stringify(this.ler())); } catch (e) { console.warn(e); } document.dispatchEvent(new CustomEvent('store:mudou')); },
    favorito(sq) { return !!this.ler().favoritos[sq]; },
    alternarFavorito(sq) { const d = this.ler(); if (d.favoritos[sq]) delete d.favoritos[sq]; else d.favoritos[sq] = true; this.salvar(); return !!d.favoritos[sq]; },
    nota(sq) { return this.ler().notas[sq] || ''; },
    setNota(sq, txt) { const d = this.ler(); if (txt && txt.trim()) d.notas[sq] = txt.trim(); else delete d.notas[sq]; this.salvar(); },
    tags(sq) { return this.ler().tags[sq] || []; },
    addTag(sq, tag) { tag = (tag || '').trim(); if (!tag) return; const d = this.ler(); const l = d.tags[sq] || []; if (!l.map(norm).includes(norm(tag))) l.push(tag); d.tags[sq] = l; this.salvar(); },
    delTag(sq, tag) { const d = this.ler(); d.tags[sq] = (d.tags[sq] || []).filter((t) => t !== tag); if (!d.tags[sq].length) delete d.tags[sq]; this.salvar(); },
    temTag(sq, tag) { return this.tags(sq).map(norm).includes(norm(tag)); },
    todasTags() { const s = new Set(); Object.values(this.ler().tags).forEach((l) => l.forEach((t) => s.add(t))); return [...s].sort(); },
    escolhas(cargo) { return this.ler().escolhas[cargo] || []; },
    escolhido(cargo, sq) { return this.escolhas(cargo).includes(sq); },
    alternarEscolha(cargo, sq) {
      const d = this.ler(); const l = d.escolhas[cargo] || []; const max = VAGAS[cargo] || 1;
      const i = l.indexOf(sq);
      if (i >= 0) l.splice(i, 1); else { l.push(sq); while (l.length > max) l.shift(); }
      d.escolhas[cargo] = l; this.salvar();
    },
    exportar() {
      const blob = new Blob([JSON.stringify(this.ler(), null, 2)], { type: 'application/json' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = 'meu-voto-2026-' + new Date().toISOString().slice(0, 10) + '.json'; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    },
    importar(arquivo) {
      return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => { try { const j = JSON.parse(r.result); this.dados = Object.assign(padrao(), j); this.salvar(); resolve(); } catch (e) { reject(e); } };
        r.onerror = reject; r.readAsText(arquivo);
      });
    },
    limpar() { this.dados = padrao(); this.dados.perfil = { uf: 'RO', mun: '' }; this.salvar(); },
    // posição do eleitor numa votação nominal: chave "alero:ID" | "camara:ID" | "senado:ID", valor 'S' ou 'N'
    posicoes() { return this.ler().posicoes || {}; },
    posicao(k) { return this.posicoes()[k] || null; },
    setPosicao(k, v) { const d = this.ler(); d.posicoes = d.posicoes || {}; if (v) d.posicoes[k] = v; else delete d.posicoes[k]; this.salvar(); },
  };

  // ---------- links externos ----------
  // DivulgaCandContas 2026: /divulga/#/candidato/{REGIAO}/{UF}/{idEleicao}/{sq}/2026/{UF}  (idEleicao das gerais 2026 = 20322002026)
  const ID_ELEICAO_DIVULGA = '20322002026';
  const REGIAO = { AC: 'NORTE', AP: 'NORTE', AM: 'NORTE', PA: 'NORTE', RO: 'NORTE', RR: 'NORTE', TO: 'NORTE',
    AL: 'NORDESTE', BA: 'NORDESTE', CE: 'NORDESTE', MA: 'NORDESTE', PB: 'NORDESTE', PE: 'NORDESTE', PI: 'NORDESTE', RN: 'NORDESTE', SE: 'NORDESTE',
    DF: 'CENTRO-OESTE', GO: 'CENTRO-OESTE', MT: 'CENTRO-OESTE', MS: 'CENTRO-OESTE', ES: 'SUDESTE', MG: 'SUDESTE', RJ: 'SUDESTE', SP: 'SUDESTE',
    PR: 'SUL', RS: 'SUL', SC: 'SUL', BR: 'BR' };
  const linkDivulga = (c) => c.sgUe && c.sq
    ? `https://divulgacandcontas.tse.jus.br/divulga/#/candidato/${REGIAO[c.sgUe] || c.sgUe}/${c.sgUe}/${ID_ELEICAO_DIVULGA}/${c.sq}/2026/${c.sgUe}` : null;
  const linkBusca = (c) => 'https://www.google.com/search?q=' + encodeURIComponent(`${titulo(c.urna)} ${c.partido} ${c.cargo} ${c.uf === 'BR' ? '' : c.uf} 2026`);
  const linkPje = (nr) => nr ? `https://consultaunificadapje.tse.jus.br/#/public/resultado/${encodeURIComponent(nr)}` : null;

  // ---------- vínculo local ----------
  // Perfil do eleitor: UF e município onde vota (aba Perfil). Tudo o que era "Ariquemes" fixo vem daqui.
  const perfil = () => { const d = Store.ler(); const p = d.perfil || {}; return { uf: p.uf || d.ufFoco || 'RO', mun: p.mun || '' }; };
  const munFoco = () => perfil().mun;
  const setPerfil = (patch) => {
    const d = Store.ler(); d.perfil = Object.assign(perfil(), patch);
    if (d.perfil.uf) d.ufFoco = d.perfil.uf;
    emCache = { chave: null, porSq: null };
    Store.salvar(); document.dispatchEvent(new CustomEvent('perfil:mudou'));
  };
  const disputouEm = (c, mun) => (c.munHist || []).some((m) => normMun(m) === normMun(mun));
  const fotoUrl = (c) => c.foto ? (c.foto.startsWith('data:') ? c.foto : encodeURI(c.foto)) : null;
  // Votos do candidato no município, na eleição anterior mais recente com dados de votação.
  // Prefere eleição estadual/federal (abrang E/F): nela o % por município mostra onde está a base eleitoral.
  // Numa eleição municipal (abrang M) 100% dos votos são no próprio município: pct fica null, só votos absolutos.
  const pctVotosEm = (c, mun) => {
    const lista = c.votosAnt || [];
    if (!lista.length) return null;
    const est = lista.find((v) => v.abrang !== 'M');
    const v = est || lista[0];
    const t = v.top.find((x) => normMun(x.mun) === normMun(mun));
    return { ano: v.ano, cargo: v.cargo, municipal: !est, pct: est ? (t ? t.pct : 0) : null, votos: t ? t.votos : 0, total: v.total, top1: v.top[0] };
  };

  // ---------- pedaços de UI ----------
  function tagsCandidato(c) {
    const out = [];
    out.push(`<span class="tag cargo">${esc(c.cargo)}</span>`);
    out.push(`<span class="tag plain">${esc(c.partido)}</span>`);
    out.push(`<span class="tag ${sitClasse(c.sit)}">${esc(sitCurta(c.sit))}</span>`);
    if (c.motivos && c.motivos.length) out.push(`<span class="tag bad" title="${esc(c.motivos.join(' | '))}">Motivo registrado</span>`);
    if (c.reeleicao) out.push('<span class="tag plain">Reeleição</span>');
    else if (c.vezesEleito) out.push(`<span class="tag plain">Eleito ${c.vezesEleito}x</span>`);
    const { uf: ufP, mun } = perfil();
    const munT = esc(titulo(mun));
    if (mun && disputouEm(c, mun)) out.push(`<span class="tag local">Disputou em ${munT}</span>`);
    const pv = mun ? pctVotosEm(c, mun) : null;
    if (pv && !pv.municipal && pv.pct >= 5) out.push(`<span class="tag local" title="${fmtNum(pv.votos)} de ${fmtNum(pv.total)} votos em ${pv.ano} (${esc(pv.cargo)})">${pv.pct}% dos votos em ${munT} (${pv.ano})</span>`);
    else if (pv && pv.municipal && pv.votos) out.push(`<span class="tag local">${fmtNum(pv.votos)} votos em ${munT} (${pv.ano}, ${esc(pv.cargo)})</span>`);
    if (mun && normMun(c.munNasc) === normMun(mun)) out.push(`<span class="tag local">Nascido em ${munT}</span>`);
    else if (ufP && c.ufNasc === ufP) out.push(`<span class="tag local">Nascido em ${esc(ufP)}</span>`);
    const ef = emendasFoco(c.sq);
    if (ef) out.push(`<span class="tag local" title="Emendas parlamentares destinadas a ${munT}: ${fmtMoeda(ef.destinado)} destinados, ${fmtMoeda(ef.pago)} pagos/recebidos">Emendas p/ ${munT}: ${fmtCurto(ef.destinado)}</span>`);
    Store.tags(c.sq).forEach((t) => out.push(`<span class="tag user">${icone('etiqueta')}${esc(t)}</span>`));
    return out.join('');
  }

  const fotoHtml = (c, classe = '') => fotoUrl(c)
    ? `<img class="foto ${classe}" src="${fotoUrl(c)}" alt="" loading="lazy">`
    : `<div class="foto vazia ${classe}" aria-hidden="true">${icone('pessoa')}</div>`;

  function cardCandidato(c, opts = {}) {
    const fav = Store.favorito(c.sq);
    const escolhido = opts.cargoEscolha && Store.escolhido(opts.cargoEscolha, c.sq);
    const extras = [titulo(c.ocupacao || '—'), c.idade ? c.idade + ' anos' : '', c.munNasc ? 'nascido em ' + titulo(c.munNasc) + (c.ufNasc ? '/' + c.ufNasc : '') : '',
      c.munHist && c.munHist.length ? 'já disputou em ' + c.munHist.map(titulo).join(', ') : ''].filter(Boolean);
    return el(`
      <button type="button" class="cand" data-sq="${esc(c.sq)}" aria-label="Abrir ficha de ${esc(titulo(c.urna))}, número ${esc(c.nr)}">
        ${escolhido ? `<span class="marcador escolhido" title="Escolhido">${icone('check')}</span>` : fav ? `<span class="marcador" title="Favorito">${icone('estrela', true)}</span>` : ''}
        ${fotoHtml(c)}
        <div class="titulo"><span class="numero">${esc(c.nr)}</span><span class="urna">${esc(titulo(c.urna))}</span></div>
        <div class="nome">${esc(titulo(c.nome))}${c.uf !== 'BR' ? ' · ' + esc(c.uf) : ''}</div>
        <div class="meta">${tagsCandidato(c)}</div>
        <div class="extra">${esc(extras.join(' · '))}</div>
      </button>`);
  }

  // ---------- emendas na ficha ----------
  function htmlEmendas(c, secao) {
    const e = Dados.emendas(c.sq);
    if (!e) return '';
    const foco = emendasFoco(c.sq);
    const nomeDestino = (m, uf) => m && m[0] === '(' ? (uf ? 'Vários municípios / estadual' : 'Nacional / não informado') : titulo(m) + (uf ? '/' + uf : '');
    const tabela = (linhas, cols) => {
      const max = Math.max(1, ...linhas.map((t) => t[2] || 0));
      return `<table class="tabela"><thead><tr><th>${cols[0]}</th>${cols.slice(1).map((c) => `<th class="r">${c}</th>`).join('')}<th><span class="sr-only">Proporção</span></th></tr></thead><tbody>
        ${linhas.map((t) => `<tr class="${munFoco() && normMun(t[0]) === normMun(munFoco()) ? 'foco' : ''}"><td>${esc(nomeDestino(t[0], t[1]))}</td><td class="r num">${fmtCurto(t[2])}</td>${t.length > 3 ? `<td class="r num">${fmtCurto(t[3])}</td>` : ''}<td><div class="barra" style="width:90px"><i style="width:${Math.round(100 * (t[2] || 0) / max)}%"></i></div></td></tr>`).join('')}</tbody></table>`;
    };
    const nivel = (x, rotulo, estadual) => {
      if (!x) return '';
      const anos = Object.keys(x.anos || {});
      const periodo = anos.length ? (anos[0] === anos[anos.length - 1] ? anos[0] : anos[0] + '–' + anos[anos.length - 1]) : '';
      const destinado = estadual ? Math.max(x.prev || 0, x.emp || 0) : x.emp;
      // "RAFAEL BENTO (EX-PARLAMENTAR LEBRAO, NOS TERMOS...)" -> "Rafael Bento (ex-parlamentar Lebrao)"
      const autores = (x.autores || []).filter((a) => norm(a) !== norm(c.urna))
        .map((a) => { const m = a.match(/^([^(]+)\((EX-PARLAMENTAR [^,)]+)/i); return m ? titulo(m[1].trim()) + ' (' + m[2].toLowerCase().replace(/ex-parlamentar /, 'emendas de ') + ')' : titulo(a); });
      const recMun = x.recMun && x.recMun.length ? `<div class="small" style="margin-top:8px"><b>Onde o dinheiro chegou</b> <span class="muted">(pagamentos recebidos por prefeituras, fundos e entidades, por município · ${fmtNum(x.nRecMun)} municípios)</span></div>${tabela(x.recMun, ['Município', 'Recebido'])}` : '';
      const declarado = (x.topMun || []).length ? `<div class="small" style="margin-top:8px"><b>Destino declarado no orçamento</b></div>${tabela(x.topMun, ['Destino', estadual ? 'Previsto' : 'Empenhado', 'Pago'])}` : '';
      return `<div class="bloco-emenda"><b>${rotulo}</b> <span class="muted small">${periodo} · ${fmtNum(x.n)} registros${autores.length ? ' · também como ' + esc(autores.join(', ')) : ''}</span>
        <div class="detalhes" style="margin-top:4px">
          <div><b>${estadual ? 'Valor previsto/empenhado' : 'Empenhado (reservado)'}</b>${fmtMoeda(destinado)}</div>
          <div><b>Pago</b>${fmtMoeda(x.pago)}</div>
          ${x.funcoes && x.funcoes.length ? `<div><b>Principais áreas</b>${esc(x.funcoes.slice(0, 4).map((f) => titulo(f[0] || '—')).join(', '))}</div>` : ''}
        </div>
        ${recMun}${declarado}
      </div>`;
    };
    const titulo_ = `Emendas parlamentares <span class="muted small">(para onde mandou recursos)</span>`;
    const munT = esc(titulo(munFoco()));
    const destaque = !munFoco() ? '' : foco
      ? `<div class="bloco destaque-foco">${icone('dinheiro')}<div><b>${munT}: ${fmtMoeda(foco.destinado)} destinados</b> · ${fmtMoeda(foco.pago)} pagos/recebidos · ${fmtNum(foco.n)} registro(s)${foco.fed && foco.fed.rec ? `<div class="small muted">Inclui ${fmtMoeda(foco.fed.rec)} recebidos por prefeitura, fundos e entidades de ${munT} (emendas federais).</div>` : ''}</div></div>`
      : temEmendasMun() ? `<div class="bloco small muted">Nenhuma emenda identificada para ${munT}.</div>` : '';
    return secao(titulo_, `${destaque}
      ${nivel(e.fed, 'Federais (como deputado federal/senador)', false)}
      ${nivel(e.est, 'Estaduais RO (como deputado estadual)', true)}
      <p class="small muted">"Empenhado" é o valor reservado no orçamento; "pago" é o que saiu de fato. Valores somados desde 2014 (federal) e 2023 (estadual). Emendas de bancada, comissão e relator não entram aqui porque não têm autor individual.</p>
      <div class="links-doc">
        <a class="btn mini" href="emendas.html#emendas" data-tela="tela-emendas">${icone('dinheiro')}Emendas por município</a>
        ${e.fed ? `<a class="btn mini" href="https://portaldatransparencia.gov.br/emendas" target="_blank" rel="noopener">${icone('externo')}Portal da Transparência</a>` : ''}
        ${e.est ? `<a class="btn mini" href="https://transparencia.ro.gov.br/emenda" target="_blank" rel="noopener">${icone('externo')}Transparência RO</a>` : ''}
      </div>`, !!foco);
  }

  // ---------- financiamento de campanha na ficha (prestação de contas TSE) ----------
  const pctFundoPublico = (ct) => ct && ct.rec ? Math.round(100 * ((ct.fontes.fefc || 0) + (ct.fontes.fp || 0)) / ct.rec) : null;
  function htmlContas(c, secao) {
    const ct = c.contas;
    if (!ct) return '';
    const f = ct.fontes || {};
    const pct = (v, t) => t ? Math.round(100 * v / t) : 0;
    const barraFontes = ct.rec ? `<div class="barra-fontes" role="img" aria-label="Fundo eleitoral ${pct(f.fefc || 0, ct.rec)}%, fundo partidário ${pct(f.fp || 0, ct.rec)}%, outros recursos ${pct(f.outros || 0, ct.rec)}%">
        <i class="fefc" style="width:${pct(f.fefc || 0, ct.rec)}%"></i><i class="fp" style="width:${pct(f.fp || 0, ct.rec)}%"></i><i class="outros" style="width:${pct(f.outros || 0, ct.rec)}%"></i></div>
      <div class="legenda-barras"><span><i class="fefc"></i>Fundo eleitoral ${fmtCurto(f.fefc || 0)}</span><span><i class="fp"></i>Fundo partidário ${fmtCurto(f.fp || 0)}</span><span><i class="outros"></i>Doações e recursos próprios ${fmtCurto(f.outros || 0)}</span></div>` : '';
    const limite = c.despesaMax ? `<div><b>Gasto x limite legal</b>${pct(ct.desp, c.despesaMax)}% de ${fmtMoeda(c.despesaMax)}<div class="barra" style="margin-top:4px"><i style="width:${Math.min(100, pct(ct.desp, c.despesaMax))}%"></i></div></div>` : '';
    const lin = (l, fmt) => l.map((x) => `<tr>${fmt(x)}</tr>`).join('');
    const doadores = (ct.doadores || []).length ? `<div class="small" style="margin-top:10px"><b>Maiores doadores</b> <span class="muted">(${fmtNum(ct.nDoadores)} no total)</span></div>
      <table class="tabela"><thead><tr><th>Doador</th><th>Tipo</th><th class="r">Valor</th></tr></thead><tbody>
      ${lin(ct.doadores, (d) => `<td>${esc(d[0])}${d[3] && !norm(d[0]).includes(norm(d[3])) ? ' <span class="muted small">· ' + esc(d[3]) + '</span>' : ''}</td><td><span class="tag ${d[1] === 'Partido' ? 'cargo' : 'plain'}">${esc(d[1])}</span></td><td class="r num">${fmtMoeda(d[2])}</td>`)}</tbody></table>` : '';
    const cats = (ct.cats || []).length ? `<div class="small" style="margin-top:10px"><b>Com o que gastou</b></div>
      <table class="tabela"><tbody>${lin(ct.cats, (x) => `<td>${esc(x[0])}</td><td class="r num">${fmtCurto(x[1])}</td><td><div class="barra" style="width:90px"><i style="width:${pct(x[1], ct.cats[0][1])}%"></i></div></td>`)}</tbody></table>` : '';
    const fornec = (ct.fornec || []).length ? `<div class="small" style="margin-top:10px"><b>Maiores fornecedores</b> <span class="muted">(${fmtNum(ct.nFornec)} no total)</span></div>
      <table class="tabela"><tbody>${lin(ct.fornec, (x) => `<td>${esc(x[0])}</td><td class="r num">${fmtMoeda(x[1])}</td>`)}</tbody></table>` : '';
    const fp = pctFundoPublico(ct);
    return secao(`Financiamento de campanha <span class="muted small">(${fmtCurto(ct.rec)} arrecadados${fp != null ? ' · ' + fp + '% dinheiro público' : ''})</span>`, `
      <div class="detalhes" style="margin-top:4px">
        <div><b>Arrecadado</b>${fmtMoeda(ct.rec)}${ct.recEst ? `<div class="small muted">inclui ${fmtMoeda(ct.recEst)} em bens/serviços estimáveis</div>` : ''}</div>
        <div><b>Gastos contratados</b>${fmtMoeda(ct.desp)}</div>
        <div><b>Gastos já pagos</b>${fmtMoeda(ct.pago)}</div>
        ${limite}
      </div>
      ${barraFontes}
      ${doadores}${cats}${fornec}
      <p class="small muted">Prestação de contas ${esc((ct.tipo || '').toLowerCase())} entregue ao TSE em ${esc(ct.data)} — os números ainda vão mudar até a prestação final, depois da eleição. "Fundo eleitoral" (FEFC) e "fundo partidário" são dinheiro público repassado pelo partido.</p>`, false);
  }

  // ---------- votações nominais na ALE-RO (ficha) ----------
  function htmlAlero(c, secao) {
    const r = Dados.aleroCand(c.sq);
    if (!r) return '';
    const A = Dados.alero();
    const cont = {};
    r.vot.forEach((x) => { const v = x.v[r.pid]; cont[v] = (cont[v] || 0) + 1; });
    const ordem = ['S', 'N', 'A', 'U', 'X', '?'];
    const resumo = ordem.filter((k) => cont[k]).map((k) => `<div><b>${VOTO_ROT[k]}</b>${fmtNum(cont[k])}</div>`).join('');
    const MAX = 15;
    const linhas = r.vot.slice(0, MAX).map((x) => {
      const lk = linkMateria(x);
      return `<tr><td class="num">${fmtData(x.d)}</td>
        <td>${lk ? `<a href="${lk}" target="_blank" rel="noopener">${esc(nomeMateria(x))}</a>` : esc(nomeMateria(x))}<div class="small muted">${esc(x.e.length > 160 ? x.e.slice(0, 157) + '…' : x.e)}</div>${avisoPlacar(x)}</td>
        <td class="small">${esc(x.r)}</td><td>${votoTag(x.v[r.pid])}</td></tr>`;
    }).join('');
    const periodo = r.vot.length ? fmtData(r.vot[r.vot.length - 1].d) + ' a ' + fmtData(r.vot[0].d) : '';
    // leis decididas em plenário desde 2023: autoria e posições declaradas em documento oficial
    const leis = A.leis || [];
    const autoria = leis.filter((l) => l.aut.some((a) => a.parl === r.pid));
    const decls = leis.flatMap((l) => (l.decl || []).filter((d) => d.parlamentar === r.pid).map((d) => ({ l, d })));
    const blocoLeis = leis.length ? `<div class="bloco-emenda"><b>Leis decididas em plenário desde ${fmtData(A.leisDesde)}</b>
      <div class="detalhes" style="margin-top:4px">
        <div><b>Autor ou coautor</b>${fmtNum(autoria.length)}${autoria.length ? ` <span class="small muted">(${fmtNum(autoria.filter((l) => !l.nominal).length)} sem voto individual registrado)</span>` : ''}</div>
      </div>
      ${decls.map(({ l, d }) => `<div class="vt-decl small"><b>${esc(nomeMateria(l))}</b> (${fmtData(d.data)}): ${esc(d.texto)}<div class="muted">Fonte: <a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.fonte)}</a></div></div>`).join('')}
      <p class="small muted">Na votação simbólica não fica registrado como cada deputado votou. Só aparecem posições declaradas em documento oficial da ALE-RO.</p>
    </div>` : '';
    return secao(`Votações na Assembleia Legislativa de RO <span class="muted small">(${fmtNum(r.vot.length)} votações nominais como ${esc(titulo(r.parl.n))})</span>`, `
      <div class="detalhes" style="margin-top:4px">${resumo}</div>
      <p class="small muted">Período: ${periodo}. Mostrando as ${Math.min(MAX, r.vot.length)} mais recentes.</p>
      <div style="overflow-x:auto"><table class="tabela vot-tabela"><thead><tr><th>Data</th><th>Matéria</th><th>Resultado</th><th>Voto</th></tr></thead><tbody>${linhas}</tbody></table></div>
      ${r.vot.slice(0, MAX).some(ehVeto) ? `<p class="small"><b>${LEGENDA_VETO}.</b></p>` : ''}
      <p class="small muted">Só as votações nominais registram o voto de cada deputado (vetos, leis complementares, emendas à Constituição do Estado). Projetos de lei ordinária costumam ser votados de forma simbólica, sem registro de quem votou como. A ALE-RO lança os votos no sistema com atraso: último registro em ${fmtData(A.ultimaVotacao)}.</p>
      ${blocoLeis}
      <div class="links-doc">
        <a class="btn mini ver-votacoes" href="votacoes.html#votacoes-${esc(r.pid)}" data-tela="tela-votacoes" data-dep="${esc(r.pid)}">${icone('plenario')}Todas as votações de ${esc(titulo(r.parl.n))}</a>
        <a class="btn mini" href="https://sapl.al.ro.leg.br/parlamentar/${esc(r.pid)}" target="_blank" rel="noopener">${icone('externo')}Perfil na ALE-RO (SAPL)</a>
      </div>`, false);
  }

  // ---------- votações nominais na Câmara / no Senado (ficha) ----------
  function tabelaVotosFed(casa, r, MAX = 15) {
    const cont = {};
    r.vot.forEach((x) => { const v = x.v[r.pid]; cont[v] = (cont[v] || 0) + 1; });
    const resumo = Object.entries(cont).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<div><b>${esc(k)}</b>${fmtNum(n)}</div>`).join('');
    const linhas = r.vot.slice(0, MAX).map((x) => {
      const lk = CASAS[casa].link(x);
      const nome = x.ident || nomeMateria(x) || 'Votação';
      const txt = x.e || x.desc || '';
      return `<tr><td class="num">${fmtData(x.d)}</td>
        <td>${lk ? `<a href="${lk}" target="_blank" rel="noopener">${esc(nome)}</a>` : esc(nome)}<div class="small muted">${esc(txt.length > 160 ? txt.slice(0, 157) + '…' : txt)}</div></td>
        <td class="small">${esc(x.r)}</td><td>${votoTagTexto(x.v[r.pid])}</td></tr>`;
    }).join('');
    const periodo = r.vot.length ? fmtData(r.vot[r.vot.length - 1].d) + ' a ' + fmtData(r.vot[0].d) : '';
    return `<div class="detalhes" style="margin-top:4px">${resumo}</div>
      <p class="small muted">${fmtNum(r.vot.length)} votações nominais registradas, de ${periodo}. Mostrando as ${Math.min(MAX, r.vot.length)} mais recentes. Os votos aparecem com o rótulo oficial ${CASAS[casa].daCasa}.</p>
      <div style="overflow-x:auto"><table class="tabela vot-tabela"><thead><tr><th>Data</th><th>Matéria</th><th>Resultado</th><th>Voto</th></tr></thead><tbody>${linhas}</tbody></table></div>
      <div class="links-doc"><a class="btn mini" href="votacoes.html#votacoes-${casa}-${esc(r.pid)}" data-tela="tela-votacoes" data-dep="${esc(r.pid)}" data-casa="${casa}">${icone('plenario')}Todas as votações de ${esc(titulo(r.parl.n))} (${CASAS[casa].nome})</a></div>`;
  }
  function htmlSenado(c, secao) {
    const r = Dados.votosFed('senado', c.sq);
    if (!r) return '';
    return secao(`Votações no Senado Federal <span class="muted small">(${fmtNum(r.vot.length)} votações nominais como ${esc(titulo(r.parl.n))})</span>`,
      tabelaVotosFed('senado', r) + '<p class="small muted">"Votou (voto secreto)" = a votação era secreta (ex.: indicação de autoridades): o Senado registra só que o senador votou, não como.</p>', false);
  }

  // ---------- concordância: posições do eleitor x votos registrados do candidato ----------
  // Só entram as votações que o eleitor marcou E em que o candidato votou Sim ou Não (ausência, abstenção,
  // obstrução e voto secreto não contam nem a favor nem contra).
  const idxVot = {};
  const acharVotacao = (casa, id) => {
    if (!idxVot[casa]) {
      const lista = casa === 'alero' ? ((window.ALERO || {}).vot || []) : (((window.VOTFED || {})[casa] || {}).vot || []);
      idxVot[casa] = new Map(lista.map((x) => [String(x.id), x]));
    }
    return idxVot[casa].get(String(id)) || null;
  };
  const pidDe = (casa, sq) => casa === 'alero' ? ((window.ALERO || {}).porCand || {})[sq] : ((((window.VOTFED || {})[casa]) || {}).porCand || {})[sq];
  const simNao = (v) => { const n = norm(v); return n === 's' || n === 'sim' ? 'S' : n === 'n' || n === 'nao' ? 'N' : null; };
  function concordancia(c) {
    const itens = [];
    for (const [k, minha] of Object.entries(Store.posicoes())) {
      const i = k.indexOf(':'); const casa = k.slice(0, i), id = k.slice(i + 1);
      const pid = pidDe(casa, c.sq); if (!pid) continue;
      const x = acharVotacao(casa, id); if (!x) continue;
      const dele = simNao(x.v[pid]); if (!dele) continue;
      itens.push({ casa, x, minha, dele, igual: dele === minha });
    }
    return { total: itens.length, iguais: itens.filter((t) => t.igual).length, itens };
  }
  const NOME_CASA = { alero: 'ALE-RO', camara: 'Câmara', senado: 'Senado' };
  function htmlConcordancia(c, secao) {
    if (!Object.keys(Store.posicoes()).length) return '';
    const r = concordancia(c);
    if (!r.total) return '';
    const linhas = r.itens.map((t) => `<tr><td class="num">${fmtData(t.x.d)}</td><td>${esc(NOME_CASA[t.casa])} · ${esc(t.x.ident || nomeMateria(t.x))}${ehVeto(t.x) ? ' <span class="small muted">(Sim = manter o veto)</span>' : ''}<div class="small muted">${esc((t.x.e || t.x.desc || '').slice(0, 120))}</div></td>
      <td>${votoTag(t.minha)}</td><td>${votoTag(t.dele)}</td><td>${t.igual ? '<span class="tag plain">Igual</span>' : '<span class="tag plain">Diferente</span>'}</td></tr>`).join('');
    return secao(`Comparação com as suas posições <span class="muted small">(mesma posição em ${r.iguais} de ${r.total})</span>`, `
      <div style="overflow-x:auto"><table class="tabela vot-tabela"><thead><tr><th>Data</th><th>Votação</th><th>Você</th><th>Candidato</th><th></th></tr></thead><tbody>${linhas}</tbody></table></div>
      <p class="small muted">Só entram as votações que você marcou na tela Votações e em que o candidato votou Sim ou Não. Ausência, abstenção e voto secreto não contam.</p>`, true);
  }

  // ---------- ficha (modal) ----------
  const Modal = {
    abrir(c, opts = {}) {
      this.fechar();
      this._foco = document.activeElement;
      const d = (label, val) => val ? `<div><b>${label}</b>${esc(val)}</div>` : '';
      const secao = (tituloHtml, conteudo, aberto) => `<details class="secao" ${aberto ? 'open' : ''}><summary>${icone('seta')}<span>${tituloHtml}</span></summary><div class="conteudo">${conteudo}</div></details>`;
      const resCls = (r) => { const n = norm(r); return n.startsWith('eleito') ? 'ok' : (n.includes('nao eleito') || n.includes('negado') || n.includes('renunc') || n.includes('cassa')) ? 'bad' : 'plain'; };

      const chapa = (c.chapa || []).map((m) => `<div class="membro">${fotoHtml(m, 'mini')}<div><b>${esc(m.cargo)}</b> ${esc(titulo(m.nome))}${m.nomeCompleto && norm(m.nomeCompleto) !== norm(m.nome) ? ' <span class="muted">(' + esc(titulo(m.nomeCompleto)) + ')</span>' : ''} · ${esc(m.partido)}${m.sit ? ` <span class="tag ${sitClasse(m.sit)}">${esc(sitCurta(m.sit))}</span>` : ''}
        ${(m.certidoes || []).length ? '<div class="links-doc" style="margin:4px 0 0">' + m.certidoes.map((p, i) => `<a class="btn mini" href="${encodeURI(p)}" target="_blank" rel="noopener">${icone('balanca')}Certidão ${i + 1}</a>`).join('') + '</div>' : ''}</div></div>`).join('');
      const hist = (c.hist || []).map((h) => `<tr><td class="num">${h.ano || ''}</td><td>${esc(h.cargo)}</td><td>${esc(titulo(h.ue))}${h.uf ? '/' + esc(h.uf) : ''}</td><td>${esc(h.partido)}${h.nr ? ' · ' + esc(h.nr) : ''}</td><td><span class="tag ${resCls(h.resultado)}">${esc(titulo(h.resultado || 'sem resultado'))}</span></td></tr>`).join('');
      const votos = (c.votosAnt || []).map((v, i) => secao(`Votação por município — ${v.ano} <span class="muted small">(${esc(v.cargo)}${v.abrang === 'M' ? ' em ' + esc(titulo(v.ue)) : ''} · ${fmtNum(v.total)} votos${v.municipios > 1 ? ' em ' + v.municipios + ' municípios' : ''})</span>`,
        `<table class="tabela"><thead><tr><th>Município</th><th class="r">Votos</th><th class="r">%</th><th><span class="sr-only">Proporção</span></th></tr></thead><tbody>
        ${v.top.map((t) => `<tr class="${munFoco() && normMun(t.mun) === normMun(munFoco()) ? 'foco' : ''}"><td>${esc(titulo(t.mun))}/${esc(t.uf)}</td><td class="r num">${fmtNum(t.votos)}</td><td class="r num">${t.pct}%</td><td><div class="barra" style="width:110px"><i style="width:${Math.min(100, t.pct)}%"></i></div></td></tr>`).join('')}
        </tbody></table>`, i === 0)).join('');
      const bens = (c.bensLista || []).map((b) => `<tr><td>${esc(titulo(b.tipo).split(':')[0])}</td><td>${esc(b.desc)}</td><td class="r num">${fmtMoeda(b.valor)}</td></tr>`).join('');
      const motivos = (c.motivos || []).map((m) => `<li>${esc(m)}</li>`).join('');
      const propostas = (c.propostas || []).map((p, i) => `<a class="btn mini" href="${encodeURI(p)}" target="_blank" rel="noopener">${icone('doc')}Plano de governo${c.propostas.length > 1 ? ' ' + (i + 1) : ''}</a>`).join('');
      const certidoes = (c.certidoes || []).map((p, i) => `<a class="btn mini" href="${encodeURI(p)}" target="_blank" rel="noopener" title="${esc(p.split('/').pop())}">${icone('balanca')}Certidão ${i + 1}</a>`).join('');
      const redes = (c.redes || []).map((u) => { const href = /^https?:/i.test(u) ? u : 'https://' + u; return `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, ''))}</a>`; }).join(' · ');
      const cam = Dados.camara(c.sq);
      const camaraHtml = cam ? secao(`Atuação na Câmara dos Deputados <span class="muted small">(${cam.atual === false ? 'ex-deputado · ' : ''}dados abertos da Câmara)</span>`, `
        <div class="detalhes" style="margin-top:4px">
          ${d('Situação', cam.situacao)}${d(cam.atual === false ? 'Último partido / UF' : 'Partido / UF atual', (cam.partido || '') + (cam.uf ? ' / ' + cam.uf : ''))}
          ${cam.mandatos && cam.mandatos.length ? d('Mandatos na Câmara', cam.mandatos.join(', ')) : ''}
          ${cam.proposicoes != null ? d('Proposições de autoria (' + (cam.propDesde || '2023') + '–2026)', fmtNum(cam.proposicoes)) : ''}
          ${cam.despesas ? Object.entries(cam.despesas).map(([ano, v]) => d('Cota parlamentar ' + ano, fmtMoeda(v))).join('') : ''}
          ${cam.frentes != null ? d('Frentes parlamentares', fmtNum(cam.frentes)) : ''}
          ${cam.orgaos && cam.orgaos.length ? d('Comissões / órgãos', cam.orgaos.join('; ')) : ''}
        </div>
        <div class="links-doc">
          ${cam.url ? `<a class="btn mini" href="${esc(cam.url)}" target="_blank" rel="noopener">${icone('externo')}Perfil na Câmara</a>` : ''}
          ${cam.id && cam.atual !== false ? `<a class="btn mini" href="https://www.camara.leg.br/deputados/${cam.id}/votacoes-nominais-plenario/2026" target="_blank" rel="noopener">${icone('externo')}Como votou (2026)</a>` : ''}
          ${cam.id && cam.atual !== false ? `<a class="btn mini" href="https://www.camara.leg.br/deputados/${cam.id}/votacoes-nominais-plenario/2025" target="_blank" rel="noopener">${icone('externo')}Como votou (2025)</a>` : ''}
          ${cam.id && cam.atual !== false ? `<a class="btn mini" href="https://www.camara.leg.br/deputados/${cam.id}/presenca-plenario/2026" target="_blank" rel="noopener">${icone('externo')}Presença</a>` : ''}
          ${cam.id ? `<a class="btn mini" href="https://www.camara.leg.br/busca-portal?contextoBusca=BuscaProposicoes&pagina=1&order=data&abaEspecifica=true&q=autores.ideCadastro:%20${cam.id}" target="_blank" rel="noopener">${icone('externo')}Projetos de autoria</a>` : ''}
          ${cam.id && cam.atual !== false ? `<a class="btn mini" href="https://www.camara.leg.br/cota-parlamentar/consulta-cota-parlamentar?ideDeputado=${cam.id}&dataInicio=012025&dataFim=122026" target="_blank" rel="noopener">${icone('externo')}Gastos (cota)</a>` : ''}
        </div>
        ${(() => { const r = Dados.votosFed('camara', c.sq); return r ? `<div class="bloco-emenda"><b>Como votou na Câmara</b>${tabelaVotosFed('camara', r)}</div>` : ''; })()}`, true) : '';
      const senadoHtml = htmlSenado(c, secao);
      const emendasHtml = htmlEmendas(c, secao);
      const contasHtml = htmlContas(c, secao);
      const aleroHtml = htmlAlero(c, secao);
      const concHtml = htmlConcordancia(c, secao);
      const dv = linkDivulga(c);
      const ag = agremiacao(c);
      const cargoEscolha = opts.cargoEscolha || c.cargo;
      const escolhido = () => Store.escolhido(cargoEscolha, c.sq);

      const fundo = el(`
        <div class="modal-fundo">
          <div class="modal" role="dialog" aria-modal="true" aria-labelledby="ficha-titulo">
            <button type="button" class="btn icone fechar" aria-label="Fechar ficha">${icone('fechar')}</button>
            <div class="cab">
              ${fotoHtml(c, 'grande')}
              <div class="cresce">
                <div class="linha"><span class="numero">${esc(c.nr)}</span><h2 id="ficha-titulo">${esc(titulo(c.urna))}</h2></div>
                <div class="muted">${esc(titulo(c.nome))}${c.social ? ' · nome social: ' + esc(titulo(c.social)) : ''}</div>
                <div class="muted small">${esc(c.cargo)} · ${esc(c.ue || c.uf)} · ${esc(c.partido)}</div>
              </div>
            </div>
            <div class="meta">${tagsCandidato(c)}</div>
            <div class="detalhes">
              ${d('Partido', c.partido + (c.nomePartido ? ' — ' + titulo(c.nomePartido) : ''))}
              ${ag.tipo === 'federacao' ? d('Federação', ag.nome + ' (' + ag.comp + ')') : ''}
              ${ag.tipo === 'coligacao' ? d('Coligação', ag.nome + ' (' + (c.compColigacao || ag.comp) + ')') : ''}
              ${d('Situação do registro', sitCurta(c.sit) + (c.sitApto && norm(c.sitApto) !== norm(c.sit) ? ' (' + titulo(c.sitApto) + ')' : ''))}
              ${d('Apto na urna', c.urnaOk == null ? '' : c.urnaOk ? 'Sim' : 'Não')}
              ${d('Nascimento', (c.munNasc ? titulo(c.munNasc) + (c.ufNasc ? '/' + c.ufNasc : '') : '') + (c.nasc ? ' · ' + c.nasc : '') + (c.idade ? ' · ' + c.idade + ' anos' : ''))}
              ${d('Gênero', titulo(c.genero))}
              ${d('Cor/raça', titulo(c.corRaca))}
              ${d('Estado civil', titulo(c.estadoCivil))}
              ${d('Escolaridade', titulo(c.instrucao))}
              ${d('Ocupação', titulo(c.ocupacao))}
              ${d('Tenta reeleição', c.reeleicao ? 'Sim (eleito na eleição anterior para o mesmo cargo)' : 'Não')}
              ${d('Histórico', c.vezesCand ? c.vezesCand + ' candidatura(s) anterior(es) · eleito ' + c.vezesEleito + 'x' : 'primeira candidatura registrada')}
              ${c.bens != null ? d('Bens declarados', fmtMoeda(c.bens)) : ''}
              ${c.despesaMax ? d('Limite de gastos', fmtMoeda(c.despesaMax)) : ''}
              ${d('Nacionalidade', c.nacionalidade && !norm(c.nacionalidade).startsWith('brasileira nata') ? c.nacionalidade : '')}
              ${c.quilombola ? d('Quilombola', 'Sim') : ''}${d('Etnia indígena', c.etnia)}
              ${c.substituido ? d('Substituído', 'Sim') : ''}${d('Destinação dos votos', c.destVotos && norm(c.destVotos) !== 'valido' ? c.destVotos : '')}
              ${d('E-mail', c.email)}
              ${d('Sequencial TSE', c.sq)}
            </div>
            <div class="links-doc"><a class="btn mini ver-aliados" href="coligacoes.html#coligacoes-${esc(c.uf)}-${esc(c.sq)}" data-tela="tela-coligacoes" data-sq="${esc(c.sq)}" data-uf="${esc(c.uf)}">${icone('rede')}Para onde vai o voto em ${esc(titulo(c.urna))}</a></div>
            ${chapa ? `<div class="bloco"><b>Chapa</b>${chapa}</div>` : ''}
            ${motivos ? `<div class="bloco alerta"><b>Motivos de indeferimento / cassação registrados pelo TSE</b><ul>${motivos}</ul></div>` : ''}
            ${(propostas || certidoes) ? `<div class="links-doc">${propostas}${certidoes}</div>` : ''}
            ${c.docsOnline && dv ? `<div class="links-doc"><a class="btn mini" href="${dv}" target="_blank" rel="noopener">${icone('doc')}${c.docsOnline.propostas ? 'Plano de governo e ' : ''}certidões (${c.docsOnline.certidoes || 0}) no TSE — online</a></div>` : ''}
            ${concHtml}
            ${camaraHtml}
            ${senadoHtml}
            ${aleroHtml}
            ${emendasHtml}
            ${contasHtml}
            ${hist ? secao(`Histórico eleitoral <span class="muted small">(${c.hist.length})</span>`, `<table class="tabela"><thead><tr><th>Ano</th><th>Cargo</th><th>Local</th><th>Partido · nº</th><th>Resultado</th></tr></thead><tbody>${hist}</tbody></table>`, true) : ''}
            ${votos}
            ${bens ? secao(`Bens declarados <span class="muted small">— ${fmtMoeda(c.bens)} (${c.bensLista.length} itens)</span>`, `<table class="tabela"><tbody>${bens}</tbody></table>`, false) : ''}
            ${redes ? `<div class="small" style="margin-top:10px"><b>Redes sociais:</b> ${redes}</div>` : ''}
            <div class="linha small" style="margin-top:8px">
              ${dv ? `<a href="${dv}" target="_blank" rel="noopener">${icone('externo')} Perfil no DivulgaCandContas (TSE)</a>` : ''}
              <a href="${linkBusca(c)}" target="_blank" rel="noopener">${icone('externo')} Pesquisar na web</a>
            </div>
            <div class="pessoal">
              <div class="linha">
                <button type="button" class="btn fav" aria-pressed="${Store.favorito(c.sq)}">${icone('estrela', Store.favorito(c.sq))}<span class="fav-txt">${Store.favorito(c.sq) ? 'Favorito' : 'Favoritar'}</span></button>
                <button type="button" class="btn escolher ${escolhido() ? 'ok' : ''}" aria-pressed="${escolhido()}">${icone('check')}<span class="esc-txt">${escolhido() ? 'Escolhido para ' + esc(cargoEscolha) : 'Escolher para ' + esc(cargoEscolha)}</span></button>
              </div>
              <div class="campo"><span class="rotulo" id="rot-tags">Minhas tags</span>
                <div class="tags-edit" aria-labelledby="rot-tags"></div>
                <div class="linha"><input type="text" class="nova-tag" aria-label="Nova tag" placeholder="ex.: minha cidade, conheço, evitar" style="max-width:280px">
                  <button type="button" class="btn mini add-tag">Adicionar tag</button>
                  ${munFoco() ? `<button type="button" class="btn mini tag-foco">Marcar "${esc(titulo(munFoco()))}"</button>` : ''}</div>
              </div>
              <div class="campo"><label for="ficha-nota">Minha nota</label><textarea id="ficha-nota" rows="3" class="nota" placeholder="Anotações pessoais sobre este candidato">${esc(Store.nota(c.sq))}</textarea></div>
            </div>
          </div>
        </div>`);
      const m = fundo.querySelector('.modal');
      const renderTags = () => {
        const box = m.querySelector('.tags-edit');
        box.innerHTML = Store.tags(c.sq).map((t) => `<span class="tag user">${esc(t)}<button type="button" data-tag="${esc(t)}" aria-label="Remover tag ${esc(t)}">${icone('fechar')}</button></span>`).join('') || '<span class="subtle small">nenhuma</span>';
        box.querySelectorAll('button').forEach((x) => x.onclick = () => { Store.delTag(c.sq, x.dataset.tag); renderTags(); });
      };
      renderTags();
      const addTag = () => { const i = m.querySelector('.nova-tag'); Store.addTag(c.sq, i.value); i.value = ''; renderTags(); };
      m.querySelector('.add-tag').onclick = addTag;
      m.querySelector('.nova-tag').onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } };
      const tf = m.querySelector('.tag-foco'); if (tf) tf.onclick = () => { Store.addTag(c.sq, titulo(munFoco())); renderTags(); };
      m.querySelector('.fav').onclick = (e) => { const on = Store.alternarFavorito(c.sq); const b = e.currentTarget; b.setAttribute('aria-pressed', on); b.innerHTML = icone('estrela', on) + `<span class="fav-txt">${on ? 'Favorito' : 'Favoritar'}</span>`; };
      m.querySelector('.escolher').onclick = (e) => { Store.alternarEscolha(cargoEscolha, c.sq); const on = escolhido(); const b = e.currentTarget; b.classList.toggle('ok', on); b.setAttribute('aria-pressed', on); b.querySelector('.esc-txt').textContent = (on ? 'Escolhido para ' : 'Escolher para ') + cargoEscolha; };
      m.querySelector('.nota').onchange = (e) => Store.setNota(c.sq, e.target.value);
      m.querySelectorAll('a[data-tela]').forEach((a) => a.onclick = (e) => {
        if (document.getElementById(a.dataset.tela)) {
          e.preventDefault(); this.fechar();
          if (a.dataset.dep) { window.App.votacoesDep = a.dataset.dep; window.App.votacoesCasa = a.dataset.casa || 'alero'; }   // tela Votações abre filtrada neste parlamentar
          if (a.dataset.sq) { window.App.coligacoesSq = a.dataset.sq; window.App.coligacoesUf = a.dataset.uf; }   // tela Coligações abre neste candidato
          Telas.mostrar(a.dataset.tela);
        }
      });
      m.querySelector('.fechar').onclick = () => this.fechar();
      fundo.onclick = (e) => { if (e.target === fundo) this.fechar(); };
      this._teclas = (e) => {
        if (e.key === 'Escape') { this.fechar(); return; }
        if (e.key === 'Tab') { // mantém o foco dentro da ficha
          const f = [...m.querySelectorAll('button, [href], input, select, textarea, summary')].filter((x) => !x.disabled && x.offsetParent !== null);
          if (!f.length) return;
          if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
          else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
        }
      };
      document.addEventListener('keydown', this._teclas);
      document.body.appendChild(fundo);
      document.body.style.overflow = 'hidden';
      this.atual = fundo;
      m.querySelector('.fechar').focus();
    },
    fechar() {
      if (!this.atual) return;
      this.atual.remove(); this.atual = null;
      document.removeEventListener('keydown', this._teclas);
      document.body.style.overflow = '';
      if (this._foco && this._foco.focus) { try { this._foco.focus(); } catch (e) { /* ignora */ } }
      document.dispatchEvent(new CustomEvent('modal:fechou'));
    },
  };

  // ---------- telas (mesma navegação no desktop e no celular) ----------
  // Cada tela é <section class="tela" id="tela-x">. Se a tela existe no documento, troca na hora;
  // se não existe (ex.: "Pesquisar" a partir de meu-voto.html), segue para o outro arquivo.
  const TELAS = [
    { id: 'tela-busca', hash: '', pagina: 'index.html', icone: 'busca', rotulo: 'Pesquisar', longo: ' candidatos' },
    { id: 'tela-voto', hash: '#voto', pagina: 'meu-voto.html', icone: 'voto', rotulo: 'Meu voto' },
    { id: 'tela-cola', hash: '#colinha', pagina: 'meu-voto.html', icone: 'urna', rotulo: 'Colinha' },
    { id: 'tela-emendas', hash: '#emendas', pagina: 'emendas.html', icone: 'dinheiro', rotulo: 'Emendas' },
    { id: 'tela-votacoes', hash: '#votacoes', pagina: 'votacoes.html', icone: 'plenario', rotulo: 'Votações' },
    { id: 'tela-coligacoes', hash: '#coligacoes', pagina: 'coligacoes.html', icone: 'rede', rotulo: 'Coligações', barraRotulo: 'Coliga&shy;ções' },
    { id: 'tela-perfil', hash: '#perfil', pagina: 'meu-voto.html', icone: 'pessoa', rotulo: 'Perfil' },
    { id: 'tela-mais', hash: '#mais', pagina: 'meu-voto.html', icone: 'lista', rotulo: 'Mais', barra: false },
  ];
  const Telas = {
    porHash(h) { h = (h || location.hash || '').toLowerCase(); return TELAS.find((t) => t.hash && h.startsWith(t.hash)) || null; },
    atual() { return document.querySelector('.tela.ativa'); },
    mostrar(id, opts = {}) {
      const alvo = document.getElementById(id);
      const t = TELAS.find((x) => x.id === id);
      if (!alvo) { if (t) location.href = t.pagina + t.hash; return; }
      document.querySelectorAll('.tela').forEach((s) => s.classList.toggle('ativa', s === alvo));
      document.querySelectorAll('[data-tela]').forEach((b) => { if (b.dataset.tela === id) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
      if (t && t.hash && location.hash !== t.hash && !opts.semHash) { try { history.replaceState(null, '', t.hash); } catch (e) { /* alguns contextos file:// não permitem; a tela já trocou */ } }
      if (!opts.semScroll) window.scrollTo(0, 0);
      document.dispatchEvent(new CustomEvent('tela:mudou', { detail: { id } }));
    },
    iniciar(padrao) {
      if (this._iniciado) return;   // no arquivo mobile as duas páginas chamam; vale a primeira (Pesquisar)
      this._iniciado = true;
      const h = this.porHash();
      const id = h && document.getElementById(h.id) ? h.id : padrao;
      this.mostrar(id, { semScroll: true });
      window.addEventListener('hashchange', () => { const x = this.porHash(); if (x && document.getElementById(x.id)) this.mostrar(x.id); });
    },
  };

  // ---------- cabeçalho comum ----------
  function montarTopo() {
    if (document.querySelector('.topbar')) return;
    const m = Dados.manifest();
    const links = TELAS.map((t) => `<a href="${t.pagina}${t.hash}" data-tela="${t.id}">${icone(t.icone)}<span>${t.rotulo}${t.longo ? '<span class="rotulo-longo">' + t.longo + '</span>' : ''}</span></a>`).join('');
    const t = el(`
      <header class="topbar"><div class="inner">
        <a class="brand" href="index.html"><span class="marca" aria-hidden="true">MV</span><span class="texto">Meu Voto 2026</span></a>
        <nav class="nav" aria-label="Páginas">${links}</nav>
      </div></header>`);
    t.querySelectorAll('.nav a').forEach((a) => a.onclick = (e) => { if (document.getElementById(a.dataset.tela)) { e.preventDefault(); Telas.mostrar(a.dataset.tela); } });
    document.body.prepend(el('<a class="skip" href="#conteudo">Ir para o conteúdo</a>'));
    document.querySelector('.skip').after(t);
    if (m.amostra) t.after(el('<div class="aviso" role="status"><b>Dados de amostra (fictícios).</b> Coloque os ZIPs do TSE em raw/ e rode scripts/build_data.py — veja o README.</div>'));
    // navegação inferior (celular / janelas estreitas)
    const nav = el(`<nav class="bottom-nav" aria-label="Navegação">${TELAS.filter((x) => x.barra !== false).map((x) => `<button type="button" data-tela="${x.id}">${icone(x.icone)}<span>${x.barraRotulo || x.rotulo}</span></button>`).join('')}</nav>`);
    nav.querySelectorAll('button').forEach((b) => b.onclick = () => Telas.mostrar(b.dataset.tela));
    document.body.appendChild(nav);
  }

  window.App = { normMun, fmtCurto, emendasFoco, pctFundoPublico, norm, esc, titulo, el, fmtMoeda, fmtNum, icone, CARGOS_ORDEM, VAGAS, sitClasse, sitCurta, Dados, Store, Modal, Telas, TELAS, cardCandidato, tagsCandidato, fotoHtml, montarTopo, linkDivulga, linkPje, perfil, munFoco, setPerfil, temEmendasMun, concordancia, acharVotacao, disputouEm, fotoUrl, pctVotosEm,
    VOTO_ROT, votoTag, votoTagTexto, CASAS, fmtData, nomeMateria, linkMateria, ehVeto, LEGENDA_VETO, avisoPlacar,
    agremiacao, ehProporcional, chaveSigla, PROPORCIONAIS };
})();
