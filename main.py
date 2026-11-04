"""borda do i3: csv de pontos da quadra no stdin -> evento de calibracao no stdout

    docker run -i --rm inv-i3 < dados/pontos_quadra.csv > calibracao.json
    docker run -i --rm --network host inv-i3 --kafka localhost:9092 < dados/pontos_quadra.csv
    python main.py --linhas dados/quadra_mediana.png < dados/pontos_quadra.csv   # linhas medidas

um json por execucao, envelope comum da arquitetura 6c (perfil EV-SINAL, sem captured_at
e session_id). e artefato: com --kafka vai pro topico ods.i3.calibration, chave source_id;
quem chega depois le a ultima do topico. sem --kafka sai no stdout.
"""
import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone

from i3_geometria import Correspondencia, calibrar, erro_reprojecao_cm, intrinsecos


TOPICO = "ods.i3.calibration"


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ler(linhas):
    """separa ajuste e holdout, ignorando comentario e ponto marcado como pular"""
    marcas = {"ajuste": [], "holdout": []}
    for r in csv.DictReader(l for l in linhas if not l.startswith("#")):
        if r["uso"] != "pular":
            marcas[r["uso"]].append(
                Correspondencia((float(r["u"]), float(r["v"])), (float(r["x"]), float(r["y"]))))
    return marcas


def evento(marcas, a):
    if a.linhas:
        # procedimento de bancada: as linhas da quadra medidas na imagem; os pontos do csv
        # so dizem onde procurar, e o erro e o de tercos de linha que ficaram fora do ajuste
        import cv2
        from medir_linhas import calibrar_por_linhas
        H, rms, cruzamentos, medidos = calibrar_por_linhas(cv2.imread(a.linhas), marcas["ajuste"] + marcas["holdout"])
        K, dist = intrinsecos(cruzamentos, a.largura, a.altura)
        n_holdout = sum(medidos.values())
    else:
        H = calibrar(marcas["ajuste"])
        rms = erro_reprojecao_cm(H, marcas["holdout"]) if marcas["holdout"] else None
        K, dist = intrinsecos(marcas["ajuste"] + marcas["holdout"], a.largura, a.altura)
        n_holdout = len(marcas["holdout"])
    return {
        "message_type": "event",
        "message_id": str(uuid.uuid4()),
        "schema": TOPICO,
        "schema_version": "1.0",
        "producer": "I3",
        "published_at": agora(),
        "source_id": a.source_id,
        "sequence": 0,                          # uma calibracao por execucao
        "artifact_version": a.versao or f"cal-{a.source_id}-1",
        "payload": {
            "valid_from": a.valido_desde or agora(),
            "image_width": a.largura,
            "image_height": a.altura,
            "intrinsics": K,
            "distortion": dist,
            "homography_px_to_m": H.tolist(),
            "reference_frame": {"space_id": a.espaco, "origin": "canto proximo esquerdo",
                                "axes": "x ao longo dos 18 m, y afastando da camera"},
            "reprojection_rms_cm": None if rms is None else round(rms, 2),
            "holdout_points": n_holdout,
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-id", default="cam-ref")
    p.add_argument("--versao", help="padrao e cal-<source_id>-1")
    p.add_argument("--largura", type=int, default=1280, help="resolucao do quadro calibrado")
    p.add_argument("--altura", type=int, default=720)
    p.add_argument("--valido-desde", help="ISO 8601 UTC; padrao e agora")
    p.add_argument("--espaco", default="quadra-volei-fivb")
    p.add_argument("--kafka", metavar="HOST:PORTA", help="publica no broker em vez do stdout")
    p.add_argument("--linhas", metavar="IMAGEM",
                   help="mede as linhas da quadra nessa imagem (mediana sem jogadores, medir_linhas.py)")
    a = p.parse_args()
    ev = evento(ler(sys.stdin), a)
    print(f"i3: rms {ev['payload']['reprojection_rms_cm']} cm fora do ajuste, focal {ev['payload']['intrinsics']['fx']} px",
          file=sys.stderr)
    if a.kafka:
        from confluent_kafka import Producer
        produtor = Producer({"bootstrap.servers": a.kafka})
        falhas = []
        produtor.produce(TOPICO, key=a.source_id, value=json.dumps(ev).encode(),
                         on_delivery=lambda erro, _msg: erro and falhas.append(erro))
        if produtor.flush(10) or falhas:
            raise SystemExit(f"i3: broker {a.kafka} nao confirmou a entrega")
        print(f"i3: publicado em {TOPICO}", file=sys.stderr)
    else:
        json.dump(ev, sys.stdout)
        print()
