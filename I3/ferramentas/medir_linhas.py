"""ferramenta de bancada: mede as linhas do chao e escreve os cruzamentos como csv

    python I3/ferramentas/medir_linhas.py dados/quadra_mediana.png padroes/quadra-volei-fivb.json \
        --perto "lateral y=0" > dados/pontos_linhas.csv
    python I3/ferramentas/medir_linhas.py dados/quadra_mediana.png padroes/quadra-volei-fivb.json \
        --csv dados/pontos_quadra.csv > dados/pontos_linhas.csv      # partindo dos pontos no olho

o csv de saida esta no formato de entrada do I3 (u,v,x,y,uso,ponto). o procedimento esta em
geometria/linhas.py; o main.py faz o mesmo direto com --linhas.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from geometria.entrada import ler, separar  # noqa: E402
from geometria.linhas import calibrar_por_linhas, padrao  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("imagem")
    p.add_argument("padrao")
    p.add_argument("--perto")
    p.add_argument("--csv")
    a = p.parse_args()
    img = cv2.imread(a.imagem)
    if img is None:
        raise SystemExit(f"nao consegui abrir a imagem {a.imagem}")
    linhas = padrao(json.loads(Path(a.padrao).read_text(encoding="utf-8")))
    iniciais = None
    if a.csv:
        with open(a.csv, encoding="utf-8") as f:
            pontos = separar(ler(f))
        iniciais = pontos["ajuste"] + pontos["holdout"]
    _, rms, cruzamentos, n = calibrar_por_linhas(img, linhas, iniciais, a.perto)
    print("# medido em " + a.imagem + ": " + ", ".join(f"{k} {v}" for k, v in n.items()), file=sys.stderr)
    print(f"# erro fora do ajuste (tercos de linha): rms {rms:.2f} cm", file=sys.stderr)
    w = csv.writer(sys.stdout)
    w.writerow(["u", "v", "x", "y", "uso", "ponto"])
    for c in cruzamentos:
        w.writerow([round(c.pixel[0], 2), round(c.pixel[1], 2), round(c.mundo[0], 3), round(c.mundo[1], 3),
                    "ajuste", "cruzamento"])


if __name__ == "__main__":
    main()
