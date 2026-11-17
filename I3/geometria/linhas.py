"""calibracao pelas linhas pintadas no chao, para qualquer instalacao: o padrao e o desenho das
linhas em metros, arquivo da instalacao (padroes/quadra-volei-fivb.json, as vagas de um patio);
a imagem e o chao sem gente (mediana de varios quadros). sem clique:

1. as faixas claras e finas da imagem (top-hat; placa e logo, maiores, somem) viram retas (hough);
2. cada hipotese leva 2 retas da imagem a 2 linhas de uma direcao do padrao e 2 a outra; os 4
   cruzamentos dao a homografia, que vale pelo quanto do padrao projetado cai sobre faixa;
3. a camera esta acima do chao, entao o referencial (destro, z para cima) nunca aparece
   espelhado. padrao simetrico (a quadra) aparece de dois jeitos: a instalacao diz qual linha
   fica mais perto da camera (perto);
4. ao longo de cada linha, a cada PASSO_M, um perfil perpendicular acha o centro da faixa no
   subpixel (centroide do brilho), e levenberg-marquardt poe cada ponto sobre a sua reta.

com pontos medidos no olho (csv), eles substituem os passos 1 a 3 como chute. a faixa e branca:
o que tem os 3 canais altos.
"""
import itertools

import cv2
import numpy as np

from geometria.homografia import Correspondencia, calibrar

PASSO_M = 0.25
PERFIL_PX = 10                                       # meia largura da busca, perpendicular
CONTRASTE_MIN = 25                                   # faixa branca contra o piso, em niveis
TOPHAT_PX = 15                                       # faixa mais fina que isso e linha
RETAS_MAX = 16                                       # os trechos mais compridos viram hipotese
VOTOS_MIN = 40                                       # pixels de faixa no trecho
TRECHO_MIN_PX = 60                                   # trecho continuo mais curto que conta
FALHA_PX = 3                                         # buraco que ainda e o mesmo trecho
FAIXA_PX = 8                                         # meia largura da faixa na imagem, perto da camera
LOTE = 20000                                         # hipoteses por vez na nota (memoria)
TOL_PX = 2.0                                         # amostra do padrao "sobre a faixa"
NOTA_MIN = 0.5                                       # fracao do padrao que tem que cair em faixa
EMPATE = 0.95                                        # outra solucao com essa nota e o mesmo desenho
POR_LINHA = 40                                       # amostras de cada linha do padrao, para a nota
COMPRIMENTO_MIN_PX = 20                              # linha do padrao menor que isso na imagem: degenerada


def padrao(dados):
    """{nome: (de, ate)} a partir do json da instalacao; recusa o que nao fixa a homografia"""
    linhas = {l["nome"]: (tuple(map(float, l["de"])), tuple(map(float, l["ate"]))) for l in dados["linhas"]}
    if len(linhas) != len(dados["linhas"]):
        raise ValueError("nome de linha repetido no padrao")
    if sum(len(f) >= 2 for f in familias(linhas)) < 2:
        raise ValueError("o padrao precisa de 2 linhas em cada uma de pelo menos duas direcoes")
    return linhas


def familias(linhas):
    """nomes agrupados por direcao (linhas paralelas no chao)"""
    grupos = []
    for nome, ((x0, y0), (x1, y1)) in linhas.items():
        a = np.arctan2(y1 - y0, x1 - x0) % np.pi
        for g in grupos:
            d = abs(a - g[0])
            if min(d, np.pi - d) < np.radians(1):
                g[1].append(nome)
                break
        else:
            grupos.append((a, [nome]))
    return [g[1] for g in grupos]


def reta(seg):
    """reta homogenea do segmento, com a normal unitaria: reta @ (x, y, 1) e a distancia em m"""
    l = np.cross([*seg[0], 1.0], [*seg[1], 1.0])
    return l / np.linalg.norm(l[:2])


def para_imagem(H_inv, x, y):
    p = H_inv @ np.array([x, y, 1.0])
    return p[:2] / p[2]


