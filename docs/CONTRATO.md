# Contrato do I3 · `ods.i3.calibration` e o artefato CALIBRATION

A Arquitetura 6c (seção 6, "Contratos e propriedade") pede, para cada contrato, evidência de
contrato, semântica, operação, teste e build. Este documento reúne as cinco para o I3.

## Contrato

- **Schemas:**
  - [`ods.i3.calibration.v1.0.schema.json`](../schemas/ods.i3.calibration.v1.0.schema.json),
    perfil EV-SINAL sem `captured_at` e `session_id`. O payload segue o schema oficial do B1
    (`ods-26-2/b1`, `I3/calibrationEvent.schema.json`), sem campos além dos previstos.
  - [`ods.artifact.published.v1.0.schema.json`](../schemas/ods.artifact.published.v1.0.schema.json),
    perfil EV-SERVIÇO sem campos de sinal, com o descritor comum (B1, `B5/artifactPublishedEvent.schema.json`).
- **Exemplos:** `schemas/examples/valid/` (quadra do A4, pátio do A8, anúncio) e
  `schemas/examples/invalid/`; cada inválido falha por um motivo só, dito no nome do arquivo.
- **Validação no publicador:** a calibração é validada antes de ir para o registro, e as
  mensagens de novo antes de sair (`I3/geometria/publicacao.py`). Fora do contrato, nada é gravado
  nem publicado.
- **Compatibilidade:** `schema_version` MAJOR.MINOR. Campo novo é opcional e sobe MINOR; renomear,
  remover ou mudar tipo sobe MAJOR. Esta é a 1.0.

## Semântica

| campo | significado |
|---|---|
| `homography_px_to_m` | pixel do quadro **bruto** para metros no plano do chão de `space_id`; não vale para objetos no ar |
| `intrinsics`, `distortion` | focal e centro ótico em pixels, `[k1, k2, p1, p2, k3]`. Hoje a focal sai dos pontos do plano (uma vista), com centro no meio e distorção zero; quem mede fora do chão corrige as coordenadas com eles |
| `reference_frame` | `space_id` é o nome do sistema de mundo da instalação, o mesmo das zonas (câmeras do mesmo pátio compartilham o `space_id`); `origin` e `axes` descrevem o referencial em texto. Os três vêm da aplicação |
| `image_width`, `image_height` | resolução para a qual os parâmetros valem |
| `reprojection_rms_cm` | rms, em cm no plano, de pontos que não entraram no ajuste |
| `holdout_points` | quantos pontos mediram esse erro |
| `valid_from` | a partir de quando a calibração vale para `source_id` |
| `artifact_version` | versão da calibração; `artifact_id` no registro é `cal-<source_id>` |

## Operação

- Roda sob demanda: na instalação da câmera e sempre que ela se mexer. Não é serviço.
- **Ciclo de vida (6c):** grava no registro com o descritor comum (`artifact_id`,
  `artifact_version`, `kind`, `owner`, `uri`, `hash_sha256`, `valid_from`), anuncia em
  `ods.artifact.published` e publica o conteúdo em `ods.i3.calibration`, chave `source_id`.
- **Versão nunca muda:** a mesma versão com outro conteúdo é recusada. Com o mesmo conteúdo, a
  execução é idempotente e pode repetir o anúncio.
- Quem chega depois lê a calibração do registro, ou o tópico desde o começo.
- Erro de entrada (csv, imagem, data) sai com código 2 e a mensagem no stderr; falha de entrega no
  broker sai com erro.

## Teste

- Suíte em `I3/tests/`, no GitHub Actions a cada envio, com três instalações sintéticas (A8, A5,
  A4) além da quadra real.
- O "produtor falso" do I3 é o próprio CLI sobre um csv conhecido: determinístico e sem broker.
- Cenário gravado: a imagem mediana do vídeo do A4 (`dados/quadra_mediana.png`), com o erro medido
  de 1,43 cm como regressão.

## Build

- `Dockerfile` (`python:3.14-slim`), dependências fixas em `requirements.txt`: numpy, opencv headless,
  confluent-kafka e jsonschema.
- Configuração por aplicação: referencial (`--espaco`, `--origem`, `--eixos`), resolução, versão e
  registro. O broker vem de `--kafka`, sem endereço embutido.
