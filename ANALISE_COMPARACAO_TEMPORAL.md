# Análise: Comparação Temporal entre Épocas da Mesma Região

**Data:** 2026-09-08
**Pergunta investigada:** É possível comparar épocas diferentes da mesma região (ex.: eventos em 2018 vs. 2020 num mesmo município), e temos eventos de cidades/lugares diferentes em épocas diferentes?

**Resposta curta:** Sim — os dados suportam, o grafo suporta, mas o app hoje não faz. Faltam três ajustes pontuais no pipeline de recuperação.

---

## 1. Os dados suportam

Fonte: `data/processed/eventos_extremos_inmet.jsonl` — 33.501 eventos, cada um com `data` (YYYY-MM-DD), `estacao`, `tipo`, `valor`, `threshold`, `unidade`. Cobertura contínua 2015–2024.

### Distribuição por ano

| Ano | Eventos | Ano | Eventos |
|---|---|---|---|
| 2015 | 2.891 | 2020 | 4.860 |
| 2016 | 2.609 | 2021 | 2.734 |
| 2017 | 3.303 | 2022 | 2.397 |
| 2018 | 3.141 | 2023 | 3.308 |
| 2019 | 3.927 | 2024 | 4.331 |

### Distribuição ano × tipo de fenômeno

| Ano | Precip. extrema | Baixa umidade | Calor extremo | Frio extremo | Chuva muito forte |
|---|---|---|---|---|---|
| 2015 | 1.424 | 763 | 541 | 63 | 100 |
| 2016 | 1.587 | 379 | 184 | 328 | 131 |
| 2017 | 2.018 | 702 | 235 | 171 | 177 |
| 2018 | 1.961 | 677 | 157 | 182 | 164 |
| 2019 | 1.929 | 1.064 | 418 | 320 | 196 |
| 2020 | 1.899 | 1.309 | 823 | 624 | 205 |
| 2021 | 1.223 | 740 | 285 | 376 | 110 |
| 2022 | 1.609 | 353 | 112 | 159 | 164 |
| 2023 | 1.912 | 220 | 940 | 57 | 179 |
| 2024 | 2.116 | 1.160 | 649 | 186 | 220 |

### Recorte geográfico

Via `data/processed/estacoes_com_municipio.json` (774 estações → `municipio_id`, `municipio_nome`, `municipio_uf`):

- **566 municípios** distintos com pelo menos um evento
- **426 municípios** têm evento em 2018 **e** em 2020
- **178 municípios** têm evento em **todos os 10 anos** (série temporal completa)
- **522 municípios** com evento em ≥5 anos
- 1.471 eventos (4,4%) ficam sem município por estação não mapeada

### Exemplos concretos de comparação já verificados nos dados

**Cuiabá/MT — 2018 vs. 2020, por tipo:**

| Tipo | 2018 | 2020 |
|---|---|---|
| precipitação extrema | 8 | 0 |
| chuva muito forte | 0 | 0 |
| calor extremo | 1 | **28** |
| frio extremo | 0 | 0 |
| baixa umidade | 2 | 12 |

**Maiores variações 2018 → 2020** (municípios com ≥20 eventos somados):

| Município | 2018 | 2020 | Δ |
|---|---|---|---|
| Novo Repartimento/PA | 17 | 239 | +222 |
| Camamu/BA | 6 | 84 | +78 |
| Nova Maringá/MT | 6 | 62 | +56 |
| Alto Paraíso de Goiás/GO | 66 | 110 | +44 |
| Urubici/SC | 2 | 45 | +43 |
| Patos/PB | 140 | 4 | **−136** |
| Touros/RN | 67 | 0 | **−67** |
| Gilbués/PI | 61 | 1 | **−60** |

> As quedas mais extremas são artefato de cobertura de estação, não sinal climático. Ver Seção 4.

### Série temporal — municípios com maior volume

