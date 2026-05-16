# Plano de Implementação — GraphRAG Climático

> Arquitetura híbrida: Python para ingestão de dados + Bun/LangChain JS para pipeline GraphRAG e interface

---

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 1 — INGESTÃO (Python)                               │
│  INMET ZIP/API/RSS + CEMADEN PDFs → Neo4j                   │
│  Scripts src/python/ (conforme PLANO_DADOS.md)              │
└───────────────────────┬─────────────────────────────────────┘
                        │ bolt://localhost:7687
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  NEO4J — Grafo de Conhecimento Climático                    │
│  ~60k nós, ~210k arestas                                    │
│  Nós: Estacao, Municipio, Estado, Evento, Fenomeno          │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 2 — GRAPHRAG PIPELINE (Bun + LangChain JS)          │
│  Query → Entity extraction → Graph traversal → LLM → Answer│
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 3 — INTERFACE (Bun + Hono)                          │
│  API REST + frontend conversacional                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Stack Técnico

### Ingestão (Python 3.11+)

| Pacote | Uso |
|---|---|
| `requests` | Download APIs e PDFs |
| `pandas` | Parsing CSVs INMET (latin-1, sep=`;`) |
| `pdfplumber` | Extração de texto dos boletins CEMADEN |
| `feedparser` | Parsing RSS INMET |
| `beautifulsoup4` | HTML dentro do RSS |
| `rapidfuzz` | Fuzzy match de nomes de municípios |
| `scipy` | KDTree para geocodificação por proximidade |
| `anthropic` | Extração de entidades dos PDFs via LLM |
| `neo4j` | Driver Python para carga no grafo |
| `tqdm` | Progresso nos loops de download |

```bash
pip install requests pandas pdfplumber feedparser beautifulsoup4 \
            rapidfuzz scipy anthropic neo4j tqdm
```

### GraphRAG Pipeline + Interface (Bun)

| Pacote | Uso |
|---|---|
| `langchain` | Core do pipeline RAG |
| `@langchain/anthropic` | Claude como LLM gerador |
| `@langchain/community` | Neo4jGraph, Neo4jVectorStore |
| `neo4j-driver` | Conexão direta ao Neo4j |
| `hono` | Servidor HTTP leve (nativo Bun) |
| `ai` | Vercel AI SDK — streaming de respostas |
| `@ai-sdk/anthropic` | Provider Claude para streaming |
| `zod` | Validação de schemas de entrada |

```bash
bun add langchain @langchain/anthropic @langchain/community \
        neo4j-driver hono ai @ai-sdk/anthropic zod
```

---

## Estrutura de Diretórios

```
tcc/
├── data/
│   ├── raw/
│   │   ├── ibge_municipios.json
│   │   ├── ibge_estados.json
│   │   ├── estacoes_automaticas.json
│   │   ├── estacoes_convencionais.json
│   │   ├── inmet_historico/        ← ZIPs extraídos por ano
│   │   └── cemaden_pdfs/           ← ~60 PDFs mensais
│   └── processed/
│       ├── municipios_centroides.csv
│       ├── estacoes_com_municipio.json
│       ├── eventos_extremos_inmet.jsonl
│       ├── alertas_inmet.jsonl
│       └── eventos_cemaden.jsonl
│
├── src/
│   ├── python/                     ← CAMADA 1: Ingestão
│   │   ├── 01_ibge.py
│   │   ├── 02_estacoes.py
│   │   ├── 03_historico_inmet.py
│   │   ├── 04_alertas_rss.py
│   │   ├── 05_cemaden_pdfs.py
│   │   └── 06_carga_neo4j.py
│   │
│   └── graphrag/                   ← CAMADA 2 + 3: Pipeline e Interface
│       ├── graph/
│       │   ├── client.ts           ← conexão Neo4j
│       │   ├── queries.ts          ← queries Cypher reutilizáveis
│       │   └── retriever.ts        ← graph traversal → contexto
│       ├── pipeline/
│       │   ├── entityExtractor.ts  ← LLM extrai entidades da pergunta
│       │   ├── graphRetriever.ts   ← busca subgrafo relevante
│       │   ├── contextBuilder.ts   ← monta contexto para o LLM
│       │   └── generator.ts        ← gera resposta final (streaming)
│       ├── baseline/
│       │   └── vectorRag.ts        ← RAG vetorial para comparação RAGAS
│       ├── evaluation/
│       │   └── ragas.ts            ← integração com RAGAS
│       ├── api/
│       │   └── index.ts            ← servidor Hono com rotas
│       ├── frontend/
│       │   └── index.html          ← interface conversacional simples
│       └── index.ts                ← entrypoint
```

