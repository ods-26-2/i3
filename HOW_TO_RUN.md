# Como rodar o I3

## 1. Testes

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s I3/tests -t I3 -v
```

A suíte cobre a homografia, os intrínsecos, o csv, o artefato e o registro, os dois contratos
(todos os exemplos de `schemas/examples/`), três instalações sintéticas (pátio do A8, galpão do
A5 e quadra do A4), o procedimento da quadra sobre a imagem real e a linha de comando, inclusive
a chamada exata da suíte do B4. Roda no GitHub Actions a cada envio.

## 2. Calibrar uma câmera

1. **Medir as correspondências na instalação.** Pontos do chão com posição conhecida em metros
   (cantos de vaga, marcas de piso, cruzamentos de linha) e onde cada um aparece na imagem da
   câmera, em pixels do quadro bruto. Pelo menos 4 de ajuste, espalhados, e 1 ou mais de holdout,
   que não entram no cálculo e medem o erro.
2. **Escrever o csv** `u,v,x,y,uso,ponto`.
3. **Rodar**, com o referencial da instalação:

```bash
.venv/bin/python main.py --source-id cam0 --versao cal-cam0-1 --largura 1920 --altura 1080 \
    --espaco patio-1 --origem "canto sudoeste do patio" --eixos "x ao longo da rua, y para o fundo" \
    < correspondencias.csv > calibracao.json
```

O stderr mostra o erro fora do ajuste e a focal. Refazer quando a câmera se mexer, com `--versao`
nova.

## 3. Publicar no barramento e no registro

```bash
.venv/bin/python main.py --source-id cam0 --versao cal-cam0-1 --registro /caminho/do/registro \
    --kafka localhost:9092 < correspondencias.csv
```

- O CALIBRATION vai para `<registro>/i3/calibration/<versao>/` (`content.json` e
  `descriptor.json`), no formato `registry://` que o S1 lê em `S1_REGISTRY_DIR`.
- O conteúdo sai em `ods.i3.calibration` e a versão é anunciada em `ods.artifact.published`.
  Os dois juntos, como no ciclo de vida da 6c (seção 3): `--kafka` sem `--registro` é recusado,
  porque quem sobe depois carrega a versão do registro, não do tópico.
- Se o broker falhar, rode de novo com o mesmo `--valido-desde`: o registro reconhece o mesmo
  conteúdo e só anuncia de novo. Conteúdo diferente com a mesma versão é recusado.
- **Kafka local:** `docker compose up -d` no repo do [A4](https://github.com/ods-26-2/a4).
  **Kafka da Jetson:** `172.18.4.56:9092`, só dentro da rede do DCOMP.

## 4. Quadra de vôlei (A4)

```bash
.venv/bin/python main.py --source-id cam0 --versao cal-cam0-2 --espaco quadra-volei-fivb \
    --origem "canto proximo esquerdo" --eixos "x ao longo dos 18 m, y afastando da camera" \
    --linhas dados/quadra_mediana.png < dados/pontos_quadra.csv
.venv/bin/python I3/ferramentas/conferir_quadra.py        # desenha a quadra reprojetada em dados/
```

O `space_id` e o referencial têm que ser esses: são os que as zonas do A4 e a regra de dentro e
fora usam.

## 5. Suíte de integração do B4

O B4 roda `python i3/main.py --camera-id cam0 --versao ... --valido-desde ... --espaco quadra-1`
com um csv no stdin, a partir da raiz deste repo. O `main.py` da raiz e o `--camera-id` (nome
antigo de `--source-id`) existem para manter essa chamada; `I3/tests/test_cli.py` a reproduz.
