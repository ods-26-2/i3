"""procedimento de bancada da quadra de volei FIVB (o da camera do A4): mede as linhas da
quadra na imagem, sem clique, e ajusta a homografia que poe cada ponto medido sobre a sua linha

e especifico da quadra: o nucleo generico do I3 e homografia.py com um csv de correspondencias
da instalacao. aqui, os pontos do csv (pontos_quadra.csv, medidos no olho) so dizem onde
procurar. ao longo de cada linha da quadra, a cada PASSO_M, um perfil perpendicular acha o
centro da faixa branca no subpixel (centroide do brilho); com esses pontos, um ajuste poe cada
um sobre o eixo da sua linha (erro ponto-reta) e devolve os cruzamentos das linhas.

geometria FIVB: linha de 5 cm; as de fronteira sao parte da quadra (borda externa em 0 e
18 x 9, eixo 2,5 cm para dentro); a de ataque tem a borda de tras a 3 m do eixo da central.
a imagem deve ser a mediana de varios quadros, sem jogadores. o CLI e ferramentas/medir_linhas.py.
"""
import cv2
import numpy as np

from geometria.homografia import Correspondencia, calibrar

MEIA = 0.025                                         # meia largura da linha, m
LINHAS = {                                           # eixo de cada linha no referencial do i3
    "lateral proxima": ("y", MEIA), "lateral distante": ("y", 9 - MEIA),
    "fundo esquerdo": ("x", MEIA), "fundo direito": ("x", 18 - MEIA),
    "ataque esquerdo": ("x", 6 + MEIA), "ataque direito": ("x", 12 - MEIA),
}
PASSO_M = 0.25
PERFIL_PX = 10                                       # meia largura da busca, perpendicular
CONTRASTE_MIN = 25                                   # faixa branca contra o piso, em niveis


def para_imagem(H_inv, x, y):
    p = H_inv @ np.array([x, y, 1.0])
    return p[:2] / p[2]


def amostras(img, H_inv, nome):
    """centros da faixa branca ao longo de uma linha da quadra"""
    eixo, valor = LINHAS[nome]
    branco = img.min(axis=2).astype(float)            # branco tem os 3 canais altos
    pontos = []
    for s in np.arange(0.3, (18 if eixo == "y" else 9) - 0.3, PASSO_M):
        a = para_imagem(H_inv, *((s, valor) if eixo == "y" else (valor, s)))
        b = para_imagem(H_inv, *((s + 0.1, valor) if eixo == "y" else (valor, s + 0.1)))
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])                   # perpendicular a linha, na imagem
        ks = np.arange(-PERFIL_PX, PERFIL_PX + 0.01, 0.5)
        xs, ys = a[0] + n[0] * ks, a[1] + n[1] * ks
        if xs.min() < 0 or ys.min() < 0 or xs.max() >= img.shape[1] - 1 or ys.max() >= img.shape[0] - 1:
            continue
        perfil = cv2.remap(branco.astype(np.float32), xs.astype(np.float32)[None], ys.astype(np.float32)[None],
                           cv2.INTER_LINEAR)[0]
        fundo = np.median(perfil)
        pico = int(np.argmax(perfil))
        if perfil[pico] - fundo < CONTRASTE_MIN or pico in (0, len(ks) - 1):
            continue                                  # ocluso (poste, logo) ou fora da faixa
        janela = slice(max(pico - 4, 0), pico + 5)
        w = np.clip(perfil[janela] - fundo, 0, None)
        k = float((ks[janela] * w).sum() / w.sum())
        pontos.append(a + n * k)
    return np.array(pontos)


def reta_do_mundo(nome):
    eixo, valor = LINHAS[nome]
    return np.array([0.0, 1.0, -valor]) if eixo == "y" else np.array([1.0, 0.0, -valor])


def corrigir(pts, k1, centro, f):
    """distorcao radial de um termo: pixel bruto -> pixel pinhole (k1 = 0 nao mexe)"""
    d = (pts - centro) / f
    return centro + (pts - centro) * (1 + k1 * (d ** 2).sum(axis=1))[:, None]