---

## Fases de Implementação

### Fase 1 — Infraestrutura (Semana 1)

- [ ] Instalar e configurar **Neo4j** local (Docker recomendado)
- [ ] Rodar os scripts Python de ingestão (etapas 1–6 do `PLANO_DADOS.md`)
- [ ] Validar grafo no Neo4j Browser: contagem de nós e arestas
- [ ] Inicializar projeto Bun: `bun init` em `src/graphrag/`
- [ ] Configurar variáveis de ambiente (`.env`)

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=senha
ANTHROPIC_API_KEY=sk-...
```

---

### Fase 2 — Conexão com o Grafo (Semana 1–2)

**`graph/client.ts`** — driver Neo4j singleton:

```typescript
import neo4j from "neo4j-driver";

const driver = neo4j.driver(
  process.env.NEO4J_URI!,
  neo4j.auth.basic(process.env.NEO4J_USER!, process.env.NEO4J_PASSWORD!)
);

export async function runQuery(cypher: string, params: Record<string, unknown> = {}) {
  const session = driver.session();
  try {
    const result = await session.run(cypher, params);
    return result.records.map((r) => r.toObject());
  } finally {
    await session.close();
  }
}
```

**`graph/queries.ts`** — queries Cypher centralizadas:

```typescript
export const QUERIES = {
  eventosPorMunicipio: `
    MATCH (m:Municipio {nome: $nome})-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    RETURN e.tipo, e.data, e.descricao, f.nome AS fenomeno
    ORDER BY e.data DESC LIMIT 20
  `,
  estacoesPorEstado: `
    MATCH (e:Estacao)-[:PERTENCE_A]->(m:Municipio)-[:PERTENCE_A]->(est:Estado {sigla: $sigla})
    RETURN e.codigo, e.nome, e.lat, e.lon
  `,
  municipiosComMaisEventos: `
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno {nome: $fenomeno})
    WHERE e.data >= $data_inicio AND e.data <= $data_fim
    RETURN m.nome, m.uf, count(e) AS total
    ORDER BY total DESC LIMIT 10
  `,
};
```

---

### Fase 3 — Pipeline GraphRAG (Semana 2–3)

#### Fluxo de uma pergunta

```
Pergunta do usuário
      ↓
entityExtractor.ts   ← LLM identifica: municípios, estados, tipos de evento, período
      ↓
graphRetriever.ts    ← constrói e executa queries Cypher com as entidades extraídas
      ↓
contextBuilder.ts    ← converte registros do grafo em texto estruturado
      ↓
generator.ts         ← LLM gera resposta fundamentada no contexto (com streaming)
      ↓
Resposta ao usuário
```

**`pipeline/entityExtractor.ts`**:

```typescript
import { anthropic } from "@ai-sdk/anthropic";
import { generateObject } from "ai";
import { z } from "zod";

const EntidadesSchema = z.object({
  municipios: z.array(z.string()),
  estados: z.array(z.string()),
  tipos_evento: z.array(z.enum(["enchente", "deslizamento", "seca", "granizo", "vendaval", "onda_de_calor", "geada"])),
  periodo_inicio: z.string().nullable(),
  periodo_fim: z.string().nullable(),
});

export async function extrairEntidades(pergunta: string) {
  const { object } = await generateObject({
    model: anthropic("claude-sonnet-4-6"),
    schema: EntidadesSchema,
    prompt: `Extraia as entidades climáticas e geográficas da seguinte pergunta sobre eventos climáticos no Brasil:

"${pergunta}"

Datas no formato YYYY-MM-DD. Se não mencionado, retorne null para período.`,
  });
  return object;
}
```

**`pipeline/generator.ts`** — resposta com streaming:

```typescript
import { anthropic } from "@ai-sdk/anthropic";
import { streamText } from "ai";

