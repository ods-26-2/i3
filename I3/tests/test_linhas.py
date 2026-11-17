"""calibracao pelas linhas pintadas no chao, sem clique: o padrao das linhas e da instalacao
(quadra FIVB, vagas de estacionamento), a busca e o ajuste sao do I3"""
import json
import unittest
from pathlib import Path

import numpy as np

from geometria.linhas import calibrar_por_linhas, padrao
from tests.sintetico import camera, erro_cm, imagem_do_chao

RAIZ = Path(__file__).resolve().parents[2]
FIVB = padrao(json.loads((RAIZ / "padroes" / "quadra-volei-fivb.json").read_text(encoding="utf-8")))
VAGAS = padrao({"nome": "6 vagas de 2,5 x 5 m", "linhas": [
    {"nome": "meio-fio", "de": [0, 0], "ate": [15, 0]},
    {"nome": "fundo", "de": [0, 5], "ate": [15, 5]},
    *[{"nome": f"divisoria x={x:g}", "de": [x, 0], "ate": [x, 5]} for x in np.arange(0, 15.1, 2.5)]]})
QUADRA = (camera(1280, 720, 1000, 18, 3, 1.9), 1280, 720)
PATIO = (camera(1920, 1080, 1100, 15, 6, 2.0), 1920, 1080)


def ver(padrao_, cena):
    (K, rvec, tvec), largura, altura = cena
    return imagem_do_chao(padrao_, K, rvec, tvec, largura, altura)


class SemClique(unittest.TestCase):
    def test_quadra_sintetica(self):
        img, G = ver(FIVB, QUADRA)
        H, rms, cruzamentos, _ = calibrar_por_linhas(img, FIVB, perto="lateral y=0")
        self.assertLess(erro_cm(H, G, FIVB), 2.0)
        self.assertLess(rms, 2.0)
        self.assertEqual(len(cruzamentos), 8, "as 2 laterais cruzam os 2 fundos e as 2 de ataque")

    def test_vagas_sinteticas(self):
        img, G = ver(VAGAS, PATIO)
        H, _, _, _ = calibrar_por_linhas(img, VAGAS, perto="meio-fio")
        self.assertLess(erro_cm(H, G, VAGAS), 2.0)

    def test_padrao_simetrico_sem_perto_e_ambiguo(self):
        img, _ = ver(FIVB, QUADRA)
        with self.assertRaisesRegex(ValueError, "--perto"):
            calibrar_por_linhas(img, FIVB)

    def test_imagem_sem_as_linhas_e_recusada(self):
        img, _ = ver(FIVB, QUADRA)
        with self.assertRaisesRegex(ValueError, "nao achei"):
            calibrar_por_linhas(np.full_like(img, 120), FIVB, perto="lateral y=0")


class Padrao(unittest.TestCase):
    def test_linhas_de_uma_direcao_so_sao_recusadas(self):
        with self.assertRaisesRegex(ValueError, "duas direcoes"):
            padrao({"nome": "x", "linhas": [{"nome": "a", "de": [0, 0], "ate": [5, 0]},
                                            {"nome": "b", "de": [0, 1], "ate": [5, 1]}]})

    def test_perto_tem_que_ser_linha_do_padrao(self):
        img, _ = ver(FIVB, QUADRA)
        with self.assertRaisesRegex(ValueError, "lateral proxima"):
            calibrar_por_linhas(img, FIVB, perto="lateral proxima")


if __name__ == "__main__":
    unittest.main()
