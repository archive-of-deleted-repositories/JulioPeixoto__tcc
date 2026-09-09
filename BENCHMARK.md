# Benchmark de Avaliação — GraphRAG vs. VectorRAG vs. No RAG

Documento de metodologia do conjunto de avaliação. Substitui as 5 perguntas
originais por **70 perguntas em 7 categorias**, com gabaritos derivados dos dados
de origem e julgamento por decomposição em afirmações.

---

## 1. Por que 5 perguntas era pouco

Três problemas, em ordem de gravidade.

### 1.1 Circularidade no ground truth

`src/evaluation/derive_gabaritos.py` derivava os gabaritos **executando Cypher no
mesmo Neo4j que o pipeline GraphRAG consulta**. O gabarito passava a ser, por
construção, aquilo que o GraphRAG recupera. Isso infla `context_recall` do
GraphRAG — o contexto cobre o gabarito porque ambos saíram da mesma query.

Agora o ground truth vem de `data/processed/eventos_extremos_inmet.jsonl`, o
arquivo que alimenta a carga do grafo, através de
`src/evaluation/build_benchmark.py`. Os três modos são julgados contra uma
verdade externa ao motor de recuperação avaliado.

### 1.2 Potência estatística

Com n=5 e métricas em [0,1], qualquer diferença abaixo de ~0,3 é indistinguível
de ruído. A literatura de avaliação de RAG trabalha com 100–200 amostras, e
recomenda validação humana em 20–50 para aferir a confiabilidade do juiz. 70
perguntas com IC bootstrap é um meio-termo defensável para um TCC: suficiente
para separar efeitos grandes, honesto quanto aos pequenos.

### 1.3 Cobertura de tipos de consulta

As 5 perguntas originais eram todas agregativas ou de listagem — justamente onde
o GraphRAG ganha. Sem perguntas factuais simples nem perguntas sem resposta, o
benchmark não mostrava onde o GraphRAG **não** ajuda, o que enfraquece a
comparação.

---

## 2. Taxonomia

Adaptada de MultiHop-RAG (Tang & Yang, 2024) — que divide consultas em
*inference*, *comparison*, *temporal* e *null* — e de "RAG vs. GraphRAG: A
Systematic Evaluation" (Han et al., 2025), acrescida das categorias agregativas
próprias do domínio climático.

| Categoria | n | O que mede | Expectativa |
|---|---|---|---|
| `C1_factual` | 10 | Lookup single-hop: houve fenômeno X em município Y no ano Z? | VectorRAG competitivo — é busca por similaridade pura |
| `C2_agregacao` | 10 | Ranking dos 5 municípios com mais registros | GraphRAG, exige contagem |
| `C3_comp_temporal` | 12 | Mesma região, épocas diferentes (2018 vs. 2020) | GraphRAG, exige duas janelas + contraste |
| `C4_comp_geografica` | 10 | Mesma época, dois estados | GraphRAG, exige duas agregações |
| `C5_sazonalidade` | 10 | Em que meses o fenômeno se concentra | GraphRAG, agregação por mês |
| `C6_multi_hop` | 10 | Estação → município → estado + valor extremo | GraphRAG, travessia de 2 saltos |
| `C7_nula` | 8 | Perguntas sem resposta na base | Mede **alucinação**, não recuperação |

Metade de `C1_factual` tem resposta negativa, para que responder "sim" sempre não
produza acerto. As perguntas de `C7_nula` vêm de duas fontes: fenômenos previstos
no esquema mas sem eventos carregados (enchente, deslizamento, seca, granizo,
vendaval — dependiam do CEMADEN, nunca processado), e combinações
(UF, fenômeno, ano) com zero registros em estado que tem cobertura de estação
naquele ano.

---

## 3. Construção dos gabaritos

`src/evaluation/build_benchmark.py`, seed fixa 42, reprodutível.

Cada item carrega:

```json
{
  "id": "C3_comp_temporal-01",
  "categoria": "C3_comp_temporal",
  "pergunta": "Em Novo Repartimento (PA), houve mais registros de baixa umidade crítica em 2020 ou em 2022? ...",
  "gabarito": "Em Novo Repartimento (PA), 2020 teve mais registros ... 227 registros em 2020 contra 0 em 2022 ...",
  "fatos_chave": ["227", "0", "2020", "Novo Repartimento"],
  "metadados": { "municipio": "...", "total_1": 227, "total_2": 0, "estacoes": ["A248"] }
}
```

