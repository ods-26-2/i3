"""I3 · geometria e calibracao: correspondencias da instalacao -> artefato CALIBRATION

    docker run -i --rm inv-i3 --source-id cam0 < correspondencias.csv > calibracao.json
    docker run -i --rm --network host inv-i3 --source-id cam0 --kafka localhost:9092 < correspondencias.csv

entrada (stdin): csv u,v,x,y,uso,ponto (geometria/entrada.py), medido na instalacao; precisa de
4 pontos de ajuste e de pelo menos 1 de holdout, que mede o erro. com --linhas, a quadra de
volei e medida na imagem (geometria/quadra_volei.py) e o csv so diz onde procurar.
saida: o evento ods.i3.calibration (6c) no stdout, como arquivo; com --kafka, no topico de mesmo
nome, chave source_id. com --registro, grava o CALIBRATION com o descritor comum e, com
--kafka, anuncia a versao em ods.artifact.published.
"""
import argparse
import sys
from datetime import datetime, timezone

from geometria import artefato, contrato, publicacao
from geometria.entrada import ler, separar
from geometria.homografia import calibrar, erro_reprojecao_cm
from geometria.intrinsecos import intrinsecos


def falhar(mensagem):
    print(f"i3: {mensagem}", file=sys.stderr)
    raise SystemExit(2)


def instante(texto):
    """ISO 8601 com fuso -> UTC com milissegundos, o formato da 6c"""
    try:
        t = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"esperado ISO 8601, ex. 2026-09-23T14:00:00.000Z, veio {texto!r}") from None
    if t.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{texto!r} sem fuso; use Z para UTC")
    return t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def argumentos(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # --camera-id: nome de antes da 6c, ainda usado pela suite do B4
    p.add_argument("--source-id", "--camera-id", dest="source_id", default="cam-ref",
                   help="camera calibrada, pelo nome do cadastro da instalacao")
    p.add_argument("--versao", help="artifact_version; padrao e cal-<source_id>-1")
    p.add_argument("--largura", type=int, default=1280, help="largura do quadro calibrado (com --linhas, a da imagem)")
    p.add_argument("--altura", type=int, default=720, help="altura do quadro calibrado (com --linhas, a da imagem)")
    p.add_argument("--valido-desde", type=instante, help="ISO 8601 com fuso; padrao e agora")
    # o referencial e valor da instalacao (6c: "A8 possui os valores da instalacao"), entao vem
    # de fora: a mesma calibracao serve a quadra do A4, ao patio do A8 e ao galpao do A5
    p.add_argument("--espaco", default="espaco-1", help="space_id do plano, o mesmo das zonas da aplicacao")
    p.add_argument("--origem", default="ponto (0, 0) das correspondencias",
                   help="onde fica a origem do plano, em texto (reference_frame.origin)")
    p.add_argument("--eixos", default="x e y das colunas x,y das correspondencias, em metros",
                   help="como correm os eixos, em texto (reference_frame.axes)")
    p.add_argument("--kafka", metavar="HOST:PORTA", help="publica no broker em vez do stdout")
    p.add_argument("--registro", metavar="PASTA",
                   help="registro de artefatos (6c): grava CALIBRATION com descritor; com --kafka, anuncia")
    p.add_argument("--linhas", metavar="IMAGEM",
                   help="quadra de volei: mede as linhas nessa imagem (mediana sem jogadores)")
    return p.parse_args(argv)


def medir(marcas, a):
    """(H, rms_cm, n_holdout, K, dist, largura, altura) pelo csv ou pelas linhas da quadra"""
    pontos = separar(marcas)
    if len(pontos["ajuste"]) < 4:
        falhar(f"sao necessarios 4 pontos de ajuste, o csv tem {len(pontos['ajuste'])}")
    if a.linhas:
        import cv2
        from geometria.quadra_volei import calibrar_por_linhas
        img = cv2.imread(a.linhas)
        if img is None:
            falhar(f"nao consegui abrir a imagem {a.linhas}")
        altura, largura = img.shape[:2]
        H, rms, cruzamentos, medidos = calibrar_por_linhas(img, pontos["ajuste"] + pontos["holdout"])
        K, dist = intrinsecos(cruzamentos, largura, altura)
        return H, rms, sum(medidos.values()), K, dist, largura, altura
    if not pontos["holdout"]:
        falhar("o csv nao tem ponto de holdout; sem ele nao ha erro de reprojecao, que a 6c exige")
    H = calibrar(pontos["ajuste"])
    K, dist = intrinsecos(pontos["ajuste"] + pontos["holdout"], a.largura, a.altura)
    return (H, erro_reprojecao_cm(H, pontos["holdout"]), len(pontos["holdout"]), K, dist,
            a.largura, a.altura)


def main(argv=None):
    a = argumentos(argv)
    try:
        marcas = ler(sys.stdin)
    except ValueError as erro:
        falhar(f"csv de correspondencias: {erro}")
    H, rms, n_holdout, K, dist, largura, altura = medir(marcas, a)
    ev = artefato.evento(a.source_id, a.versao or f"cal-{a.source_id}-1", a.valido_desde or artefato.agora(),
                         largura, altura, K, dist, H, rms, n_holdout, a.espaco, a.origem, a.eixos)
    print(f"i3: rms {ev['payload']['reprojection_rms_cm']} cm fora do ajuste, focal {K['fx']} px",
          file=sys.stderr)
    contrato.validar(ev)                      # antes de gravar: o registro so recebe artefato valido
    mensagens = [ev]
    if a.registro:
        try:
            descritor = artefato.registrar(ev, a.registro)
        except ValueError as erro:
            falhar(str(erro))
        print(f"i3: {descritor['uri']} no registro {a.registro}", file=sys.stderr)
        mensagens.append(artefato.anuncio(descritor))
    publicacao.publicar(mensagens, a.source_id, a.kafka)


if __name__ == "__main__":
    main()
