"""ferramenta de bancada da quadra de volei: mede as linhas e escreve os cruzamentos como csv

    python I3/ferramentas/medir_linhas.py dados/quadra_mediana.png dados/pontos_quadra.csv > dados/pontos_linhas.csv

o csv de saida esta no formato de entrada do I3 (u,v,x,y,uso,ponto). o procedimento esta em
geometria/quadra_volei.py; o main.py faz o mesmo direto com --linhas.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from geometria.entrada import ler, separar  # noqa: E402
from geometria.quadra_volei import calibrar_por_linhas  # noqa: E402


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    img = cv2.imread(sys.argv[1])
    if img is None:
        raise SystemExit(f"nao consegui abrir a imagem {sys.argv[1]}")
    with open(sys.argv[2], encoding="utf-8") as f:
        pontos = separar(ler(f))
    _, rms, cruzamentos, n = calibrar_por_linhas(img, pontos["ajuste"] + pontos["holdout"])
    print("# medido em " + sys.argv[1] + ": " + ", ".join(f"{k} {v}" for k, v in n.items()), file=sys.stderr)
    print(f"# erro fora do ajuste (tercos de linha): rms {rms:.2f} cm", file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(["u", "v", "x", "y", "uso", "ponto"])
    for c in cruzamentos:
        w.writerow([round(c.pixel[0], 2), round(c.pixel[1], 2), round(c.mundo[0], 3), round(c.mundo[1], 3),
                    "ajuste", "cruzamento"])


if __name__ == "__main__":
    main()
