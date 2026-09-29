# Estado do projeto e próximos passos

Última sessão: **24/09/2026**. Eleição: **04/10/2026**.

## O que está pronto e conferido

- `scripts/baixar_tse.py`: baixa tudo do TSE; o bloqueio é contornado com curl_cffi e, se precisar, pelo Edge.
- `scripts/build_data.py`: dados dos 20.061 candidatos, incluindo a **prestação de contas 2026**.
- `scripts/fetch_emendas.py`: emendas federais (CGU) e estaduais de RO. Casamento federal confirmado por data de nascimento.
- `scripts/fetch_camara.py --todas`: **refeito em 23/09 com o código final**, as 27 UFs, 787 deputados (SP precisou de `--uf SP` por erro 504 da API).
- **Votações** (fases 1 a 3, 23/09) — tela `votacoes.html` com quatro modos e seções na ficha:
  - `scripts/fetch_alero.py`: ALE-RO, 2.173 votações nominais (2013 a 23/06/2026, data da sessão),
    32 candidatos ligados; 1.250 leis/PECs decididas em plenário desde 2023 (1.085 sem voto individual).
  - `scripts/fetch_votacoes_federais.py`: Câmara (4.073 votações, 15 candidatos de RO) e Senado (1.364, 2 candidatos), 2015–2026.
- **Perfil** (fase 4, 23/09): aba Perfil em `meu-voto.html#perfil` — estado e município livres (lista oficial,
  `scripts/build_municipios.py`), resumo dos critérios, posições nas votações ("Como você votaria?" na tela
  Votações) e o critério "Vota como eu". Quem já usava o sistema continua em Ariquemes/RO automaticamente.
  Critério que não se aplica a um candidato sai da média dele (sem informação não é zero).
- **Atas da ALE-RO** (24/09): `scripts/fetch_alero_atas.py` leu as 242 atas desde 2023 (OCR do Windows nas escaneadas)
  e achou 35 posições individuais em votações simbólicas (abstenções e votos contrários, a maioria do Delegado Camargo;
  também Eyder Brasil, Luizinho Goebel, Dra. Taíssa, Ismael Crispin). Todas conferidas na ata e cadastradas em
  `data/alero_declaracoes.json` com ata, folha e link (36 no total). Nas atualizações, `logs/atas_posicoes.md` mostra
  as posições NOVAS para conferir antes de cadastrar. As declarações aparecem na tela Votações e na ficha, mas não
  entram no critério "Vota como eu" (que usa só votações nominais).
- `scripts/testes/`: `rodar_testes.py` (dados + interface). Última rodada completa: ver o fim de
  `logs/rodar_testes_2026-09-24.log`.
- `scripts/atualizar_tudo.py`: atualiza tudo e testa em um comando (8 passos).
- **Auditoria cruzada** (23/09): `python scripts/testes/rodar_testes.py --cruzado` confere os dados contra as APIs
  oficiais (SAPL, Câmara, Senado) e o TSE; relatório em `scripts/testes/saida/auditoria_cruzada.md`. Achou e já
  corrigiu: paginação instável do SAPL (367 votações com data errada, 147 leis sem número; agora `o=id` + conferência
  do total), grafias "D'Oeste"/"do Oeste" (5 municípios de RO perdiam emendas/histórico), número da lei vindo da
  norma publicada. Resta 1 alerta da própria fonte (placar do veto 87/2017).

## Regra de todas as votações: neutralidade

O sistema só mostra "na votação X, o político Y votou Z", com link para a fonte oficial. Nada de rotular voto
como "a favor/contra o povo"; quem decide o que acha certo é o eleitor (posições no Perfil). Sim e Não têm cores
neutras. Votação simbólica aparece como "sem voto individual registrado"; posição individual só com documento
oficial (`data/alero_declaracoes.json`). Lista de presença não é voto e não é usada.

Casamentos parlamentar → candidato que exigiram cuidado (viraram testes): Kaká Mendonça ≠ Jean Mendonça,
Zequinha Araújo ≠ Dr. Ribamar Araújo, Jair Montes (pai) ≠ Jair Montes Jr., Pastor Moura ≠ Wilson Santiago (PB).
Nos vetos da ALE-RO, Sim = manter o veto (confere em 710 de 712; os 2 que não conferem ficam marcados).

## Antes da eleição (semana de 28/09 a 03/10)

```
python scripts\atualizar_tudo.py                # baixa o que mudou no TSE, regera tudo e testa
python scripts\build_mobile.py --todas          # (opcional) versão Brasil do arquivo do celular
```

Situações das candidaturas e prestação de contas mudam até o dia 4/10. Imprima a colinha (Meu voto → Colinha →
Imprimir) depois dessa atualização.

## Ideias para depois (não bloqueiam)

- Colocar o sistema na internet para o público (hoje é local). Confirmar antes: publica algo em nome do usuário.
- Emendas por município fora de RO (hoje o critério fica de fora do cálculo em outras UFs, com aviso).
- Votação de 2022 por município: a base guarda os 12 municípios com mais votos de cada candidato.
- Atas anteriores a 2023 não foram lidas (a lista de leis sem voto individual começa em 01/02/2023).
- Arquivo do celular versão Brasil ficou com ~77 MB (votações); dá para enxugar se for usado.

## Pendências conhecidas

- Emendas estaduais de RO: não há lista oficial com data de nascimento; casamento pelo nome de urna ou histórico.
- A Câmara (`camara.js`) só cobre quem foi deputado a partir de 2015.
- A ALE-RO lança os votos no SAPL com atraso (última sessão com votos lançados: 23/06/2026).
- Prestação de contas é parcial até a eleição (a ficha mostra a data da entrega).
- Conferir `mobile/meu-voto-mobile.html` em um celular de verdade (os testes emulam 4 aparelhos).