`fatos_chave` sustenta uma métrica determinística (§5) que não passa por juiz LLM.

### Validação

62 dos 70 itens foram reconferidos por uma recontagem independente direta do
JSONL, escrita separadamente do gerador: **zero divergências**. Os 8 restantes
são as perguntas nulas, verdadeiras por construção.

### O gabarito contém apenas o que uma resposta afirmaria

Cada item tem dois campos textuais: `gabarito` (avaliado) e `nota` (não avaliado).

Isso não era assim na primeira rodada, e o erro custou uma re-execução. Eu
concatenava a procedência — *"Base de referência: eventos extremos derivados das
séries horárias do INMET (2015–2024)"* — ao fim de todo gabarito. Como o juiz
decompõe o gabarito em afirmações e procura cada uma na resposta, essa frase
entrava como 1–2 afirmações que **nenhuma resposta produziria**, rebaixando
`answer_correctness` de todos os modos — e de forma desigual, já que as nulas,
de gabarito curto, eram proporcionalmente mais punidas.

Efeito medido ao remover (mesmas respostas, só o gabarito mudou):

| | antes | depois |
|---|---|---|
| answer_correctness GraphRAG | 0,367 | 0,549 |
| context_recall GraphRAG | 0,602 | 0,879 |

Regra que ficou: **no `gabarito`, só afirmações verificáveis na resposta**.
Procedência, ressalvas metodológicas e explicações de por que um dado falta vão
para `nota`.

### Controle de cobertura de estações em C3

As comparações temporais só são geradas quando **o conjunto de estações do
município com registros é o mesmo nos dois anos**. Sem esse filtro, quedas como
Patos/PB (140 registros em 2018 → 4 em 2020) entrariam no benchmark como se
fossem sinal climático, quando são estação em pane. Ver
`ANALISE_COMPARACAO_TEMPORAL.md`, seção 4.

Vale registrar o enquadramento: este é um benchmark de **recuperação**, não um
estudo climatológico. As perguntas são sobre o que consta na base do INMET, e a
resposta correta é o que a base diz.

---

## 4. Correção no grafo descoberta durante a construção

Ao conferir o Neo4j antes de rodar, o grafo tinha **67.531 nós `:Evento` para
33.501 eventos reais**.

Causa: `Neo4jVectorStore.fromTexts` do LangChain **cria nós novos** — não anexa
embeddings aos existentes. Como a configuração apontava para `nodeLabel:
"Evento"`, cada reindexação despejava mais uma cópia órfã de cada evento dentro
do mesmo label do grafo. Eram 34.030 nós sem nenhuma aresta (2.000 da primeira
indexação com `LIMIT 2000` + 32.030 da reindexação posterior).

Efeito real:

- **GraphRAG não era afetado.** Todas as suas queries navegam por
  `(m:Municipio)-[:SOFREU]->(e:Evento)`, e os órfãos não tinham arestas.
- **VectorRAG não era sabotado.** Os órfãos carregavam a descrição textual
  correta, então o corpus tinha o conteúdo certo — com ~2.000 duplicatas.
- **Contagens diretas ficavam erradas.** Qualquer `MATCH (e:Evento) RETURN
  count(e)` retornava o dobro.

Correção: o corpus vetorial passou para o label próprio `:EventoIndexado`
(`src/app/baseline/vectorRag.ts`), os órfãos foram removidos e o índice
reconstruído. `:Evento` voltou a 33.501.

---

## 5. Métricas

| Métrica | Como é calculada |
|---|---|
| `faithfulness` | Resposta quebrada em afirmações atômicas; fração sustentada pelo contexto |
| `answer_correctness` | Gabarito quebrado em afirmações; fração presente na resposta |
| `context_recall` | Gabarito quebrado em afirmações; fração coberta pelo contexto recuperado |
| `context_precision` | Contexto dividido em blocos; fração relevante à pergunta |
| `answer_relevancy` | Coseno entre embeddings da pergunta e da resposta |
| `cobertura_fatos` | **Sem LLM** — fração dos `fatos_chave` presentes na resposta |
| `abstencao_correta` | Só em C7: a resposta declarou ausência de dados em vez de inventar? |

