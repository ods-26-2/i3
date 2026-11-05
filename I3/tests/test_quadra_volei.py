"""o procedimento de bancada da quadra do A4, sobre a imagem mediana que esta no repo: regressao
do numero medido (1,43 cm fora do ajuste, card I3.3), nao ajuste"""
import unittest
from pathlib import Path

import cv2

from geometria.entrada import ler, separar
from geometria.intrinsecos import intrinsecos
from geometria.quadra_volei import calibrar_por_linhas

DADOS = Path(__file__).resolve().parents[2] / "dados"


class QuadraDoA4(unittest.TestCase):
    def test_linhas_medidas_dao_o_erro_registrado(self):
        img = cv2.imread(str(DADOS / "quadra_mediana.png"))
        with open(DADOS / "pontos_quadra.csv", encoding="utf-8") as f:
            pontos = separar(ler(f))
        _, rms, cruzamentos, medidos = calibrar_por_linhas(img, pontos["ajuste"] + pontos["holdout"])
        self.assertAlmostEqual(rms, 1.43, delta=0.05)
        self.assertEqual(sum(medidos.values()), 253)
        k, _ = intrinsecos(cruzamentos, img.shape[1], img.shape[0])
        self.assertAlmostEqual(k["fx"], 769.8, delta=1.0)


if __name__ == "__main__":
    unittest.main()
