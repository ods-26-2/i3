"""o csv de correspondencias: o que vale e o erro claro, com a linha, no que nao vale"""
import unittest

from geometria.entrada import ler, separar

BOM = """# comentario da instalacao
u,v,x,y,uso,ponto
0,0,0,0,ajuste,a
100,0,1,0,ajuste,b

0,100,0,1,pular,c
50,50,0.5,0.5,holdout,d
""".splitlines(keepends=True)


class Csv(unittest.TestCase):
    def test_separa_ajuste_e_holdout_e_tira_os_pulados(self):
        marcas = ler(BOM)
        self.assertEqual([(m.ponto, m.uso, m.linha) for m in marcas], [("a", "ajuste", 3), ("b", "ajuste", 4), ("d", "holdout", 7)])
        pontos = separar(marcas)
        self.assertEqual((len(pontos["ajuste"]), len(pontos["holdout"])), (2, 1))
        self.assertEqual(pontos["holdout"][0].mundo, (0.5, 0.5))

    def test_uso_desconhecido_diz_a_linha(self):
        with self.assertRaisesRegex(ValueError, "linha 3: uso 'ajust'"):
            ler(["# x\n", "u,v,x,y,uso,ponto\n", "0,0,0,0,ajust,a\n"])

    def test_numero_invalido_diz_a_linha(self):
        with self.assertRaisesRegex(ValueError, "linha 2: u, v, x e y"):
            ler(["u,v,x,y,uso,ponto\n", "0,zero,0,0,ajuste,a\n"])

    def test_coluna_faltando(self):
        with self.assertRaisesRegex(ValueError, "faltam as colunas"):
            ler(["u,v,x,y,ponto\n", "0,0,0,0,a\n"])

    def test_csv_vazio(self):
        with self.assertRaisesRegex(ValueError, "vazio"):
            ler(["# so comentario\n"])


if __name__ == "__main__":
    unittest.main()