def amostras(branco, H_inv, seg):
    """centros da faixa branca ao longo de uma linha do padrao"""
    p0, p1 = np.array(seg[0]), np.array(seg[1])
    comprimento = np.linalg.norm(p1 - p0)
    direcao = (p1 - p0) / comprimento
    pontos = []
    for s in np.arange(0.3, comprimento - 0.3, PASSO_M):
        a = para_imagem(H_inv, *(p0 + s * direcao))
        b = para_imagem(H_inv, *(p0 + (s + 0.1) * direcao))
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])                   # perpendicular a linha, na imagem
        ks = np.arange(-PERFIL_PX, PERFIL_PX + 0.01, 0.5)
        xs, ys = a[0] + n[0] * ks, a[1] + n[1] * ks
        if xs.min() < 0 or ys.min() < 0 or xs.max() >= branco.shape[1] - 1 or ys.max() >= branco.shape[0] - 1:
            continue
        perfil = cv2.remap(branco, xs.astype(np.float32)[None], ys.astype(np.float32)[None], cv2.INTER_LINEAR)[0]
        fundo = np.median(perfil)
        pico = int(np.argmax(perfil))
        if perfil[pico] - fundo < CONTRASTE_MIN or pico in (0, len(ks) - 1):
            continue                                  # ocluso (poste, logo) ou fora da faixa
        janela = slice(max(pico - 4, 0), pico + 5)
        w = np.clip(perfil[janela] - fundo, 0, None)
        k = float((ks[janela] * w).sum() / w.sum())
        pontos.append(a + n * k)
    return np.array(pontos)


def retas_da_imagem(branco):
    """as faixas claras e finas como retas homogeneas (normal unitaria) e a distancia de cada
    pixel a faixa mais perto, para dar nota as hipoteses.

    as retas vem dos trechos continuos de faixa, do mais comprido para o mais curto: pintura e
    traco continuo, e arquibancada, telhado e painel espalham pixel claro em pedacos"""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (TOPHAT_PX, TOPHAT_PX))
    faixa = (cv2.morphologyEx(branco.astype(np.uint8), cv2.MORPH_TOPHAT, kernel) > CONTRASTE_MIN).astype(np.uint8)
    distancia = cv2.distanceTransform(1 - faixa, cv2.DIST_L2, 3)
    trechos = cv2.HoughLinesP(faixa * 255, 1, np.pi / 360, VOTOS_MIN, minLineLength=TRECHO_MIN_PX,
                              maxLineGap=FALHA_PX)
    trechos = np.zeros((0, 4)) if trechos is None else trechos.reshape(-1, 4).astype(float)
    trechos = trechos[np.argsort(-np.hypot(trechos[:, 2] - trechos[:, 0], trechos[:, 3] - trechos[:, 1]))]
    ys, xs = np.nonzero(faixa)
    pixels = np.column_stack([xs, ys, np.ones(len(xs))])
    retas = []
    for x0, y0, x1, y1 in trechos:
        pontas = np.array([[x0, y0, 1.0], [x1, y1, 1.0]])
        if any(np.abs(pontas @ k).max() < FAIXA_PX for k in retas):
            continue                                  # outro pedaco de uma faixa ja achada
        l = np.cross(*pontas)
        l /= np.linalg.norm(l[:2])
        ao_longo = pixels[:, :2] @ [-l[1], l[0]]
        t0, t1 = sorted(pontas[:, :2] @ [-l[1], l[0]])
        apoio = pixels[(np.abs(pixels @ l) <= 3) & (ao_longo >= t0) & (ao_longo <= t1), :2]
        centro = apoio.mean(axis=0)                   # o hough erra ate meio grau: ajusta aos pixels
        normal = np.linalg.svd(apoio - centro)[2][1]
        retas.append(np.array([*normal, -normal @ centro]))
        if len(retas) == RETAS_MAX:
            break
    return np.array(retas), distancia


def giro(quadrilatero):
    """+1 ou -1 conforme o sentido do quadrilatero (n, 4, 2) convexo; 0 se nao e convexo"""
    lados = np.roll(quadrilatero, -1, axis=1) - quadrilatero
    z = lados[..., 0] * np.roll(lados, -1, axis=1)[..., 1] - lados[..., 1] * np.roll(lados, -1, axis=1)[..., 0]
    return np.where((z > 0).all(axis=1), 1, np.where((z < 0).all(axis=1), -1, 0))


