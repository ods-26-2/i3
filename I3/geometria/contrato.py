"""validacao no publicador (6c): ods.i3.calibration e ods.artifact.published

os schemas em schemas/ sao a unica fonte do contrato; o publicador e os testes validam contra
eles, sem regra duplicada em codigo.
"""
import json
from functools import lru_cache
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
ARQUIVOS = {"ods.i3.calibration": "ods.i3.calibration.v1.0.schema.json",
            "ods.artifact.published": "ods.artifact.published.v1.0.schema.json"}


@lru_cache(maxsize=None)
def _validador(schema):
    from jsonschema import Draft202012Validator, FormatChecker
    conteudo = json.loads((SCHEMAS / ARQUIVOS[schema]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(conteudo)
    return Draft202012Validator(conteudo, format_checker=FormatChecker())


def erros(msg):
    """violacoes do contrato, em ordem estavel; vazia se a mensagem e valida"""
    schema = msg.get("schema") if isinstance(msg, dict) else None
    if schema not in ARQUIVOS:
        return [f"schema: {schema!r} nao e publicado pelo I3"]
    achados = sorted(_validador(schema).iter_errors(msg), key=lambda e: list(map(str, e.absolute_path)))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<raiz>'}: {e.message}" for e in achados]


def validar(msg):
    problemas = erros(msg)
    if problemas:
        raise ValueError(f"{msg.get('schema')} fora do contrato: " + "; ".join(problemas))
