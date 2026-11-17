"""o procedimento de bancada da quadra do A4, sobre a imagem mediana que esta no repo: regressao
do numero medido (1,43 cm fora do ajuste, card I3.3), nao ajuste; e sem clique, a mesma quadra"""
import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from geometria.entrada import ler, separar
from geometria.intrinsecos import intrinsecos
from geometria.linhas import calibrar_por_linhas, padrao

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "dados"
FIVB = padrao(json.loads((RAIZ / "padroes" / "quadra-volei-fivb.json").read_text(encoding="utf-8")))


class QuadraDoA4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = cv2.imread(str(DADOS / "quadra_mediana.png"))
        with open(DADOS / "pontos_quadra.csv", encoding="utf-8") as f:
            pontos = separar(ler(f))
        cls.manual = calibrar_por_linhas(cls.img, FIVB, iniciais=pontos["ajuste"] + pontos["holdout"])

    def test_linhas_medidas_dao_o_erro_registrado(self):
        _, rms, cruzamentos, medidos = self.manual
        self.assertAlmostEqual(rms, 1.43, delta=0.05)
        self.assertEqual(sum(medidos.values()), 253)
        k, _ = intrinsecos(cruzamentos, self.img.shape[1], self.img.shape[0])
        self.assertAlmostEqual(k["fx"], 769.8, delta=1.0)

    def test_sem_clique_acha_a_mesma_quadra(self):
        H, rms, _, medidos = calibrar_por_linhas(self.img, FIVB, perto="lateral y=0")
        self.assertLess(rms, 1.5, "pelo menos tao bom quanto o da bancada (1,43 cm)")
        self.assertGreater(sum(medidos.values()), 240)
        cantos = np.array([(0, 0, 1), (18, 0, 1), (18, 9, 1), (0, 9, 1)], float).T
        px = [(np.linalg.inv(h) @ cantos)[:2] / (np.linalg.inv(h) @ cantos)[2] for h in (H, self.manual[0])]
        self.assertLess(np.abs(px[0] - px[1]).max(), 1.0, "cantos da quadra a menos de 1 px dos da bancada")


if __name__ == "__main__":
    unittest.main()
