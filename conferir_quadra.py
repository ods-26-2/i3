"""laco de marcacao do i3: desenha a quadra de volta em cima da foto

le dados/pontos_quadra.csv, calibra com o i3 e reprojeta as linhas conhecidas
da quadra sobre a imagem. se as linhas desenhadas caem em cima das pintadas, a
marcacao esta boa; onde escorregam, voce ve quanto e onde -- coisa que um
rms_cm sozinho nao conta.

    python conferir_quadra.py   (fora do container; pip install numpy opencv-python)

corrija os u,v no csv, rode de novo, repita ate encostar.
"""
import csv
import pathlib
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from i3_geometria import Correspondencia, calibrar, erro_reprojecao_cm, pixel_para_mundo

RAIZ = pathlib.Path(__file__).resolve().parent
# linhas da quadra de volei em metros; homografia leva reta em reta, 2 pontos bastam
LINHAS = [((0, 0), (18, 0)), ((18, 0), (18, 9)), ((18, 9), (0, 9)), ((0, 9), (0, 0)),
          ((9, 0), (9, 9)), ((6, 0), (6, 9)), ((12, 0), (12, 9))]
COR = {"ajuste": (0, 255, 0), "holdout": (0, 255, 255)}


def ler(caminho):
    """le o csv ignorando comentario e linha marcada como pular"""
    linhas = [l for l in open(caminho) if not l.startswith("#")]
    for r in csv.DictReader(linhas):
        if r["uso"] != "pular":
            yield (Correspondencia((float(r["u"]), float(r["v"])), (float(r["x"]), float(r["y"]))),
                   r["uso"], r["ponto"])


def montar_zoom(img, marcas, r=45, amp=4):
    """um recorte ampliado por ponto -- e a unica escala em que da pra julgar 2 px"""
    celulas = []
    for c, uso, nome in marcas:
        u, v = (int(round(t)) for t in c.pixel)
        pedaco = img[max(v - r, 0):v + r, max(u - r, 0):u + r]
        z = cv2.resize(pedaco, None, fx=amp, fy=amp, interpolation=cv2.INTER_NEAREST)
        cv2.putText(z, f"{nome[:26]} ({u},{v})", (6, 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (255, 255, 255), 1, cv2.LINE_AA)
        celulas.append(cv2.copyMakeBorder(z, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(40, 40, 40)))
    lado = 2 * r * amp + 4
    celulas += [np.zeros((lado, lado, 3), np.uint8)] * (-len(celulas) % 4)
    return np.vstack([np.hstack(celulas[i:i + 4]) for i in range(0, len(celulas), 4)])


def main():
    marcas = list(ler(RAIZ / "dados/pontos_quadra.csv"))
    ajuste = [c for c, uso, _ in marcas if uso == "ajuste"]
    holdout = [c for c, uso, _ in marcas if uso == "holdout"]
    if len(ajuste) < 4:
        raise SystemExit(f"o i3 precisa de 4 pontos de ajuste, tem {len(ajuste)}")

    H = calibrar(ajuste)
    Hinv = np.linalg.inv(H)

    def para_pixel(p):
        v = Hinv @ np.array([p[0], p[1], 1.0])
        return tuple(int(round(c)) for c in v[:2] / v[2])

    img = cv2.imread(str(RAIZ / "dados/quadra_limpa.png"))
    for a, b in LINHAS:                                  # quadra reprojetada, em magenta
        cv2.line(img, para_pixel(a), para_pixel(b), (255, 0, 255), 2, cv2.LINE_AA)

    print(f"{'ponto':32s} {'marcado':>12s} {'reprojetado':>12s}  erro_px")
    for c, uso, nome in marcas:
        marcado = tuple(int(round(v)) for v in c.pixel)
        volta = para_pixel(c.mundo)
        d = float(np.hypot(volta[0] - marcado[0], volta[1] - marcado[1]))
        cv2.circle(img, marcado, 7, COR[uso], 2, cv2.LINE_AA)   # onde voce marcou
        cv2.drawMarker(img, volta, (0, 0, 255), cv2.MARKER_CROSS, 14, 2)  # onde a calibracao poe
        print(f"{nome:32s} {str(marcado):>12s} {str(volta):>12s}  {d:6.1f}  {uso}")

    print(f"\najuste : {len(ajuste)} pontos · rms {erro_reprojecao_cm(H, ajuste):.1f} cm (otimista)")
    if holdout:
        print(f"holdout: {len(holdout)} pontos · rms {erro_reprojecao_cm(H, holdout):.1f} cm  <- o que vale")
    canto = pixel_para_mundo(H, (640, 598))
    print(f"\nsanidade: pixel (640,598) cai em ({canto[0]:.2f}, {canto[1]:.2f}) m  [esperado ~(9, 0)]")

    painel = montar_zoom(img, marcas)
    cv2.imwrite(str(RAIZ / "dados/conferencia_zoom.png"), painel)

    saida = RAIZ / "dados/conferencia.png"
    cv2.imwrite(str(saida), img)
    print(f"\nmagenta = quadra reprojetada · circulo = voce marcou · cruz vermelha = calibracao\n{saida}")


if __name__ == "__main__":
    main()
