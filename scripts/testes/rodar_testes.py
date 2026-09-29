# -*- coding: utf-8 -*-
"""
rodar_testes.py - roda toda a bateria (dados + interface) e resume o resultado.

Uso:
    python scripts/testes/rodar_testes.py            # dados + interface (~4 min)
    python scripts/testes/rodar_testes.py --so-dados # so a conferencia dos dados (~1 min, nao precisa do Edge)
    python scripts/testes/rodar_testes.py --cruzado  # + auditoria cruzada contra as APIs oficiais (~3 min, internet)

Saida da interface (screenshots, colinha.pdf): scripts/testes/saida/
Sai com codigo 1 se algum teste falhar.
"""
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))


def rodar(nome):
    print("=" * 70)
    print(" %s" % nome)
    print("=" * 70)
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(AQUI, nome)], env=env)
    print("(%s: %.0f s)\n" % (nome, time.time() - t0))
    return r.returncode


def main():
    codigos = {"teste_dados.py": rodar("teste_dados.py")}
    if "--so-dados" not in sys.argv:
        codigos["teste_ui.py"] = rodar("teste_ui.py")
    if "--cruzado" in sys.argv:
        codigos["teste_cruzado.py"] = rodar("teste_cruzado.py")
    print("=" * 70)
    for nome, cod in codigos.items():
        print("  %-16s %s" % (nome, "OK" if cod == 0 else "FALHOU"))
    sys.exit(0 if all(c == 0 for c in codigos.values()) else 1)


if __name__ == "__main__":
    main()
