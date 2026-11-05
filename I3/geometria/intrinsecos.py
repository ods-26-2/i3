"""intrinsecos e distorcao, campos obrigatorios do CALIBRATION na 6c (o P4 entrega o quadro
bruto, e quem mede fora do chao corrige as coordenadas com eles)"""
import cv2
import numpy as np


def intrinsecos(correspondencias, largura, altura):
    """focal da camera a partir dos pontos do plano; centro otico e distorcao fixos"""
    # ponytail: uma vista so do plano, entao so a focal e estimavel; centro no meio e distorcao
    # zero. na jetson a lente e fixa: calibrar uma vez com tabuleiro (varias vistas) e ler o
    # resultado em vez de estimar aqui
    mundo = np.array([[(x, y, 0.0) for _, (x, y) in correspondencias]], np.float32)
    pixel = np.array([[p for p, _ in correspondencias]], np.float32)
    K0 = np.array([[largura, 0, largura / 2], [0, largura, altura / 2], [0, 0, 1]], float)
    fixo = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT
            | cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_ZERO_TANGENT_DIST
            | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3)
    _, K, dist, _, _ = cv2.calibrateCamera(mundo, pixel, (largura, altura), K0, None, flags=fixo)
    return ({"fx": round(K[0, 0], 1), "fy": round(K[1, 1], 1),
             "cx": round(K[0, 2], 1), "cy": round(K[1, 2], 1)},
            [round(float(c), 6) for c in dist.ravel()[:5]])
