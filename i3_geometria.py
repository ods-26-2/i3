"""i3 geometria e calibracao -- sprint 2"""
from collections import namedtuple

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
