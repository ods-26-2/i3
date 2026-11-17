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


def imagem_do_chao(padrao, K, rvec, tvec, largura, altura, px_por_m=100, semente=0):
    """o chao com as linhas do padrao pintadas, visto pela camera; devolve (imagem, G mundo -> pixel).

    piso de madeira com ruido, faixas brancas de 5 cm e as distracoes de um ginasio de verdade:
    placa branca grande (logo), faixa escura de outra modalidade e manchas claras soltas"""
    rng = np.random.default_rng(semente)
    pts = np.array([p for seg in padrao.values() for p in seg])
    x0, y0 = pts.min(axis=0) - 3
    x1, y1 = pts.max(axis=0) + 3
    w, h = int((x1 - x0) * px_por_m), int((y1 - y0) * px_por_m)
    tela = np.clip(np.array([110, 160, 200]) + rng.normal(0, 12, (h, w, 3)), 0, 255).astype(np.uint8)

    def px(p):
        return tuple(int(round(c)) for c in ((p[0] - x0) * px_por_m, (p[1] - y0) * px_por_m))

    cx, cy = pts.mean(axis=0)
    cv2.rectangle(tela, px((cx - 2.5, cy - 1.2)), px((cx - 0.5, cy - 0.8)), (245, 245, 245), -1)   # logo
    cv2.line(tela, px((x0 + 1, y0 + 1)), px((x1 - 1, y1 - 2)), (40, 40, 40), 5)                    # outra quadra
    for _ in range(40):
        cv2.circle(tela, px(rng.uniform((x0, y0), (x1, y1))), int(rng.integers(2, 8)), (230, 230, 230), -1)
    for a, b in padrao.values():
        cv2.line(tela, px(a), px(b), (240, 240, 240), max(1, round(0.05 * px_por_m)), cv2.LINE_AA)

    R, _ = cv2.Rodrigues(rvec)
    G = K @ np.column_stack([R[:, 0], R[:, 1], tvec.ravel()])
    T = np.array([[1 / px_por_m, 0, x0], [0, 1 / px_por_m, y0], [0, 0, 1]])
    img = cv2.warpPerspective(tela, G @ T, (largura, altura), borderValue=(60, 60, 60))
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    return img, G / G[2, 2]


def erro_cm(H, G, padrao):
    """rms, em cm, de onde H (pixel -> m) poe as pontas das linhas do padrao vistas pela camera G"""
    mundo = np.array([p for seg in padrao.values() for p in seg] + [(0.0, 0.0)])
    img = (G @ np.column_stack([mundo, np.ones(len(mundo))]).T).T
    volta = (H @ img.T).T
    return 100 * float(np.sqrt(np.mean(np.sum((volta[:, :2] / volta[:, 2:] - mundo) ** 2, axis=1))))


def csv(pares_ajuste, pares_holdout):
    linhas = ["u,v,x,y,uso,ponto"]
    for uso, pares in (("ajuste", pares_ajuste), ("holdout", pares_holdout)):
        linhas += [f"{c.pixel[0]:.4f},{c.pixel[1]:.4f},{c.mundo[0]},{c.mundo[1]},{uso},p{i}" for i, c in enumerate(pares)]
    return "\n".join(linhas) + "\n"
