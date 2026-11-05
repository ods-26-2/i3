"""o artefato CALIBRATION da 6c: o evento ods.i3.calibration, o registro e o anuncio

ciclo de vida (6c, Arquitetura secao 3): o dono grava o artefato no registro com o descritor
comum, anuncia a versao em ods.artifact.published e publica o conteudo em ods.i3.calibration.
uma versao nunca muda: correcao e versao nova.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

TOPICO = "ods.i3.calibration"
ANUNCIO = "ods.artifact.published"


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def evento(source_id, versao, valido_desde, largura, altura, K, dist, H, rms_cm, n_holdout,
           espaco, origem, eixos):
    """ods.i3.calibration, perfil EV-SINAL sem captured_at e session_id (6c): e artefato, nao
    sinal de um quadro. o referencial (space_id, origin, axes) e valor da instalacao, da aplicacao"""
    return {
        "message_type": "event",
        "message_id": str(uuid.uuid4()),
        "schema": TOPICO,
        "schema_version": "1.0",
        "producer": "I3",
        "published_at": agora(),
        "source_id": source_id,
        "sequence": 0,                          # uma calibracao por execucao
        "artifact_version": versao,
        "payload": {
            "valid_from": valido_desde,
            "image_width": largura,
            "image_height": altura,
            "intrinsics": K,
            "distortion": dist,
            "homography_px_to_m": H.tolist(),
            "reference_frame": {"space_id": espaco, "origin": origem, "axes": eixos},
            "reprojection_rms_cm": round(rms_cm, 2),
            "holdout_points": n_holdout,
        },
    }


def registrar(ev, raiz):
    """grava o CALIBRATION no registro (registry://<caminho> = <raiz>/<caminho>), a pasta que o
    S1 le em S1_REGISTRY_DIR, e devolve o descritor comum.

    idempotente: a mesma versao com o mesmo conteudo devolve o descritor gravado (da para
    anunciar de novo se o broker falhou); com outro conteudo e erro, porque versao nao muda."""
    versao = ev["artifact_version"]
    caminho = f"i3/calibration/{versao}/content.json"
    pasta = Path(raiz) / caminho.rsplit("/", 1)[0]
    dados = json.dumps(ev["payload"], ensure_ascii=False, indent=2).encode("utf-8")
    hash_sha256 = hashlib.sha256(dados).hexdigest()
    if pasta.exists():
        gravado = json.loads((pasta / "descriptor.json").read_text(encoding="utf-8"))
        if gravado["hash_sha256"] != hash_sha256:
            raise ValueError(f"{versao} ja esta no registro com outro conteudo; versao nao muda (6c), "
                             "use --versao nova (ou o mesmo --valido-desde para repetir o anuncio)")
        return gravado
    pasta.mkdir(parents=True)
    descritor = {"artifact_id": f"cal-{ev['source_id']}", "artifact_version": versao, "kind": "CALIBRATION",
                 "owner": "I3", "uri": f"registry://{caminho}", "hash_sha256": hash_sha256,
                 "valid_from": ev["payload"]["valid_from"], "schema_version": "1.0"}
    (pasta / "content.json").write_bytes(dados)
    (pasta / "descriptor.json").write_text(json.dumps(descritor, indent=2), encoding="utf-8")
    return descritor


def anuncio(descritor):
    """envelope de ods.artifact.published (perfil EV-SERVICO sem campos de sinal); o payload e o
    descritor comum"""
    return {"message_type": "event", "message_id": str(uuid.uuid4()), "schema": ANUNCIO,
            "schema_version": "1.0", "producer": "I3", "published_at": agora(), "payload": descritor}
