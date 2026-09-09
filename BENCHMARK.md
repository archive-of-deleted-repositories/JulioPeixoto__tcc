# Benchmark de Avaliação — GraphRAG vs. VectorRAG vs. No RAG

Documento de metodologia do conjunto de avaliação. Substitui as 5 perguntas
originais por **70 perguntas em 7 categorias**, com gabaritos derivados dos dados
de origem e julgamento por decomposição em afirmações.

São avaliados **quatro** modos: No RAG, VectorRAG ingênuo, VectorRAG com
pré-filtragem por metadados (baseline forte) e GraphRAG. O baseline forte existe
para que a comparação não meça esforço de engenharia — ver §5.

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

### Dois baselines vetoriais

`vectorRag.ts` (ingênuo) usa `asRetriever({ k: 10 })` puro e **ignora os
metadados que a própria indexação gravou** (`uf`, `tipo`, `ano`, `municipio`,
`estacao`). Comparar o GraphRAG só contra isso mediria, em parte, "recuperação
projetada para a tarefa" contra "top-k sem engenharia".

`vectorRagFiltrado.ts` (forte) usa as **mesmas entidades extraídas** que o
GraphRAG recebe para filtrar o corpus *antes* de ranquear, via
`vector.similarity.cosine` sobre o subconjunto sobrevivente. Filtrar depois de
ranquear seria inútil — o top-k global já teria descartado o que interessa.
`k=10` mantido, para isolar o efeito do filtro.

Os dois modos compartilham com o GraphRAG: extração de entidades, prompt de
geração, modelo gerador e **normalização geográfica** (`pipeline/geo.ts`). Esta
última importa: o extrator devolve "Bahia" no campo de município, e aplicar a
correção só ao GraphRAG penalizaria o baseline por um defeito da extração
compartilhada, não da sua arquitetura.

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
reamostragens, seed 42). Coluna *p*: permutação pareada GraphRAG vs. **baseline
forte** (Vector+F).

**Vector** = top-k puro, sem usar metadados.
**Vector+F** = pré-filtragem por metadados + ranqueamento. Recebe as mesmas
entidades extraídas, o mesmo prompt e a mesma normalização geográfica do
GraphRAG — existe para que a comparação não meça esforço de engenharia.

| Métrica | No RAG | Vector | Vector+F | GraphRAG | p |
|---|---|---|---|---|---|
| faithfulness | — | 0,716 | 0,825 | **0,932** | 0,0220 |
| answer_relevancy | 0,799 | 0,802 | 0,858 | **0,878** | 0,0097 |
| answer_correctness | 0,040 | 0,160 | 0,222 | **0,664** | <0,0001 |
| context_recall | — | 0,223 | 0,270 | **0,886** | <0,0001 |
| **context_precision** | — | 0,431 | **0,656** | 0,504 | **0,0142** |
| cobertura_fatos | 0,301 | 0,273 | 0,312 | **0,737** | <0,0001 |
| abstenção correta (C7) | 1,000 | 1,000 | 1,000 | 1,000 | — |

### Por categoria — answer_correctness

| Categoria | n | No RAG | Vector | Vector+F | GraphRAG |
|---|---|---|---|---|---|
| C1 factual | 10 | 0,000 | 0,033 | 0,167 | **0,367** |
| C2 agregação | 10 | 0,043 | 0,029 | 0,029 | **0,640** |
| C3 comp. temporal | 12 | 0,000 | 0,096 | 0,181 | **0,792** |
| C4 comp. geográfica | 10 | 0,000 | 0,078 | 0,183 | **1,000** |
| C5 sazonalidade | 10 | 0,000 | 0,194 | 0,138 | **0,703** |
| C6 multi-hop | 10 | 0,040 | 0,000 | 0,073 | **0,337** |
| C7 nulas | 8 | 0,250 | 0,833 | **0,938** | 0,812 |

### Por categoria — context_recall

| Categoria | n | Vector | Vector+F | GraphRAG |
|---|---|---|---|---|
| C1 factual | 10 | 0,500 | 0,617 | **0,733** |
| C2 agregação | 10 | 0,067 | 0,087 | **0,917** |
| C3 comp. temporal | 12 | 0,132 | 0,215 | **1,000** |
| C4 comp. geográfica | 10 | 0,000 | 0,025 | **0,955** |
| C5 sazonalidade | 10 | 0,000 | 0,000 | **1,000** |
| C6 multi-hop | 10 | 0,033 | 0,100 | **0,600** |
| C7 nulas | 8 | **1,000** | **1,000** | **1,000** |

### Leitura

**1. Armar o baseline custou pouco ao GraphRAG.** A pré-filtragem rendeu ao
vetorial +6,3 p.p. de correção (p=0.011) e
+4,7 p.p. de abrangência (p=0.0054). Ou seja, só cerca de
um oitavo da vantagem originalmente medida vinha de o baseline ignorar seus
próprios metadados; o resto é arquitetural.

**2. Em agregação (C2) o filtro rendeu exatamente zero** — 0,029 nos dois
baselines, context_recall 0,067 → 0,087, contra 0,917 do GraphRAG. Filtrar
perfeitamente não aproxima da resposta quando a operação exigida é ordenar por
contagem. Em C5 o filtro chegou a **piorar** (0,194 → 0,138): restringir a 10
documentos uma pergunta sobre a distribuição mensal de 10 anos é
contraproducente.

**3. O GraphRAG PERDE em context_precision** — 0,504 contra 0,656 do baseline
forte (p=0,014). O contexto do grafo traz totais, ranking, extremos e
sazonalidade; nem toda seção serve a toda pergunta. O baseline devolve 10
documentos já restritos ao escopo. É o custo de recuperar as agregações
incondicionalmente, escolha feita porque o roteamento por intenção via LLM se
mostrou instável. É a otimização mais evidente a fazer.

**4. A métrica sem LLM concorda com o juiz.** cobertura_fatos (0,737 vs 0,312)
reproduz o ordenamento de answer_correctness (0,664 vs 0,222).

### Caso ilustrativo (C3_comp_temporal-06)

*"Em Pão de Açúcar (AL), houve mais registros de baixa umidade crítica em 2023 ou
em 2024?"* — gabarito: 70 em 2023, 0 em 2024.

- **Vector**: *"Em 2023, houve **10 registros**"* ❌
- **Vector+F**: *"Em 2023, houve um total de **10 registros**"* ❌ — filtro
  aplicado corretamente, **mesmo erro, mesmo número**
- **GraphRAG**: *"**70 casos** em 2023. Em 2024, não houve registros"* ✓

O 10 é o `k` do retriever. Que o modo pré-filtrado erre igual, com o filtro
funcionando, é a evidência mais limpa de que o problema não é *quais* documentos
são recuperados — é recuperar **documentos** quando a pergunta pede um
**agregado**. Aumentar `k` só troca um número errado por outro.

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
4. **Configurações vetoriais mais elaboradas não foram testadas.** O baseline
   forte usa pré-filtragem + top-k. Busca híbrida com BM25, *reranking*, ou uma
   camada de agregação sobre os documentos recuperados poderiam estreitar a
   diferença — sobretudo esta última, que atacaria a limitação estrutural
   identificada em §6.

5. **Sem denominador de observação.** Os eventos são excedências de limiar sem a
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
