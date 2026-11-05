"""saida do I3: o evento de calibracao no stdout, ou os topicos com --kafka

as mensagens sao validadas antes de sair, todas ou nenhuma: calibracao fora do contrato nao
chega ao barramento (6c).
"""
import json
import sys

from geometria import contrato


def publicar(mensagens, chave, broker=None):
    """mensagens: [ods.i3.calibration, (ods.artifact.published)]. sem broker, so a calibracao vai
    para o stdout, como arquivo de artefato; com broker, todas vao para os seus topicos"""
    for msg in mensagens:
        contrato.validar(msg)
    if broker is None:
        json.dump(mensagens[0], sys.stdout)
        print()
        return
    from confluent_kafka import Producer
    produtor, falhas = Producer({"bootstrap.servers": broker}), []
    for msg in mensagens:
        produtor.produce(msg["schema"], key=chave, value=json.dumps(msg).encode(),
                         on_delivery=lambda erro, _msg: erro and falhas.append(erro))
    if produtor.flush(10) or falhas:
        raise SystemExit(f"i3: broker {broker} nao confirmou a entrega")
    print("i3: publicado em " + ", ".join(m["schema"] for m in mensagens), file=sys.stderr)
