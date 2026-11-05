"""o I3 calibra a camera de qualquer aplicacao que a 6c calibra na 1.0 (A4, A8 e A5): so mudam as
correspondencias e o referencial da instalacao"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

from geometria import contrato
from geometria.homografia import pixel_para_mundo
from tests.sintetico import camera, correspondencias, csv

RAIZ = Path(__file__).resolve().parents[2]

INSTALACOES = {
    # nome: (largura x comprimento do plano em m, camera, space_id, origem, eixos)
    "patio do A8": ((30, 20), camera(1920, 1080, 1400, 30, 6, 1.9), "patio-1",
                    "canto sudoeste do patio", "x ao longo da rua, y para o fundo"),
    "galpao do A5": ((12, 8), camera(1280, 720, 900, 12, 3, 2.0), "galpao-1",
                     "pilar A1", "x ao longo das bancadas, y para a parede norte"),
    "quadra do A4": ((18, 9), camera(1280, 720, 1000, 18, 3, 1.9), "quadra-volei-fivb",
                     "canto proximo esquerdo", "x ao longo dos 18 m, y afastando da camera"),
}


class Instalacoes(unittest.TestCase):
    def test_cada_instalacao_da_calibracao_valida_com_o_seu_referencial(self):
        for nome, ((lx, ly), (K, r, t), espaco, origem, eixos) in INSTALACOES.items():
            with self.subTest(nome):
                grade = [(x * lx / 4, y * ly / 3) for x in range(5) for y in range(4)]
                ajuste = correspondencias(grade, K, r, t)
                holdout = correspondencias([(lx * 0.31, ly * 0.47), (lx * 0.77, ly * 0.12)], K, r, t)
                saida = subprocess.run(
                    [sys.executable, str(RAIZ / "main.py"), "--source-id", "camx", "--largura", str(int(K[0, 2] * 2)),
                     "--altura", str(int(K[1, 2] * 2)), "--espaco", espaco, "--origem", origem, "--eixos", eixos],
                    input=csv(ajuste, holdout), text=True, capture_output=True, timeout=60)
                self.assertEqual(saida.returncode, 0, saida.stderr)
                ev = json.loads(saida.stdout)
                self.assertEqual(contrato.erros(ev), [])
                p = ev["payload"]
                self.assertEqual(p["reference_frame"], {"space_id": espaco, "origin": origem, "axes": eixos})
                self.assertLess(p["reprojection_rms_cm"], 1.0, "pontos exatos: erro so de arredondamento")
                self.assertEqual(p["holdout_points"], 2)
                x, y = pixel_para_mundo(np.array(p["homography_px_to_m"]), holdout[0].pixel)
                self.assertAlmostEqual(x, holdout[0].mundo[0], places=2)
                self.assertAlmostEqual(y, holdout[0].mundo[1], places=2)


if __name__ == "__main__":
    unittest.main()