| Município | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Alto Paraíso de Goiás/GO | 5 | 26 | 60 | 66 | 68 | 110 | 136 | 0 | 3 | 2 | 476 |
| Urubici/SC | 18 | 57 | 39 | 2 | 27 | 45 | 34 | 32 | 27 | 53 | 334 |
| Novo Repartimento/PA | 6 | 0 | 9 | 17 | 4 | 239 | 29 | 1 | 0 | 4 | 309 |
| Patos/PB | 11 | 55 | 75 | 140 | 17 | 4 | 0 | 0 | 1 | 0 | 303 |
| Ibotirama/BA | 66 | 15 | 24 | 19 | 44 | 30 | 4 | 22 | 34 | 15 | 273 |
| Oeiras/PI | 35 | 30 | 16 | 11 | 27 | 4 | 0 | 14 | 44 | 31 | 212 |
| Cuiabá/MT | 13 | 4 | 3 | 11 | 7 | 40 | 28 | 2 | 38 | 50 | 196 |
| Quaraí/RS | 10 | 20 | 12 | 14 | 25 | 15 | 12 | 21 | 19 | 23 | 171 |

---

## 2. O grafo já está pronto

- `src/data/06_carga_neo4j.py` grava `evento.data = date($data)` — tipo `date` nativo do Neo4j, não string. Comparação e extração de ano funcionam direto em Cypher.
- **Todas** as queries em `src/app/graph/queries.ts` já expõem `$data_inicio` / `$data_fim`.
- O caminho `(Municipio)-[:SOFREU]->(Evento)-[:CAUSADO_POR]->(Fenomeno)` permite agregar por município, ano e fenômeno numa única passada.

A infraestrutura de filtro temporal existe e funciona. Falta usá-la **duas vezes** (uma por janela) e agregar.

---

## 3. O que impedia — três pontos, todos corrigidos

> **Status:** implementado. As três correções desta seção estão no código; o
> benchmark que as exercita está descrito em `BENCHMARK.md`.

### (a) O extrator de entidades só extrai UM período

`src/app/pipeline/entityExtractor.ts:28-36` define `periodo_inicio` e `periodo_fim` como escalares:

```ts
periodo_inicio: z.string().nullable().describe("Data de início no formato YYYY-MM-DD"),
periodo_fim: z.string().nullable().describe("Data de fim no formato YYYY-MM-DD"),
```

Perguntar *"compare Cuiabá em 2018 com 2020"* colapsa num único intervalo `2018-01-01 → 2020-12-31`, que **soma** os dois anos em vez de compará-los.

**Correção:** trocar por uma lista de janelas nomeadas:

```ts
periodos: z.array(z.object({
  inicio: z.string(),
  fim: z.string(),
  rotulo: z.string(),   // ex.: "2018"
})).describe("Uma janela por período mencionado; duas ou mais quando a pergunta for comparativa")
```

### (b) Não existe query de agregação por ano

As queries atuais retornam eventos individuais (`ORDER BY e.data DESC LIMIT 30`) ou ranking de municípios. Falta uma agregação temporal:

```cypher
// comparativoTemporal
MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
WHERE toLower(m.nome) CONTAINS toLower($nome)
  AND ($tipo IS NULL OR e.tipo = $tipo)
  AND e.data.year IN $anos
RETURN e.data.year AS ano, f.nome AS fenomeno,
       count(e) AS total, round(avg(e.valor), 2) AS valor_medio,
       max(e.valor) AS valor_max
ORDER BY ano, total DESC
```

Essa é **exatamente** a classe de consulta que o VectorRAG não resolve — similaridade semântica não agrega nem contrasta janelas temporais. Reforça o argumento central do paper (context_recall 0,00 do baseline vetorial) com um caso ainda mais forte que o ranking do Q1.

### (c) Bug latente: janela padrão ancorada em `new Date()`

`src/app/graph/retriever.ts:11`:

```ts
const PERIODO_PADRAO_ANOS = 2;
```

