# I3 · geometria de câmera

Parte do INV-1 · ODS 2026/2. O squad tem três componentes, cada um no seu repositório
e no seu container: [I2](https://github.com/ods-26-2/i2) (identidade e rastreio), [I3](https://github.com/ods-26-2/i3) (geometria e
calibração) e [A4](https://github.com/ods-26-2/a4) (arbitragem). Nenhum importa o outro: eles conversam pelo
Kafka do projeto, no envelope de `docs/INV-1_interfaces.md`, seguindo o guia
`docs/Guia_Kafka_B2_v2.pdf`. A cadeia completa está no README do [A4](https://github.com/ods-26-2/a4).

Só numpy + cliente Kafka.

## Rodar

```
docker build -t inv-i3 .
docker run -i --rm inv-i3 < dados/pontos_quadra.csv > calibracao.json   # local, em arquivo
docker run -i --rm inv-i3 --kafka 34.66.235.91:9093 < dados/pontos_quadra.csv   # barramento
```

Entrada (stdin): o csv de `dados/pontos_quadra.csv` (`u,v,x,y,uso,ponto`; `uso` é
`ajuste`, `holdout` ou `pular`). Saída: **um** evento JSON no stdout, ou no tópico de mesmo nome com `--kafka`,
`ods.visao.calibracao_publicada`, no formato de `docs/INV-1_interfaces.md`. É artefato: grava em
arquivo e quem consome lê quando quiser. Opções: `--camera-id`, `--versao`,
`--valido-desde`, `--espaco`.

Entra vídeo já corrigido de distorção (P4, SIS-2). Consumidores: S1, S5, A4, A8.

**Entrada** `Correspondencia(pixel, mundo)`

| campo | formato | de onde vem |
|---|---|---|
| `pixel` | `(u, v)` em px | ponto marcado na imagem |
| `mundo` | `(x, y)` em m | medida real da quadra, do regulamento |

**Saída** `Calibracao(camera_id, homografia, referencial, rms_cm, valido_desde, versao)`

| campo | formato | por que existe |
|---|---|---|
| `homografia` | matriz 3×3 | imagem → plano |
| `referencial` | `Referencial(origem, eixos, unidade)` | tem que bater com o de S1 |
| `rms_cm` | float | medido em holdout, em cm |
| `valido_desde` / `versao` | data / str | consumidor precisa dizer qual usou |

**O que importa**

- É artefato versionado, não serviço em runtime. Sai uma tupla mais a função pura
  `pixel_para_mundo()`. Serviço criaria acoplamento em execução com LIB-1 e VER-5.
- Erro medido nos pontos do ajuste é otimista por construção — deu 0,3 cm contra
  0,9 cm em pontos novos. A métrica é a do holdout, em centímetro, não em pixel.
  O procedimento que produz esse número está no fim deste arquivo.
- Refazer quando a câmera se mexe.

## Procedimento de bancada · card I3.3

- O padrão é a própria quadra: cantos e cruzamentos de linha do vôlei FIVB, 18 × 9 m,
  marcados no olho em `dados/quadra_limpa.png` e anotados em `dados/pontos_quadra.csv`.
- 8 correspondências: 6 entram no ajuste, 2 ficam de holdout. O erro que vale é o do
  holdout — medir nos pontos do próprio ajuste é otimista por construção.
- Conferência: `python conferir_quadra.py` (fora do container; precisa de
  `pip install numpy opencv-python`) reprojeta as linhas conhecidas por
  cima da foto e amplia cada ponto 4×, que é a escala em que 2 px se decidem. Corrige o `u,v`
  no csv, roda de novo, repete até encostar.
- Medido assim: **rms 0,9 cm no holdout**, 0,3 cm no ajuste. Evidência em
  `dados/conferencia.png` e `dados/conferencia_zoom.png`. Refazer quando a câmera se mexer.