def ajustar(medidas, H_px_m, com_k1=False, centro=None, f=None):
    """homografia (pixel -> metro) que poe cada ponto medido sobre a reta da sua linha, em
    metros no chao; levenberg-marquardt a partir da calibracao antiga. com_k1 estima junto um
    termo de distorcao radial (centro e focal fixos). devolve H, k1 e os residuos por linha"""
    def residuos(par, por_linha=False):
        H = np.append(par[:8], 1.0).reshape(3, 3)
        r = {}
        for nome, pts in medidas.items():
            reta = reta_do_mundo(nome)
            q = corrigir(pts, par[8], centro, f) if com_k1 else pts
            m = (H @ np.column_stack([q, np.ones(len(q))]).T).T
            r[nome] = m[:, :2] / m[:, 2:] @ reta[:2] + reta[2]   # distancia (m) do ponto a reta
        return r if por_linha else np.concatenate(list(r.values()))

    par = np.append((H_px_m / H_px_m[2, 2]).ravel()[:8], 0.0 if com_k1 else [])
    passos = np.eye(len(par)) * np.append(np.full(8, 1e-9), [1e-6] if com_k1 else [])
    mu, r = 1e-3, residuos(par)
    for _ in range(100):
        J = np.column_stack([(residuos(par + e) - r) / e.max() for e in passos])
        passo = np.linalg.solve(J.T @ J + mu * np.diag(np.diag(J.T @ J)), -J.T @ r)
        r_novo = residuos(par + passo)
        if r_novo @ r_novo < r @ r:
            par, r, mu = par + passo, r_novo, mu / 3
        else:
            mu *= 5
    return np.append(par[:8], 1.0).reshape(3, 3), (par[8] if com_k1 else 0.0), residuos(par, True)


def ajustar_robusto(medidas, H0, **kw):
    """tira o ponto a mais de 3 desvios (pela mediana) da sua linha -- poste, logo, oclusao --
    e ajusta de novo, ate parar de sair ponto"""
    while True:
        H, k1, r = ajustar(medidas, H0, **kw)
        todos = np.concatenate(list(r.values()))
        limite = max(3 * 1.4826 * np.median(np.abs(todos)), 0.02)
        filtradas = {k: v[np.abs(r[k]) <= limite] for k, v in medidas.items()}
        if sum(map(len, filtradas.values())) == sum(map(len, medidas.values())):
            return H, k1, r, medidas
        medidas = filtradas


def erro_fora_do_ajuste(medidas, H0, **kw):
    """cada linha em tercos; cada terco sai do ajuste por vez e e medido contra a sua reta.
    rms, em cm, de todos os tercos medidos de fora"""
    erros = []
    for nome, pts in medidas.items():
        posicao = np.argsort(np.argsort(pts[:, 0] if abs(pts[-1, 0] - pts[0, 0]) > abs(pts[-1, 1] - pts[0, 1]) else pts[:, 1]))
        for t in range(3):
            fora = (posicao * 3 // len(pts)) == t
            resto = dict(medidas, **{nome: pts[~fora]})
            H, k1, _ = ajustar(resto, H0, **kw)
            q = corrigir(pts[fora], k1, kw["centro"], kw["f"]) if kw.get("com_k1") else pts[fora]
            reta = reta_do_mundo(nome)
            m = (H @ np.column_stack([q, np.ones(len(q))]).T).T
            erros.extend(m[:, :2] / m[:, 2:] @ reta[:2] + reta[2])
    return 100 * float(np.sqrt(np.mean(np.square(erros))))


def cruzamento(H_px_m, a, b):
    """onde as linhas a e b se cruzam, na imagem"""
    l = np.cross(reta_do_mundo(a), reta_do_mundo(b))
    p = np.linalg.inv(H_px_m) @ (l / l[2])
    return p[:2] / p[2], l[:2] / l[2]


def calibrar_por_linhas(img, iniciais):
    """o procedimento inteiro: (H pixel -> m, erro fora do ajuste em cm, cruzamentos medidos
    como Correspondencia, pontos medidos por linha). iniciais so dizem onde procurar

    sem distorcao: a radial de um termo ganhou 0,24 cm no erro fora do ajuste (1,43 -> 1,19)
    na camera do a4, e a 6c pede homografia sobre o pixel bruto, que distorcao nao deixa exata
    """
    H0 = calibrar(iniciais)
    medidas = {nome: amostras(img, np.linalg.inv(H0), nome) for nome in LINHAS}
    medidas = {k: v for k, v in medidas.items() if len(v) >= 6}
    kw = {"centro": np.array([img.shape[1] / 2, img.shape[0] / 2]), "f": float(img.shape[1])}
    H, _, _, medidas = ajustar_robusto(medidas, H0, **kw)
    cruzamentos = []
    for a in ("lateral proxima", "lateral distante"):
        for b in ("fundo esquerdo", "ataque esquerdo", "ataque direito", "fundo direito"):
            if a in medidas and b in medidas:
                (u, v), (x, y) = cruzamento(H, a, b)
                cruzamentos.append(Correspondencia((float(u), float(v)), (float(x), float(y))))
    return H / H[2, 2], erro_fora_do_ajuste(medidas, H0, **kw), cruzamentos, {k: len(v) for k, v in medidas.items()}