### Por que decomposição em afirmações

A versão anterior pedia ao juiz "responda apenas um número de 0 a 1". Notas
holísticas de LLM são mal calibradas e pouco reprodutíveis; scoring por
afirmação correlaciona melhor com julgamento humano. Além disso o juiz agora
responde em **JSON estruturado**, o que elimina o parsing por regex que antes
podia devolver `NaN` silenciosamente.

### Por que uma métrica determinística

`cobertura_fatos` não passa por juiz nenhum. Se ela e as métricas de LLM
apontarem na mesma direção, o resultado é mais confiável; se divergirem, é sinal
de viés do juiz. Serve de âncora.

### Prompt único para os dois modos

VectorRAG e GraphRAG compartilham o prompt de geração (`src/app/baseline/prompt.ts`).

Também não era assim no início: cada um herdava um texto do seu próprio módulo.
Prompts diferentes entre os arms são um confundidor — parte da diferença medida
seria efeito do texto, não da arquitetura. Ao unificar, acrescentei a instrução
de citar os números concretos do contexto, que vale igualmente para os dois:
o benchmark tinha exposto que em `C1_factual` o contexto do GraphRAG trazia
`total de registros: 15` e o gerador respondia só *"Sim, houve registros"* —
recuperação certa, resposta pobre.

### Estatística

- **IC 95% por bootstrap** (10.000 reamostragens, seed 42) em toda média.
- **Teste de permutação pareado** para GraphRAG vs. VectorRAG. Pareado porque os
  dois modos respondem às mesmas perguntas: a variância entre perguntas é muito
  maior que entre modos, e ignorar o pareamento mascara o efeito.
- **Recorte por categoria**, porque a média global esconde onde cada arquitetura
  ganha ou perde — que é o resultado interessante.

---

## 6. Resultados

70 perguntas, juiz GPT-4o-mini, gerador GPT-4o. IC 95% por bootstrap (10.000
reamostragens, seed 42). Coluna *p*: teste de permutação pareado GraphRAG vs.
VectorRAG.

| Métrica | No RAG | VectorRAG | GraphRAG | p |
|---|---|---|---|---|
| faithfulness | — | 0,689 [0,59–0,78] | **0,928** [0,88–0,97] | <0,0001 |
| answer_relevancy | 0,801 [0,78–0,82] | 0,784 [0,74–0,82] | **0,878** [0,86–0,89] | <0,0001 |
| answer_correctness | 0,051 [0,01–0,10] | 0,185 [0,11–0,26] | **0,659** [0,59–0,73] | <0,0001 |
| context_recall | — | 0,212 [0,13–0,30] | **0,890** [0,83–0,94] | <0,0001 |
| context_precision | — | 0,444 [0,35–0,54] | 0,518 [0,46–0,58] | 0,1462 |
| cobertura_fatos | 0,312 [0,25–0,37] | 0,273 [0,22–0,33] | **0,733** [0,66–0,81] | <0,0001 |
| abstenção correta (só C7) | 1,000 | 1,000 | 1,000 | — |

### Por categoria

| Categoria | n | \_ac\_ No RAG | Vector | Graph | \_cr\_ Vector | Graph |
|---|---|---|---|---|---|---|
| C1 factual | 10 | 0,033 | 0,117 | **0,333** | 0,500 | **0,700** |
| C2 agregação | 10 | 0,000 | 0,014 | **0,552** | 0,064 | **0,917** |
| C3 comp. temporal | 12 | 0,000 | 0,167 | **0,812** | 0,132 | **1,000** |
| C4 comp. geográfica | 10 | 0,000 | 0,050 | **1,000** | 0,000 | **1,000** |
| C5 sazonalidade | 10 | 0,000 | 0,166 | **0,707** | 0,029 | **1,000** |
| C6 multi-hop | 10 | 0,025 | 0,000 | **0,327** | 0,000 | **0,617** |
| C7 nulas | 8 | 0,375 | **0,938** | 0,896 | 0,917 | **1,000** |

*ac* = answer_correctness, *cr* = context_recall.

### Leitura

