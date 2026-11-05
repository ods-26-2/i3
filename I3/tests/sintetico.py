"""cameras sinteticas: projeta pontos de um plano conhecido para gerar correspondencias exatas"""
import cv2
import numpy as np

from geometria.homografia import Correspondencia


def camera(largura, altura, focal, distancia, altura_camera, inclinacao):
    """camera olhando o plano z = 0 de cima e de lado; devolve (K, rvec, tvec)"""
    K = np.array([[focal, 0, largura / 2], [0, focal, altura / 2], [0, 0, 1.0]])
    return K, np.array([[inclinacao], [0.0], [0.0]]), np.array([[-distancia / 2], [altura_camera], [distancia]])


def correspondencias(pontos_m, K, rvec, tvec):
    proj, _ = cv2.projectPoints(np.array([(x, y, 0.0) for x, y in pontos_m]), rvec, tvec, K, None)
    return [Correspondencia(tuple(map(float, p)), tuple(map(float, m))) for p, m in zip(proj.reshape(-1, 2), pontos_m)]


def csv(pares_ajuste, pares_holdout):
    linhas = ["u,v,x,y,uso,ponto"]
    for uso, pares in (("ajuste", pares_ajuste), ("holdout", pares_holdout)):
        linhas += [f"{c.pixel[0]:.4f},{c.pixel[1]:.4f},{c.mundo[0]},{c.mundo[1]},{uso},p{i}" for i, c in enumerate(pares)]
    return "\n".join(linhas) + "\n"
