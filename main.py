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
ANUNCIO = "ods.artifact.published"


def registrar(ev, raiz):
    """6c, ciclo de vida do artefato: o dono grava o CALIBRATION no registro com o descritor
    comum. pasta no formato do registro (registry://<caminho> = <raiz>/<caminho>), a mesma
    que o a4 usa para as zonas e o s1 le em S1_REGISTRY_DIR. versao nao muda: se ja existe, erro"""
    import hashlib
    from pathlib import Path
    versao = ev["artifact_version"]
    caminho = f"i3/calibration/{versao}/content.json"
    pasta = Path(raiz) / caminho.rsplit("/", 1)[0]
    if pasta.exists():
        raise SystemExit(f"i3: {versao} ja esta no registro; versao nao muda (6c), use --versao nova")
    pasta.mkdir(parents=True)
    dados = json.dumps(ev["payload"], ensure_ascii=False, indent=2).encode("utf-8")
    descritor = {"artifact_id": f"cal-{ev['source_id']}", "artifact_version": versao, "kind": "CALIBRATION",
                 "owner": "I3", "uri": f"registry://{caminho}", "hash_sha256": hashlib.sha256(dados).hexdigest(),
                 "valid_from": ev["payload"]["valid_from"], "schema_version": "1.0"}
    (pasta / "content.json").write_bytes(dados)
    (pasta / "descriptor.json").write_text(json.dumps(descritor, indent=2), encoding="utf-8")
    return descritor


def anuncio(descritor):
    """envelope de ods.artifact.published; o payload e o descritor"""
    return {"message_type": "event", "message_id": str(uuid.uuid4()), "schema": ANUNCIO,
            "schema_version": "1.0", "producer": "I3", "published_at": agora(), "payload": descritor}


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
    p.add_argument("--registro", metavar="PASTA",
                   help="registro de artefatos (6c): grava CALIBRATION com descritor; com --kafka, anuncia")
    p.add_argument("--linhas", metavar="IMAGEM",
                   help="mede as linhas da quadra nessa imagem (mediana sem jogadores, medir_linhas.py)")
    a = p.parse_args()
    ev = evento(ler(sys.stdin), a)
    print(f"i3: rms {ev['payload']['reprojection_rms_cm']} cm fora do ajuste, focal {ev['payload']['intrinsics']['fx']} px",
          file=sys.stderr)
    descritor = registrar(ev, a.registro) if a.registro else None
    if descritor:
        print(f"i3: {descritor['uri']} gravado em {a.registro}", file=sys.stderr)
    if a.kafka:
        from confluent_kafka import Producer
        produtor = Producer({"bootstrap.servers": a.kafka})
        falhas = []
        # 6c: o conteudo vai em ods.i3.calibration e a versao e anunciada em ods.artifact.published
        mensagens = [(TOPICO, ev)] + ([(ANUNCIO, anuncio(descritor))] if descritor else [])
        for topico, msg in mensagens:
            produtor.produce(topico, key=a.source_id, value=json.dumps(msg).encode(),
                             on_delivery=lambda erro, _msg: erro and falhas.append(erro))
        if produtor.flush(10) or falhas:
            raise SystemExit(f"i3: broker {a.kafka} nao confirmou a entrega")
        print("i3: publicado em " + ", ".join(t for t, _ in mensagens), file=sys.stderr)
    else:
        json.dump(ev, sys.stdout)
        print()
