---
marp: true
theme: default
paginate: true
size: 16:9
header: 'GraphRAG para Eventos Climáticos Extremos no Brasil'
footer: 'Julio Rafael — TCC · Ciência da Computação · Unidade Tiradentes'
---

<!-- _paginate: false -->
<!-- _header: '' -->
<!-- _footer: '' -->

# GraphRAG para Consultas sobre Eventos Climáticos Extremos no Brasil
## Uma Avaliação Comparativa

**Julio Rafael**

Orientador: _[nome do orientador]_
Ciência da Computação — Unidade Tiradentes

2026

---

## Contexto e Problema

- Eventos climáticos extremos no Brasil são **cada vez mais frequentes** (chuvas intensas, secas, ondas de calor).
- Dados de **INMET** e **CEMADEN** são **públicos**, mas:
  - formato técnico (séries históricas, planilhas, PDFs);
  - **inacessíveis** ao público geral.
- Não há interface para **perguntar em linguagem natural** sobre esses dados.

> *Como tornar dados climáticos públicos consultáveis por qualquer pessoa?*

---

## Pergunta de Pesquisa e Objetivo

**Pergunta:**
RAG vetorial responde bem consultas **relacionais** — *ranking de municípios, contagem de eventos por estado* — ou apenas consultas semânticas?

**Objetivo:**
Avaliar comparativamente três abordagens sobre o mesmo conjunto de dados climáticos:

- **No RAG** (LLM puro)
- **Vector RAG** (busca semântica)
- **Graph RAG** (consulta estruturada em grafo)

---

## Fundamentação — RAG

**RAG (Retrieval-Augmented Generation)** combina recuperação de informação com geração por LLM:

1. **Recuperação** — busca trechos relevantes em uma base externa.
2. **Aumento** — injeta esses trechos no prompt.
3. **Geração** — o LLM responde fundamentado no contexto.

✅ Reduz alucinação e mantém respostas atualizadas, sem re-treinar o modelo.

- **Embeddings**: representam texto como vetores; busca por **similaridade semântica**.

---

## Vector RAG × Graph RAG

| Aspecto | Vector RAG | Graph RAG |
|---|---|---|
| Recuperação | Similaridade semântica | Travessia de relações |
| Forte em | Perguntas conceituais | Consultas relacionais / agregações |
| Ranking / contagem | ❌ Frágil | ✅ Preciso (via Cypher) |
| Estrutura dos dados | Ignorada | Explícita (nós e arestas) |

> A hipótese: consultas como *"municípios com mais eventos"* exigem **estrutura**, não só semântica.

---

## Trabalhos Relacionados

- **Sistemas de IA para dados climáticos** — assistentes e chatbots sobre dados meteorológicos.
- **Frameworks de avaliação de RAG** — RAGAS e métricas baseadas em LLM-as-judge.
- **Comparações empíricas Vector × Graph RAG** — estudos em outros domínios.

➡️ **Lacuna:** falta avaliação comparativa no domínio **climático brasileiro**.

---

## Metodologia — Fontes de Dados

Dados do **INMET** (estações automáticas, 2015–2024):

| Entidade | Volume |
|---|---|
| Estados | 27 |
| Municípios | 5.571 |
| Estações INMET | 774 |
| Eventos extremos (2015–2024) | 33.501 |
| Tipos de fenômeno | 12 |

CEMADEN previsto, mas **não integrado** (ver limitações).

---

## Metodologia — Modelo de Grafo (Neo4j)

```
(Estado) ──contém──> (Município) ──possui──> (Estação)
                                                  │
                                              registra
                                                  ▼
                          (Fenômeno) <──tipo── (Evento)
```

- Relações explícitas permitem **agregações e rankings** com **Cypher**.
- Índice vetorial em Neo4j (`eventos_vector`) para a baseline semântica.

---

## Arquitetura e Pipeline

**Stack:** TypeScript + Bun · Hono (API) · Neo4j · OpenAI

- **Geração:** GPT-4o  ·  **Extração/avaliação:** GPT-4o-mini
- **Embeddings:** text-embedding-3-small

**Fluxo de uma pergunta:**

```
Pergunta → Roteamento → ┌ Cypher (Graph RAG)
                        └ Índice vetorial (Vector RAG)
                                   → Contexto → LLM → Resposta
```

---

## Avaliação (RAGAS)

- **5 perguntas** representativas (relacionais e factuais).
- **Gabaritos** derivados de consultas **Cypher reais** sobre os dados.
- **Juiz:** LLM-as-judge (GPT-4o-mini), janela de 6.000 caracteres.

**Métricas:**

- **Faithfulness** — fidelidade ao contexto
- **Answer Relevancy** — relevância da resposta
- **Context Recall** — cobertura do contexto recuperado
- **Context Precision** — precisão do contexto recuperado

---

## Resultados

| Métrica | No RAG | Vector RAG | Graph RAG |
|---|---|---|---|
| Faithfulness | — | 0,80 | 0,80 |
| Answer Relevancy | 0,81 | 0,80 | **0,87** |
| Context Recall | — | 0,00 | **0,80** |
| Context Precision | — | 0,30 | **1,00** |

- Graph RAG: **+7 p.p.** relevância, **+80 p.p.** recall, **+70 p.p.** precisão.

---

## Discussão — Insight Principal

🔑 **Vector RAG: Context Recall = 0** mesmo com o índice completo (32 mil eventos).

- Similaridade semântica **não resolve** consultas relacionais.
- Buscar "eventos parecidos" ≠ **contar/ranquear** eventos por município.

**Graph RAG** recupera exatamente os fatos necessários via Cypher → contexto **preciso e completo**.

*(Q1 com faithfulness=0 no GraphRAG é artefato: ranking correto, mas contexto dominado por eventos individuais de 2024.)*

---

## Limitações e Ameaças à Validade

- **CEMADEN não processado** (PDFs exigem download manual + extração).
- Conjunto de avaliação **pequeno** (5 perguntas).
- **Juiz LLM** pode introduzir viés (LLM-as-judge).
- Recorte temporal **2015–2024** e somente estações automáticas.

---

## Conclusão

- Evidência **empírica** de que **Graph RAG supera Vector RAG** em consultas **relacionais** sobre dados climáticos brasileiros.
- A **estrutura** dos dados é decisiva — não basta semântica.

**Trabalhos futuros:**

- Integrar dados do **CEMADEN**.
- Ampliar o conjunto de avaliação.
- Interface pública de consulta em linguagem natural.

---

<!-- _paginate: false -->

# Obrigado!

**Perguntas?**

Julio Rafael — juliorafaelnft@hotmail.com

_[Referências completas no paper / artigo]_
