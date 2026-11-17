"""o main.py da raiz, do jeito que o B4 e a cadeia chamam, e os erros de entrada"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from geometria import contrato

RAIZ = Path(__file__).resolve().parents[2]

# a chamada exata da suite do B4 (ods-26-2/b4, tests/integration/i3/test_i3.py)
CSV_B4 = (
    "u,v,x,y,uso,ponto\n"
    "0,0,0,0,ajuste,p0\n"
    "100,0,1,0,ajuste,p1\n"
    "0,100,0,1,ajuste,p2\n"
    "100,100,1,1,ajuste,p3\n"
    "50,0,0.5,0,ajuste,p4\n"
    "0,50,0,0.5,ajuste,p5\n"
    "50,50,0.5,0.5,holdout,p6\n"
    "80,20,0.8,0.2,holdout,p7\n"
)


def rodar(*args, entrada=CSV_B4):
    return subprocess.run([sys.executable, str(RAIZ / "main.py"), *args], cwd=RAIZ, input=entrada,
                          text=True, capture_output=True, timeout=120)


class ChamadaDoB4(unittest.TestCase):
    def test_csv_com_camera_id_da_calibracao_valida(self):
        r = rodar("--camera-id", "cam0", "--versao", "cal-cam0-test", "--valido-desde", "2026-09-23T14:00:00.000Z",
                  "--espaco", "quadra-1")
        self.assertEqual(r.returncode, 0, r.stderr)
        ev = json.loads(r.stdout)
        self.assertEqual(contrato.erros(ev), [])
        self.assertEqual((ev["source_id"], ev["artifact_version"]), ("cam0", "cal-cam0-test"))
        self.assertEqual(ev["payload"]["reference_frame"]["space_id"], "quadra-1")


class Erros(unittest.TestCase):
    def test_sem_holdout_e_codigo_2(self):
        r = rodar(entrada=CSV_B4.replace("holdout", "ajuste"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("holdout", r.stderr)

    def test_imagem_inexistente_com_linhas(self):
        r = rodar("--linhas", "/nao/existe.png")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nao consegui abrir a imagem", r.stderr)

    def test_csv_errado_diz_a_linha(self):
        r = rodar(entrada=CSV_B4.replace("p3", "p3\n1,1,1,1,medir,p9"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("linha 6", r.stderr)

    def test_valido_desde_sem_fuso_e_recusado(self):
        r = rodar("--valido-desde", "2026-09-23T14:00:00")
        self.assertEqual(r.returncode, 2)


class Registro(unittest.TestCase):
    def test_repetir_a_mesma_versao_reaproveita_o_registro(self):
        raiz = tempfile.mkdtemp()
        args = ("--source-id", "cam0", "--valido-desde", "2026-09-23T14:00:00.000Z", "--registro", raiz)
        self.assertEqual(rodar(*args).returncode, 0)
        self.assertEqual(rodar(*args).returncode, 0, "mesmo conteudo: pode repetir para anunciar de novo")
        r = rodar("--source-id", "cam0", "--valido-desde", "2026-09-24T14:00:00.000Z", "--registro", raiz)
        self.assertEqual(r.returncode, 2)
        self.assertIn("versao nao muda", r.stderr)

    def test_publicar_sem_registro_e_recusado(self):
        r = rodar("--source-id", "cam0", "--kafka", "localhost:1")    # recusa antes de abrir o broker
        self.assertEqual(r.returncode, 2)
        self.assertIn("--registro", r.stderr)


if __name__ == "__main__":
    unittest.main()
