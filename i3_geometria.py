"""i3 geometria e calibracao -- sprint 2"""
from collections import namedtuple

import cv2
import numpy as np

# entrada, pixel em px e mundo em metros
Correspondencia = namedtuple("Correspondencia", "pixel mundo")

# saida
Referencial = namedtuple("Referencial", "origem eixos unidade")
Calibracao = namedtuple("Calibracao",
                        "camera_id homografia referencial rms_cm valido_desde versao")


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
    """calcula uma imagem -> plano por DLT normalizado.

    A normalizacao evita que o sistema fique mal condicionado quando os pontos
    estao em escalas muito diferentes entre pixel e mundo. O resultado final e a
    homografia de imagem para o plano, pronta para `pixel_para_mundo()`.

    card I3.2 · calculo da homografia -- sprint 2, etapa 7 (Diego, apoio Jose)
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


def calibrar_com_holdout(correspondencias, n_holdout=2):
    """calibra com ajuste e mede o RMS em cm no holdout.

    O README pede 8 correspondencias, com 6 para ajuste e 2 para validacao. O
    retorno e composto por: homografia, rms_cm, ajuste e holdout.
    """
    lista = list(correspondencias)
    if len(lista) < 4:
        raise ValueError("sao necessarias pelo menos 4 correspondencias")
    if n_holdout < 1:
        raise ValueError("n_holdout precisa ser >= 1")
    if len(lista) <= n_holdout:
        raise ValueError("precisa haver mais correspondencias do que o numero de holdout")

    ajuste = lista[:-n_holdout]
    holdout = lista[-n_holdout:]
    H = calibrar(ajuste)
    rms_cm = erro_reprojecao_cm(H, holdout) if holdout else float("nan")
    return H, rms_cm, ajuste, holdout


def intrinsecos(correspondencias, largura, altura):
    """focal da camera a partir dos pontos da quadra; centro otico e distorcao fixos

    card A4.0b · intrinsecos obrigatorios da 6c -- sprint 3 (Jose)
    """
    # ponytail: uma vista so do plano da quadra, entao so a focal e estimavel; centro no
    # meio e distorcao zero. na jetson a lente e fixa: calibrar uma vez com tabuleiro
    # (varias vistas) e ler o resultado em vez de estimar aqui
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


def pixel_para_mundo(H, pixel):
    """converte ponto da imagem em ponto do plano
    card I3.2 · conversao pixel -> quadra -- sprint 2, etapa 8 (Jose)
    """
    v = H @ np.array([pixel[0], pixel[1], 1.0])
    return tuple(v[:2] / v[2])


def erro_reprojecao_cm(H, correspondencias):
    """erro medio no plano em centimetros, sobre pontos que nao entraram no ajuste

    card I3.3 · metrica erro de reprojecao -- sprint 2, etapa 9 (Diego)
    falta: o procedimento de bancada documentado junto do numero
    """
    erros_m2 = []
    for pixel, mundo in correspondencias:
        u, v = pixel_para_mundo(H, pixel)          # onde a homografia acha que cai
        dx, dy = u - mundo[0], v - mundo[1]         # distancia ate onde cai de verdade
        erros_m2.append(dx * dx + dy * dy)          # erro daquele ponto, ao quadrado
    media_m2 = sum(erros_m2) / len(erros_m2)        # media dos erros ao quadrado
    return media_m2 ** 0.5 * 100.0                  # raiz volta pra metro, x100 vira cm


def publicar(camera_id, H, rms_cm, referencial, valido_desde, versao):
    """monta o artefato de calibracao

    card I3.1 · calibracao inicial, versionar artefato -- sprint 2, etapa 6 (Diego)
    falta: etapa 2 do passo a passo -- parametros intrinsecos de lente/sensor; o artefato
    so leva homografia, e P4 espera os intrinsecos pra corrigir distorcao
    falta: etapa 10 -- publicar coordenadas da quadra no esquema de B1
    """
    return Calibracao(camera_id, H, referencial, round(rms_cm, 2), valido_desde, versao)


def publicar_artefato(camera_id, correspondencias, referencial, valido_desde, versao, n_holdout=2):
    """calibra com ajuste + holdout e publica o artefato completo do README."""
    H, rms_cm, _, _ = calibrar_com_holdout(correspondencias, n_holdout=n_holdout)
    return publicar(camera_id, H, rms_cm, referencial, valido_desde, versao)


if __name__ == "__main__":
    # camera conhecida (f = 1000, 1280x720) olhando a quadra de cima e de lado:
    # intrinsecos tem que achar a mesma focal a partir so dos pontos projetados
    K = np.array([[1000.0, 0, 640], [0, 1000.0, 360], [0, 0, 1]])
    rvec, tvec = np.array([[1.9], [0.0], [0.0]]), np.array([[-9.0], [3.0], [16.0]])
    quadra = [(x, y) for x in (0, 6, 9, 12, 18) for y in (0, 9)]
    proj, _ = cv2.projectPoints(np.array([(x, y, 0.0) for x, y in quadra]), rvec, tvec, K, None)
    pares = [Correspondencia(tuple(p), m) for p, m in zip(proj.reshape(-1, 2), quadra)]
    k, d = intrinsecos(pares, 1280, 720)
    assert abs(k["fx"] - 1000) < 20, k
    assert (k["cx"], k["cy"], d) == (640, 360, [0.0] * 5), (k, d)
    print("intrinsecos ok")