def homografias(origem, destino):
    """lote de homografias de 4 pontos (n, 4, 2) -> (n, 4, 2); None onde a conta degenera"""
    x, y = origem[..., 0], origem[..., 1]
    u, v = destino[..., 0], destino[..., 1]
    zero, um = np.zeros_like(x), np.ones_like(x)
    A = np.concatenate([np.stack([x, y, um, zero, zero, zero, -u * x, -u * y], -1),
                        np.stack([zero, zero, zero, x, y, um, -v * x, -v * y], -1)], axis=1)
    b = np.concatenate([u, v], axis=1)
    ok = np.abs(np.linalg.det(A)) > 1e-9
    h = np.linalg.solve(A[ok], b[ok][..., None])[..., 0]
    return np.concatenate([h, np.ones((len(h), 1))], axis=1).reshape(-1, 3, 3), ok


def procurar(branco, linhas, perto=None):
    """acha o padrao na imagem; devolve a homografia pixel -> m, so para comecar o ajuste"""
    retas_img, distancia = retas_da_imagem(branco)
    altura, largura = branco.shape
    if len(retas_img) < 4:
        raise ValueError("nao achei faixas suficientes na imagem; o chao precisa aparecer sem gente")
    # escala ~1 nas duas pontas, para a conta de 4 pontos nao degenerar
    escala_px, escala_m = float(largura), float(np.ptp(np.array([p for s in linhas.values() for p in s])))
    nomes = list(linhas)
    retas_m = np.array([reta(linhas[n]) for n in nomes])
    amostra = np.array([(*(np.array(a) + s * (np.array(b) - np.array(a))), 1.0)
                        for a, b in linhas.values() for s in np.linspace(0, 1, POR_LINHA)])
    centro = amostra.mean(axis=0)

    def cruz(l1, l2):
        p = np.cross(l1, l2)
        return p[..., :2] / p[..., 2:]

    with np.errstate(divide="ignore", invalid="ignore"):
        cruz_img = cruz(retas_img[:, None], retas_img[None, :]) / escala_px
    quadras = np.array(list(itertools.permutations(range(len(retas_img)), 4)))
    a, b, c, d = quadras.T
    # os 4 cruzamentos em volta do quadrilatero: a com c, a com d, b com d, b com c
    img4 = np.stack([cruz_img[a, c], cruz_img[a, d], cruz_img[b, d], cruz_img[b, c]], axis=1)
    noimg = np.isfinite(img4).all(axis=(1, 2)) & (np.abs(img4 - 0.5) < 1.5).all(axis=(1, 2))
    giro_img = np.zeros(len(img4), int)
    giro_img[noimg] = giro(img4[noimg])

    candidatas = []                                   # (nota, G mundo -> pixel)
    todas = familias(linhas)
    grupos = [i for i, f in enumerate(todas) if len(f) >= 2]
    for f1, f2 in itertools.combinations(grupos, 2):
        for (p, q), (r, s) in itertools.product(itertools.combinations(todas[f1], 2),
                                                itertools.combinations(todas[f2], 2)):
            i = [nomes.index(n) for n in (p, q, r, s)]
            m4 = np.stack([cruz(retas_m[i[0]], retas_m[i[2]]), cruz(retas_m[i[0]], retas_m[i[3]]),
                           cruz(retas_m[i[1]], retas_m[i[3]]), cruz(retas_m[i[1]], retas_m[i[2]])]) / escala_m
            # o retangulo do chao visto de cima aparece convexo e girando ao contrario (imagem de v
            # para baixo): o resto das combinacoes nem vira homografia
            sel = giro_img == -giro(m4[None])[0]
            for lote in np.array_split(np.nonzero(sel)[0], max(1, sel.sum() // LOTE)):
                G, _ = homografias(np.broadcast_to(m4, (len(lote), 4, 2)), img4[lote])
                G = np.diag([escala_px, escala_px, 1.0]) @ G @ np.diag([1 / escala_m, 1 / escala_m, 1.0])
                candidatas += [(n, g) for n, g in zip(nota(G, amostra, centro, distancia), G) if n > 0]
    if not candidatas or max(n for n, _ in candidatas) < NOTA_MIN:
        raise ValueError("nao achei o padrao na imagem: confira o arquivo do padrao e se o chao aparece")
    return np.linalg.inv(escolher(candidatas, linhas, perto))


def nota(G, amostra, centro, distancia):
    """fracao do padrao projetado que cai sobre faixa; 0 para o desenho espelhado (camera embaixo
    do chao), cortado pelo horizonte ou degenerado"""
    w = (G @ centro)[:, 2]
    G = G * np.sign(w)[:, None, None]
    q = np.einsum("nij,sj->nsi", G, amostra)
    frente = (q[..., 2] > 0).all(axis=1)
    uv = q[..., :2] / np.where(q[..., 2:] > 0, q[..., 2:], 1)
    altura, largura = distancia.shape
    u, v = np.round(uv[..., 0]).astype(int), np.round(uv[..., 1]).astype(int)
    dentro = (u >= 0) & (u < largura) & (v >= 0) & (v < altura)
    perto = np.zeros(u.shape, bool)
    perto[dentro] = distancia[v[dentro], u[dentro]] <= TOL_PX
    # jacobiano no centro: com o referencial destro e a imagem de v para baixo, a camera acima
    # do chao ve o determinante negativo
    qc = G @ centro
    J = (G[:, :2, :2] * qc[:, 2, None, None] - qc[:, :2, None] * G[:, 2, None, :2])
    destro = np.linalg.det(J) < 0
    # camera de verdade nao encolhe uma linha inteira num ponto; a hipotese degenerada achata o
    # padrao sobre uma faixa so e acerta quase toda amostra
    comprimento = np.linalg.norm(uv[:, POR_LINHA - 1::POR_LINHA] - uv[:, ::POR_LINHA], axis=2).min(axis=1)
    return np.where(frente & destro & (comprimento >= COMPRIMENTO_MIN_PX), perto.mean(axis=1), 0.0)


def escolher(candidatas, linhas, perto):
    """a melhor hipotese; se o padrao e simetrico, a que poe a linha `perto` mais baixa na imagem"""
    melhor = max(n for n, _ in candidatas)
    pontas = np.array([(*p, 1.0) for s in linhas.values() for p in s])
    solucoes = []                                     # (nota, G), uma por desenho distinto
    for n, G in sorted(candidatas, key=lambda c: -c[0]):
        if n < EMPATE * melhor:
            break
        q = (G @ pontas.T).T
        px = q[:, :2] / q[:, 2:]
        if all(np.abs(px - s[2]).max() > 5 for s in solucoes):
            solucoes.append((n, G, px))
    if len(solucoes) > 1:
        if perto is None:
            raise ValueError("o padrao aparece de mais de um jeito na imagem (e simetrico): diga com --perto "
                             "qual linha do padrao fica mais perto da camera")
        meio = np.array([(*np.mean(linhas[perto], axis=0), 1.0)])
        return max(solucoes, key=lambda s: (s[1] @ meio.T)[1, 0] / (s[1] @ meio.T)[2, 0])[1]
    return solucoes[0][1]


def corrigir(pts, k1, centro, f):
    """distorcao radial de um termo: pixel bruto -> pixel pinhole (k1 = 0 nao mexe)"""
    d = (pts - centro) / f
    return centro + (pts - centro) * (1 + k1 * (d ** 2).sum(axis=1))[:, None]


def ajustar(medidas, H_px_m, retas, com_k1=False, centro=None, f=None):
    """homografia (pixel -> metro) que poe cada ponto medido sobre a reta da sua linha, em
    metros no chao; levenberg-marquardt a partir do chute. com_k1 estima junto um termo de
    distorcao radial (centro e focal fixos). devolve H, k1 e os residuos por linha"""
    def residuos(par, por_linha=False):
        H = np.append(par[:8], 1.0).reshape(3, 3)
        r = {}
        for nome, pts in medidas.items():
            q = corrigir(pts, par[8], centro, f) if com_k1 else pts
            m = (H @ np.column_stack([q, np.ones(len(q))]).T).T
            r[nome] = m[:, :2] / m[:, 2:] @ retas[nome][:2] + retas[nome][2]   # distancia (m) a reta
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


def ajustar_robusto(medidas, H0, retas, **kw):
    """tira o ponto a mais de 3 desvios (pela mediana) da sua linha -- poste, logo, oclusao --
    e ajusta de novo, ate parar de sair ponto"""
    while True:
        H, k1, r = ajustar(medidas, H0, retas, **kw)
        todos = np.concatenate(list(r.values()))
        limite = max(3 * 1.4826 * np.median(np.abs(todos)), 0.02)
        filtradas = {k: v[np.abs(r[k]) <= limite] for k, v in medidas.items()}
        if sum(map(len, filtradas.values())) == sum(map(len, medidas.values())):
            return H, k1, r, medidas
        medidas = filtradas


def erro_fora_do_ajuste(medidas, H0, retas, **kw):
    """cada linha em tercos; cada terco sai do ajuste por vez e e medido contra a sua reta.
    rms, em cm, de todos os tercos medidos de fora"""
    erros = []
    for nome, pts in medidas.items():
        posicao = np.argsort(np.argsort(pts[:, 0] if abs(pts[-1, 0] - pts[0, 0]) > abs(pts[-1, 1] - pts[0, 1]) else pts[:, 1]))
        for t in range(3):
            fora = (posicao * 3 // len(pts)) == t
            resto = dict(medidas, **{nome: pts[~fora]})
            H, k1, _ = ajustar(resto, H0, retas, **kw)
            q = corrigir(pts[fora], k1, kw["centro"], kw["f"]) if kw.get("com_k1") else pts[fora]
            m = (H @ np.column_stack([q, np.ones(len(q))]).T).T
            erros.extend(m[:, :2] / m[:, 2:] @ retas[nome][:2] + retas[nome][2])
    return 100 * float(np.sqrt(np.mean(np.square(erros))))


def cruzamentos(H_px_m, linhas, medidas):
    """onde duas linhas medidas se cruzam dentro dos dois segmentos: na imagem e no chao"""
    saida = []
    for a, b in itertools.combinations([n for n in linhas if n in medidas], 2):
        p = np.cross(reta(linhas[a]), reta(linhas[b]))
        if abs(p[2]) < 1e-12:
            continue                                  # paralelas
        x, y = p[:2] / p[2]
        if all(min(s[0][k], s[1][k]) - 0.1 <= (x, y)[k] <= max(s[0][k], s[1][k]) + 0.1
               for s in (linhas[a], linhas[b]) for k in (0, 1)):
            u, v = para_imagem(np.linalg.inv(H_px_m), x, y)
            saida.append(Correspondencia((float(u), float(v)), (float(x), float(y))))
    return saida


def calibrar_por_linhas(img, linhas, iniciais=None, perto=None):
    """o procedimento inteiro: (H pixel -> m, erro fora do ajuste em cm, cruzamentos medidos
    como Correspondencia, pontos medidos por linha). iniciais (pontos do csv) so dizem onde
    procurar; sem eles, o I3 acha o padrao sozinho

    sem distorcao: a radial de um termo ganhou 0,24 cm no erro fora do ajuste (1,43 -> 1,19)
    na camera do a4, e a 6c pede homografia sobre o pixel bruto, que distorcao nao deixa exata
    """
    if perto is not None and perto not in linhas:
        raise ValueError(f"--perto {perto!r} nao e linha do padrao; as linhas sao: {', '.join(linhas)}")
    branco = img.min(axis=2).astype(np.float32)       # branco tem os 3 canais altos
    H0 = calibrar(iniciais) if iniciais else procurar(branco, linhas, perto)
    medidas = {nome: amostras(branco, np.linalg.inv(H0), seg) for nome, seg in linhas.items()}
    medidas = {k: v for k, v in medidas.items() if len(v) >= 6}
    retas = {nome: reta(seg) for nome, seg in linhas.items()}
    kw = {"centro": np.array([img.shape[1] / 2, img.shape[0] / 2]), "f": float(img.shape[1])}
    H, _, _, medidas = ajustar_robusto(medidas, H0, retas, **kw)
    return (H / H[2, 2], erro_fora_do_ajuste(medidas, H0, retas, **kw), cruzamentos(H, linhas, medidas),
            {k: len(v) for k, v in medidas.items()})
