"""o nucleo: homografia por DLT, erro fora do ajuste e intrinsecos"""
import unittest

import cv2
import numpy as np

from geometria.homografia import Correspondencia, calibrar, erro_reprojecao_cm, pixel_para_mundo
from geometria.intrinsecos import intrinsecos
from tests.sintetico import camera, correspondencias


class Homografia(unittest.TestCase):
    def test_recupera_o_plano_de_uma_camera_conhecida(self):
        K, r, t = camera(1920, 1080, 1400, 30, 6, 1.9)
        pares = correspondencias([(x, y) for x in (0, 10, 20, 30) for y in (0, 10, 20)], K, r, t)
        H = calibrar(pares)
        for c in correspondencias([(4.2, 7.7), (25.1, 18.3)], K, r, t):
            x, y = pixel_para_mundo(H, c.pixel)
            self.assertLess(np.hypot(x - c.mundo[0], y - c.mundo[1]), 1e-3, "erro abaixo de 1 mm")
        self.assertAlmostEqual(H[2, 2], 1.0)

    def test_menos_de_4_pontos_e_erro(self):
        with self.assertRaises(ValueError):
            calibrar([Correspondencia((0, 0), (0, 0))] * 3)

    def test_erro_de_reprojecao_em_centimetros(self):
        H = np.diag([0.01, 0.01, 1.0])                 # 1 px = 1 cm
        self.assertAlmostEqual(erro_reprojecao_cm(H, [Correspondencia((100, 0), (1.03, 0.04))]), 5.0)


class Intrinsecos(unittest.TestCase):
    def test_acha_a_focal_de_uma_camera_conhecida_so_pelos_pontos_do_chao(self):
        K = np.array([[1000.0, 0, 640], [0, 1000.0, 360], [0, 0, 1]])
        rvec, tvec = np.array([[1.9], [0.0], [0.0]]), np.array([[-9.0], [3.0], [16.0]])
        quadra = [(x, y) for x in (0, 6, 9, 12, 18) for y in (0, 9)]
        proj, _ = cv2.projectPoints(np.array([(x, y, 0.0) for x, y in quadra]), rvec, tvec, K, None)
        pares = [Correspondencia(tuple(p), m) for p, m in zip(proj.reshape(-1, 2), quadra)]
        k, d = intrinsecos(pares, 1280, 720)
        self.assertLess(abs(k["fx"] - 1000), 20)
        self.assertEqual((k["cx"], k["cy"], d), (640, 360, [0.0] * 5))


if __name__ == "__main__":
    unittest.main()
