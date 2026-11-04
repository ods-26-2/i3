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
docker run -i --rm -v $PWD/dados:/dados inv-i3 --linhas /dados/quadra_mediana.png \
    < dados/pontos_quadra.csv > calibracao.json                                  # linhas medidas
```

Entrada (stdin): o csv de `dados/pontos_quadra.csv` (`u,v,x,y,uso,ponto`; `uso` é
`ajuste`, `holdout` ou `pular`). Saída: **um** evento JSON no stdout, ou no tópico de mesmo nome com `--kafka`,
`ods.i3.calibration`, no envelope e no payload da arquitetura 6c. É artefato: grava em
arquivo e quem consome lê quando quiser. Opções: `--source-id`, `--versao` (padrão
`cal-<source_id>-1`), `--largura`, `--altura`, `--valido-desde`, `--espaco`, `--linhas`
(mede as linhas da quadra numa imagem; ver o procedimento abaixo).

Na 6c o P4 entrega o quadro bruto, então o artefato leva intrínsecos e distorção. Hoje a focal
sai dos próprios pontos da quadra (uma vista, centro no meio, distorção zero); na Jetson a
lente é fixa e a calibração com tabuleiro é feita uma vez. Consumidores: S1, S5, I9, A4, A8.

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

O padrão é a própria quadra de vôlei FIVB, 18 × 9 m. As linhas são medidas na imagem, sem
clique (`medir_linhas.py`, opção `--linhas` do `main.py`):

1. **Câmera fixa.** Conferir que a quadra não anda entre trechos do jogo (na câmera do A4,
   menos de 1 px em 8 min). Se andar, uma calibração por trecho.
2. **Imagem sem jogadores.** Mediana de dezenas de quadros espalhados pelo jogo
   (`dados/quadra_mediana.png`: 80 quadros do vídeo do A4).
3. **Linhas no subpixel.** A cada 25 cm ao longo de cada linha (laterais, fundos e ataques),
   um perfil perpendicular acha o centro da faixa branca pelo centróide do brilho. Os pontos
   de `dados/pontos_quadra.csv` só dizem onde procurar.
4. **Homografia pelas linhas.** Ajuste que põe cada ponto medido sobre o eixo da sua linha,
   com a geometria FIVB: linha de 5 cm, as de fronteira dentro da quadra, a de ataque com a
   borda de trás a 3 m do eixo da central. Ponto a mais de 3 desvios (pela mediana) da sua
   linha sai e o ajuste refaz: poste, logo e oclusão saem sozinhos.
5. **Erro fora do ajuste.** Cada linha em terços; cada terço sai do ajuste e é medido contra
   a sua reta. É esse rms que vai em `reprojection_rms_cm`.
6. **Intrínsecos.** Focal pelos cruzamentos das linhas medidas, centro ótico no meio da imagem.

Medido na câmera do A4 (`cal-cam0-2`): **1,43 cm fora do ajuste**, 253 pontos de linha. Os
8 pontos marcados no olho davam 14,7 cm. Uma distorção radial de um termo baixava para
1,19 cm, mas a 6c pede homografia sobre o pixel bruto, que a distorção não deixa exata;
fica sem distorção. Refazer quando a câmera se mexer.

Conferência visual: `python conferir_quadra.py` (fora do container; precisa de
`pip install numpy opencv-python`) reprojeta as linhas conhecidas por cima da foto.
