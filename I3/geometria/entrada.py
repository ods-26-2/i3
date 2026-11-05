"""o csv de correspondencias da instalacao: u,v,x,y,uso,ponto

u,v em pixels do quadro bruto; x,y em metros no plano do chao, no referencial da instalacao;
uso e `ajuste` (entra no calculo), `holdout` (so mede o erro) ou `pular` (ocluso). linhas que
comecam com # sao comentario.
"""
import csv
from collections import namedtuple

from geometria.homografia import Correspondencia

Marca = namedtuple("Marca", "correspondencia uso ponto linha")
USOS = ("ajuste", "holdout", "pular")
COLUNAS = ("u", "v", "x", "y", "uso", "ponto")


def ler(linhas):
    """lista de Marca, sem as puladas; ValueError com o numero da linha no que estiver errado"""
    numeradas = [(i, l) for i, l in enumerate(linhas, 1) if not l.lstrip().startswith("#") and l.strip()]
    if not numeradas:
        raise ValueError("csv vazio")
    leitor = csv.DictReader(l for _, l in numeradas)
    faltam = set(COLUNAS) - set(leitor.fieldnames or ())
    if faltam:
        raise ValueError(f"linha {numeradas[0][0]}: faltam as colunas {sorted(faltam)}")
    marcas = []
    for (n, _), r in zip(numeradas[1:], leitor):
        uso = (r["uso"] or "").strip()
        if uso not in USOS:
            raise ValueError(f"linha {n}: uso {uso!r}, esperado um de {USOS}")
        try:
            c = Correspondencia((float(r["u"]), float(r["v"])), (float(r["x"]), float(r["y"])))
        except (TypeError, ValueError):
            raise ValueError(f"linha {n}: u, v, x e y tem que ser numeros") from None
        if uso != "pular":
            marcas.append(Marca(c, uso, (r["ponto"] or "").strip(), n))
    return marcas


def separar(marcas):
    """{"ajuste": [Correspondencia], "holdout": [Correspondencia]}"""
    return {uso: [m.correspondencia for m in marcas if m.uso == uso] for uso in ("ajuste", "holdout")}