export async function gerarResposta(pergunta: string, contexto: string) {
  return streamText({
    model: anthropic("claude-sonnet-4-6"),
    system: `Você é um assistente especializado em eventos climáticos extremos no Brasil.
Responda perguntas em linguagem acessível usando APENAS as informações do contexto fornecido.
Se o contexto não contiver informações suficientes, diga explicitamente.`,
    messages: [
      {
        role: "user",
        content: `Contexto do grafo de conhecimento climático:\n${contexto}\n\nPergunta: ${pergunta}`,
      },
    ],
  });
}
```

---

### Fase 4 — Baseline RAG Vetorial (Semana 3)

Implementar em `baseline/vectorRag.ts` usando `Neo4jVectorStore` do LangChain para comparação com RAGAS:

```typescript
import { Neo4jVectorStore } from "@langchain/community/vectorstores/neo4j_vector";
import { ChatAnthropic } from "@langchain/anthropic";

// RAG vetorial convencional sobre os mesmos dados
// para comparação justa com o GraphRAG
```

---

### Fase 5 — API e Interface (Semana 4)

**`api/index.ts`** — servidor Hono:

```typescript
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { extrairEntidades } from "../pipeline/entityExtractor";
import { buscarSubgrafo } from "../pipeline/graphRetriever";
import { construirContexto } from "../pipeline/contextBuilder";
import { gerarResposta } from "../pipeline/generator";

const app = new Hono();

app.post("/chat", async (c) => {
  const { pergunta } = await c.req.json();

  return streamSSE(c, async (stream) => {
    const entidades = await extrairEntidades(pergunta);
    const subgrafo = await buscarSubgrafo(entidades);
    const contexto = construirContexto(subgrafo);
    const resposta = await gerarResposta(pergunta, contexto);

    for await (const chunk of resposta.textStream) {
      await stream.writeSSE({ data: chunk });
    }
  });
});

app.get("/", (c) => c.html(Bun.file("frontend/index.html")));

export default { port: 3000, fetch: app.fetch };
```

**`package.json`** (via `bun init`):

```json
{
  "name": "graphrag-climatico",
  "scripts": {
    "dev": "bun --watch src/graphrag/index.ts",
    "start": "bun src/graphrag/index.ts"
  }
}
```

---

### Fase 6 — Avaliação RAGAS (Semana 5)

Comparar GraphRAG vs RAG vetorial com um conjunto de 30–50 perguntas elaboradas manualmente com gabaritos baseados nos dados reais.

| Métrica | GraphRAG esperado | RAG Vetorial esperado |
|---|---|---|
| Faithfulness | Alto (contexto estruturado) | Médio |
| Answer Relevancy | Alto | Alto |
| Context Recall | Alto em perguntas relacionais | Baixo em perguntas relacionais |

---

## Docker Compose — Neo4j

```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:5.18
    ports:
      - "7474:7474"   # Neo4j Browser
      - "7687:7687"   # Bolt (driver)
    environment:
      NEO4J_AUTH: neo4j/senha
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
volumes:
  neo4j_data:
```

```bash
docker compose up -d
```

---

## Ordem de Execução

```
1. docker compose up -d              ← Neo4j rodando
2. python src/python/01_ibge.py      ← municípios e estados
3. python src/python/02_estacoes.py  ← estações INMET
4. python src/python/03_historico_inmet.py  # paralelo
   python src/python/04_alertas_rss.py      # paralelo
   python src/python/05_cemaden_pdfs.py     # paralelo
5. python src/python/06_carga_neo4j.py ← carga final
6. bun dev                           ← GraphRAG + interface no ar
```

---

## Referências

- [LangChain JS — Neo4j integration](https://js.langchain.com/docs/integrations/graphs/neo4j_cypher)
- [Vercel AI SDK — streamText](https://sdk.vercel.ai/docs/reference/ai-sdk-core/stream-text)
- [Hono — Bun](https://hono.dev/docs/getting-started/bun)
- [Neo4j Driver JS](https://neo4j.com/docs/javascript-manual/current/)
- [RAGAS](https://docs.ragas.io)
