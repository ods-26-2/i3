"""o artefato CALIBRATION: evento, registro idempotente, anuncio e os exemplos do schema"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from geometria import artefato, contrato

EXEMPLOS = Path(__file__).resolve().parents[2] / "schemas" / "examples"


def evento(rms=1.43, espaco="patio-1"):
    return artefato.evento("cam-patio", "cal-cam-patio-1", "2026-09-23T14:00:00.000Z", 1920, 1080,
                           {"fx": 1400.0, "fy": 1400.0, "cx": 960.0, "cy": 540.0}, [0.0] * 5, np.eye(3), rms, 4,
                           espaco, "canto sudoeste do patio", "x ao longo da rua, y para o fundo")


class Evento(unittest.TestCase):
    def test_referencial_vem_da_instalacao(self):
        ev = evento()
        self.assertEqual(ev["payload"]["reference_frame"],
                         {"space_id": "patio-1", "origin": "canto sudoeste do patio",
                          "axes": "x ao longo da rua, y para o fundo"})
        self.assertEqual(contrato.erros(ev), [])


class Registro(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp()

    def test_grava_conteudo_e_descritor_que_o_s1_le(self):
        ev = evento()
        d = artefato.registrar(ev, self.raiz)
        conteudo = (Path(self.raiz) / d["uri"].removeprefix("registry://")).read_bytes()
        self.assertEqual(hashlib.sha256(conteudo).hexdigest(), d["hash_sha256"], "o S1 confere o sha256 dos bytes")
        self.assertEqual(json.loads(conteudo), ev["payload"])
        self.assertEqual((d["artifact_id"], d["kind"], d["owner"]), ("cal-cam-patio", "CALIBRATION", "I3"))
        self.assertEqual(contrato.erros(artefato.anuncio(d)), [])

    def test_mesma_versao_e_mesmo_conteudo_reaproveita(self):
        primeiro = artefato.registrar(evento(), self.raiz)
        self.assertEqual(artefato.registrar(evento(), self.raiz), primeiro)

    def test_mesma_versao_com_outro_conteudo_e_erro(self):
        artefato.registrar(evento(), self.raiz)
        with self.assertRaisesRegex(ValueError, "versao nao muda"):
            artefato.registrar(evento(rms=2.0), self.raiz)


class Exemplos(unittest.TestCase):
    def test_validos_passam_e_invalidos_falham(self):
        for pasta, valido in (("valid", True), ("invalid", False)):
            for p in sorted((EXEMPLOS / pasta).glob("*.json")):
                with self.subTest(p.name):
                    self.assertEqual(contrato.erros(json.loads(p.read_text(encoding="utf-8"))) == [], valido)

    def test_schema_que_o_i3_nao_publica(self):
        self.assertNotEqual(contrato.erros({"schema": "ods.i2.tracks"}), [])


if __name__ == "__main__":
    unittest.main()
