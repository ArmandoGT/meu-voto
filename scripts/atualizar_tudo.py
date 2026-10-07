# -*- coding: utf-8 -*-
"""
atualizar_tudo.py - atualiza o sistema inteiro em um comando e confere o resultado.

    1. baixar_tse.py      baixa do TSE so o que mudou (candidatos, prestacao de contas, ...)
    2. build_data.py      regera data/cand_XX.js
    3. fetch_emendas.py   baixa e cruza as emendas (federais + estaduais RO)
    4. fetch_camara.py    atuacao na Camara dos candidatos de RO (atuais e ex-deputados)
    5. fetch_alero.py     votacoes da Assembleia Legislativa de RO (nominais + leis sem voto individual)
       fetch_alero_atas.py  atas novas da ALE-RO: lista posicoes individuais a conferir (logs/atas_posicoes.md)
    6. fetch_votacoes_federais.py  votacoes na Camara e no Senado dos candidatos de RO
    7. fetch_resultados.py + build_resultados.py  resultados da eleicao 2026 (site do TSE + votos por municipio)
       build_mapas.py     contorno dos municipios (malha do IBGE) para o mapa da tela Resultados
    8. build_mobile.py    regera mobile/meu-voto-mobile.html
    9. testes             confere os dados (e, sem --rapido, a interface e a auditoria cruzada com as APIs oficiais)

Uso:
    python scripts/atualizar_tudo.py            # tudo (~10 min na primeira vez; depois so o que mudou)
    python scripts/atualizar_tudo.py --rapido   # testa so os dados (sem abrir o Edge)

Depois da eleicao, rode de novo para atualizar os resultados (candidaturas sub judice podem mudar o resultado).
"""
import os
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def passo(titulo, args):
    print("\n" + "#" * 70 + "\n# " + titulo + "\n" + "#" * 70)
    t0 = time.time()
    r = subprocess.run([sys.executable] + args, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    print("# %s: %s (%.0f s)" % (titulo, "OK" if r.returncode == 0 else "ERRO %d" % r.returncode, time.time() - t0))
    return r.returncode == 0


def main():
    ok = passo("1/9 Baixando do TSE o que mudou", [os.path.join(SCRIPTS, "baixar_tse.py")])
    ok = passo("2/9 Gerando os dados dos candidatos", [os.path.join(SCRIPTS, "build_data.py")]) and ok
    ok = passo("3/9 Emendas parlamentares", [os.path.join(SCRIPTS, "fetch_emendas.py")]) and ok
    ok = passo("4/9 Camara dos Deputados (RO)", [os.path.join(SCRIPTS, "fetch_camara.py"), "--uf", "RO"]) and ok
    ok = passo("5/9 Votacoes da Assembleia Legislativa de RO", [os.path.join(SCRIPTS, "fetch_alero.py")]) and ok
    ok = passo("5/9 Atas da ALE-RO (posicoes em votacoes simbolicas)", [os.path.join(SCRIPTS, "fetch_alero_atas.py")]) and ok
    ok = passo("6/9 Votacoes na Camara e no Senado", [os.path.join(SCRIPTS, "fetch_votacoes_federais.py")]) and ok
    ok = passo("7/9 Resultados da eleicao 2026 (site do TSE)", [os.path.join(SCRIPTS, "fetch_resultados.py")]) and ok
    ok = passo("7/9 Resultados: vagas, votos por cidade e explicacoes", [os.path.join(SCRIPTS, "build_resultados.py")]) and ok
    ok = passo("7/9 Resultados: mapas dos municipios (IBGE)", [os.path.join(SCRIPTS, "build_mapas.py")]) and ok
    ok = passo("8/9 Versao para celular", [os.path.join(SCRIPTS, "build_mobile.py")]) and ok
    testes = [os.path.join(SCRIPTS, "testes", "rodar_testes.py")] + (["--so-dados"] if "--rapido" in sys.argv else ["--cruzado"])
    ok = passo("9/9 Testes", testes) and ok
    print("\n" + ("TUDO ATUALIZADO E CONFERIDO." if ok else "ATENCAO: algum passo falhou - veja as mensagens acima."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