A janela padrão é calculada a partir de **hoje**. Como a data corrente já passou de 2026 e os dados terminam em 2024-12-31, qualquer pergunta sem data explícita cai numa faixa de poucos meses no fim de 2024 — ou em faixa vazia.

Isso é provavelmente a causa real do artefato registrado no Q1 da avaliação ("seção de ranking correta mas dominada por eventos individuais de 2024").

**Correção:** ancorar na data máxima do grafo (`MATCH (e:Evento) RETURN max(e.data)`) ou usar toda a série como padrão quando a pergunta não trouxer recorte temporal.

---

## 4. Ressalva metodológica — cobertura de estações

Os eventos são **excedências de limiar**, contados sem denominador. O número de estações que reportam ao menos um evento varia bastante por ano:

| Ano | Estações | Ano | Estações |
|---|---|---|---|
| 2015 | 431 | 2020 | 503 |
| 2016 | 458 | 2021 | **385** |
| 2017 | 494 | 2022 | 441 |
| 2018 | 519 | 2023 | 477 |
| 2019 | **536** | 2024 | 486 |

Entre 2018 e 2020: **444 estações em comum**, 75 exclusivas de 2018, 59 exclusivas de 2020.

Em `estacoes_com_municipio.json`, **190 das 774 estações** estão com `CD_SITUACAO: "Pane"`. É por isso que Patos/PB "cai" de 140 para 4 eventos — sensor fora de operação, não mudança climática. Sem tratar isso, uma comparação 2018 vs. 2020 mede disponibilidade de instrumento tanto quanto clima.

### Duas saídas

1. **Restringir aos pares comuns** — comparar apenas estações presentes nas duas janelas (444 no exemplo). Barato de implementar, resolve o grosso do viés. Em Cypher: exigir que a estação tenha registro em ambos os anos antes de agregar.

2. **Normalizar pelo denominador** — contar dias com observação válida por estação/ano nos CSVs do INMET e reportar taxa (`eventos / dias observados`) em vez de contagem bruta. Exige alterar `src/data/03_historico_inmet.py` para emitir também a contagem de dias válidos por estação/ano.

**Recomendação:** implementar (1) no código e declarar (2) como limitação na Seção V do paper. Isso fortalece o trabalho em vez de enfraquecê-lo — mostra consciência do viés de amostragem.

---

## 5. O que foi implementado

1. `src/app/pipeline/entityExtractor.ts` — `periodos[]` (janelas com rótulo) no lugar dos escalares, mais as flags `comparativa` e `intencao`. O prompt distingue **intervalo contínuo** ("entre 2020 e 2024" = uma janela) de **épocas contrastadas** ("2018 ou 2020" = duas janelas) — sem essa distinção, um intervalo virava comparação e o roteamento errava.
2. `src/app/graph/queries.ts` — `comparativoTemporalMunicipio`, `comparativoTemporalEstado` (agregam por `e.data.year`), `coberturaEstacoesPorAno`, `sazonalidadePorEstado`, `extremoPorEstado`, `contagemPorEstado`, `contagemPorMunicipio`.
3. `src/app/graph/retriever.ts` — itera sobre as janelas; janela padrão ancorada em `min/max(e.data)` do grafo; preenche com zero os anos sem registro (senão "0 em 2022" nunca aparece no contexto, porque `count` não devolve linha onde não há evento); descarta de `municipios` nomes que são estados; não puxa o estado inteiro quando o município já respondeu.
4. `src/app/graph/client.ts` — converte `Integer`/`Date` do driver Neo4j para valores nativos. Sem isso o contexto ia para o LLM com `{"low":227,"high":0}` no lugar de `227`.
5. `src/app/pipeline/contextBuilder.ts` — seções com títulos em português e colunas ordenadas, para o gerador não tratar uma contagem agregada como lista de eventos.
6. `src/evaluation/build_benchmark.py` — 70 perguntas em 7 categorias, 12 delas de comparação temporal, com gabaritos derivados do JSONL de origem. Ver `BENCHMARK.md`.
