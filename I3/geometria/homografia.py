"""homografia imagem -> plano do chao, a partir de correspondencias medidas na instalacao

e o nucleo generico do I3 (6c: "I3 fornece o procedimento generico"): a quadra do A4, o patio
do A8 ou o galpao do A5 sao so correspondencias diferentes. o plano e o de space_id, em metros.
"""
from collections import namedtuple

import numpy as np

# entrada, pixel em px e mundo em metros no plano do chao
Correspondencia = namedtuple("Correspondencia", "pixel mundo")


def _normalizar_pontos(pontos):
    """normaliza coordenadas 2D para escala media de distancias ~= sqrt(2)."""
    pontos = np.asarray(pontos, dtype=float)
    if pontos.size == 0:
        raise ValueError("precisa de pelo menos um ponto")
    centro = pontos.mean(axis=0)
    deslocados = pontos - centro
    distancias = np.linalg.norm(deslocados, axis=1)
    media = distancias.mean()
    if not np.isfinite(media) or media == 0.0:
        return np.eye(3)
    escala = np.sqrt(2.0) / media
    T = np.array([
        [escala, 0.0, -escala * centro[0]],
        [0.0, escala, -escala * centro[1]],
        [0.0, 0.0, 1.0],
    ], dtype=float)
    return T


def calibrar(correspondencias):
    """homografia imagem -> plano por DLT normalizado.

    A normalizacao evita que o sistema fique mal condicionado quando os pontos estao em escalas
    muito diferentes entre pixel e mundo. O resultado e a homografia de imagem para o plano,
    pronta para `pixel_para_mundo()`.
    """
    if len(correspondencias) < 4:
        raise ValueError("sao necessarias pelo menos 4 correspondencias para calibrar")

    pixels = np.asarray([p for p, _ in correspondencias], dtype=float)
    mundos = np.asarray([m for _, m in correspondencias], dtype=float)

    T_img = _normalizar_pontos(pixels)
    T_mundo = _normalizar_pontos(mundos)

    pixels_h = np.hstack([pixels, np.ones((len(pixels), 1))])
    mundos_h = np.hstack([mundos, np.ones((len(mundos), 1))])

    pixels_norm = pixels_h @ T_img.T
    mundos_norm = mundos_h @ T_mundo.T

    A = []
    for p, P in zip(pixels_norm, mundos_norm):
        u, v, _ = p                                 # origem e o pixel
        X, Y, _ = P                                 # destino e o mundo
        A.append([-u, -v, -1, 0, 0, 0, X * u, X * v, X])
        A.append([0, 0, 0, -u, -v, -1, Y * u, Y * v, Y])

    _, _, Vt = np.linalg.svd(np.asarray(A, dtype=float))
    H_norm = Vt[-1].reshape(3, 3)                   # pixel_norm -> mundo_norm

    H = np.linalg.inv(T_mundo) @ H_norm @ T_img     # desfaz as duas normalizacoes
    H /= H[2, 2]
    return H


def pixel_para_mundo(H, pixel):
    """converte ponto da imagem em ponto do plano"""
    v = H @ np.array([pixel[0], pixel[1], 1.0])
    return tuple(v[:2] / v[2])


def erro_reprojecao_cm(H, correspondencias):
    """erro rms no plano, em centimetros, sobre pontos que nao entraram no ajuste

    o erro nos pontos do ajuste e otimista por construcao; a metrica do I3 e esta, em pontos de
    holdout, junto com o procedimento que os mediu (6c)."""
    erros_m2 = []
    for pixel, mundo in correspondencias:
        u, v = pixel_para_mundo(H, pixel)          # onde a homografia acha que cai
        dx, dy = u - mundo[0], v - mundo[1]         # distancia ate onde cai de verdade
        erros_m2.append(dx * dx + dy * dy)
    return (sum(erros_m2) / len(erros_m2)) ** 0.5 * 100.0