1. **A vantagem é relacional, não geral.** Em C4 e C3 o VectorRAG tem
   `context_recall` de 0,000 e 0,132 — o contexto por similaridade praticamente
   não contém o necessário. Em C1 (fato único) sobe para 0,500 e a diferença
   encolhe. Coerente com Han et al. (2025): RAG vetorial é competitivo em
   single-hop detalhado.

2. **`context_precision` é o único empate** (p=0,15, ICs sobrepostos). O contexto
   do grafo traz várias seções agregadas e nem todas servem a cada pergunta.

3. **A métrica sem LLM concorda com a julgada por LLM.** `cobertura_fatos` (0,733
   vs 0,273) reproduz o ordenamento de `answer_correctness` (0,659 vs 0,185).
   Convergência entre determinística e LLM enfraquece a hipótese de viés do juiz.

4. **Ninguém alucinou nas nulas.** Abstenção correta 1,000 nos três modos.

### Caso ilustrativo (C3_comp_temporal-06)

*"Em Pão de Açúcar (AL), houve mais registros de baixa umidade crítica em 2023 ou
em 2024?"* — gabarito: 70 em 2023, 0 em 2024.

- **VectorRAG**: *"Em 2023, houve um total de **10 registros**"* — errado, e o 10 é
  exatamente o `k` do retriever. O modelo descreveu **quantos documentos recebeu**
  como se fosse a contagem de eventos. Note que `faithfulness` = 1,00 nesse item:
  ele foi fiel ao contexto e ainda assim produziu um fato falso. Recuperação por
  similaridade entrega uma *amostra*; amostra não responde pergunta de contagem, e
  aumentar `k` só troca um número errado por outro.
- **GraphRAG**: *"70 casos em 2023, enquanto em 2024 não houve registros"* — correto.

---

## 7. Como rodar

```bash
# 0. Neo4j de pé
make up

# 1. (só se o grafo estiver vazio) carga — agora em lotes UNWIND de 1000
.venv/Scripts/python.exe src/data/06_carga_neo4j.py

# 2. (só se o índice vetorial não existir) corpus do baseline
bun run src/evaluation/reindex.ts

# 3. gerar o benchmark a partir dos dados de origem
.venv/Scripts/python.exe src/evaluation/build_benchmark.py

# 4. rodar os três modos (use argumentos para filtrar categorias)
bun run src/evaluation/run_eval.ts
bun run src/evaluation/run_eval.ts C3 C7     # só comparação temporal e nulas

# 5. julgar e consolidar
.venv/Scripts/python.exe src/evaluation/ragas_eval.py
```

Saídas em `data/evaluation/`: `benchmark.json`, `respostas_brutas.json`,
`ragas_scores.json` (geral + significância + por categoria),
`ragas_scores_por_pergunta.json`.

---

## 8. Limitações

1. **Juiz e gerador da mesma família.** GPT-4o gera, GPT-4o-mini julga. Há risco
   de viés de auto-preferência. `cobertura_fatos` existe justamente como
   contrapeso — e de fato concordou com o juiz (§6). Validação humana em uma
   amostra reduziria mais a dúvida.
2. **70 perguntas ainda é modesto** para diferenças pequenas. Os IC bootstrap
   deixam isso explícito em vez de esconder.
3. **Perguntas geradas por template.** Ganha-se gabarito exato e escala; perde-se
   a variedade linguística de perguntas reais de usuário. Um trabalho futuro
   natural é parafrasear cada pergunta em 2–3 formulações e medir a sensibilidade
   das métricas ao fraseado.
4. **Sem denominador de observação.** Os eventos são excedências de limiar sem a
   contagem de dias válidos por estação. Isso limita a interpretação
   climatológica, não a de recuperação.

---

## Referências

- Tang & Yang (2024). *MultiHop-RAG: Benchmarking Retrieval-Augmented Generation
  for Multi-Hop Queries.* — taxonomia inference/comparison/temporal/null.
- Han et al. (2025). *RAG vs. GraphRAG: A Systematic Evaluation and Key Insights.*
  arXiv:2502.11371 — GraphRAG vence em multi-hop, comparação e temporal; RAG
  vetorial vence em single-hop detalhado.
- Es et al. (2023). *RAGAS: Automated Evaluation of Retrieval Augmented
  Generation.* — decomposição em afirmações para faithfulness.
- RAGChecker / literatura de LLM-as-judge — scoring por afirmação correlaciona
  melhor com julgamento humano do que nota holística.
