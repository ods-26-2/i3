"""borda do i3: csv de pontos da quadra no stdin -> evento de calibracao no stdout

    docker run -i --rm inv-i3 < dados/pontos_quadra.csv > calibracao.json
    docker run -i --rm inv-i3 --kafka 34.66.235.91:9093 < dados/pontos_quadra.csv

um json por execucao, envelope do guia kafka b2 (docs/Guia_Kafka_B2_v2.pdf).
e artefato: com --kafka vai pro topico ods.visao.calibracao_publicada, chave
camera_id; quem chega depois le a ultima do topico. sem --kafka sai no stdout.
"""
import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone

from i3_geometria import Correspondencia, calibrar, erro_reprojecao_cm


TOPICO = "ods.visao.calibracao_publicada"


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
    H = calibrar(marcas["ajuste"])
    rms = erro_reprojecao_cm(H, marcas["holdout"]) if marcas["holdout"] else None
    valido = a.valido_desde or agora()
    return {
        "message_id": str(uuid.uuid4()),
        "message_type": "event",
        "schema": TOPICO,
        "schema_version": "1.0",
        "producer": "I3",
        "occurred_at": valido,                  # o fato e a calibracao passar a valer
        "published_at": agora(),
        "payload": {
            "camera_id": a.camera_id,
            "calibration_version": a.versao,
            "valid_from": valido,
            "homography": H.tolist(),
            "reference_frame": {"space_id": a.espaco, "origin": "canto proximo esquerdo",
                                "axes": "x ao longo dos 18 m, y afastando da camera",
                                "unit": "m"},
            "reprojection_rms_cm": None if rms is None else round(rms, 2),
            "holdout_points": len(marcas["holdout"]),
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--camera-id", default="cam-ref")
    p.add_argument("--versao", default="i3-v1")
    p.add_argument("--valido-desde", help="ISO 8601 UTC; padrao e agora")
    p.add_argument("--espaco", default="quadra-volei-fivb")
    p.add_argument("--kafka", metavar="HOST:PORTA", help="publica no broker em vez do stdout")
    a = p.parse_args()
    ev = evento(ler(sys.stdin), a)
    print(f"i3: rms {ev['payload']['reprojection_rms_cm']} cm no holdout", file=sys.stderr)
    if a.kafka:
        from confluent_kafka import Producer
        produtor = Producer({"bootstrap.servers": a.kafka})
        falhas = []
        produtor.produce(TOPICO, key=a.camera_id, value=json.dumps(ev).encode(),
                         on_delivery=lambda erro, _msg: erro and falhas.append(erro))
        if produtor.flush(10) or falhas:
            raise SystemExit(f"i3: broker {a.kafka} nao confirmou a entrega")
        print(f"i3: publicado em {TOPICO}", file=sys.stderr)
    else:
        json.dump(ev, sys.stdout)
        print()
