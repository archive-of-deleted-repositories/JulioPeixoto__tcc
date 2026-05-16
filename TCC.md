# TCC — Conhecimento em Grafos para o Clima

**Universidade Tiradentes — Ciência da Computação**  
**Aluno:** Julio Rafael Souza Peixoto  
**Orientador:** Victor Flávio de Andrade Araujo  
**Período:** 2º semestre de 2026  

---

## Título

**Conhecimento em Grafos para o Clima: construção de um sistema GraphRAG para consulta de eventos climáticos extremos no Brasil**

---

## Resumo

Eventos climáticos extremos como enchentes, secas e deslizamentos têm se tornado cada vez mais frequentes e severos no Brasil, causando impactos socioeconômicos expressivos. Embora o INMET e o CEMADEN produzam vastos volumes de dados meteorológicos e boletins técnicos, o acesso a essas informações pela população geral permanece limitado pela complexidade da linguagem e da estrutura dos documentos.

Este trabalho propõe a construção de um sistema conversacional baseado em **Graph Retrieval-Augmented Generation (GraphRAG)**, capaz de responder perguntas em linguagem natural sobre eventos climáticos extremos no Brasil, utilizando como base de conhecimento dados históricos do INMET e relatórios do CEMADEN.

Diferentemente do RAG vetorial tradicional, o GraphRAG representa o conhecimento como um **grafo de entidades e relações** — conectando municípios, estações meteorológicas e eventos climáticos — permitindo respostas mais precisas a perguntas relacionais complexas. O sistema será avaliado com o framework **RAGAS**, comparando sua performance com uma baseline de RAG vetorial convencional.

---

## Objetivos

### Geral

Construir um sistema conversacional baseado em GraphRAG capaz de responder perguntas em linguagem natural sobre eventos climáticos extremos no Brasil, utilizando dados do INMET e do CEMADEN como base de conhecimento estruturada em grafo.

### Específicos

- [ ] Coletar e pré-processar dados históricos meteorológicos do INMET (BDMEP) e boletins de eventos extremos do CEMADEN
- [ ] Construir um grafo de conhecimento climático conectando entidades como municípios, estações, fenômenos meteorológicos e eventos de desastre
- [ ] Implementar o pipeline GraphRAG sobre o grafo construído, integrando LLM para geração de respostas fundamentadas
- [ ] Comparar o desempenho do GraphRAG com uma baseline de RAG vetorial convencional utilizando o framework RAGAS
- [ ] Disponibilizar uma interface conversacional acessível para consulta de informações climáticas pela população geral

---

## Justificativa

O Brasil é um dos países mais vulneráveis a eventos climáticos extremos no mundo. Em 2024:
- Catástrofes naturais geraram prejuízos de aproximadamente **US$ 12 bilhões**
- Mais de **1.161 eventos** foram registrados pelo CEMADEN em um único ano
- Destaque para inundações e deslizamentos de terra

Os dados do INMET e CEMADEN são públicos, porém apresentados em formatos técnicos (CSVs com séries temporais, boletins em PDF) que exigem conhecimento prévio para interpretação. Há uma lacuna entre a produção de dados climáticos de qualidade e sua efetiva acessibilidade.

O GraphRAG representa um avanço sobre o RAG vetorial tradicional ao modelar o conhecimento como grafo de entidades e relações — abordagem especialmente adequada para dados climáticos, que são naturalmente relacionais. Perguntas como _"quais municípios do Sul do Brasil registraram mais eventos de inundação após precipitações acima de 100mm?"_ exigem raciocínio sobre múltiplas entidades conectadas, algo que o RAG vetorial convencional frequentemente falha em capturar.

**Originalidade:** aplicar GraphRAG a dados climáticos brasileiros é uma lacuna não explorada na literatura nacional.

---

## Metodologia

### 5.1 Coleta e Pré-processamento de Dados

**Fontes:**
- **INMET / BDMEP:** séries históricas de precipitação, temperatura e velocidade do vento de estações automáticas e convencionais
- **CEMADEN:** boletins mensais de eventos extremos em formato PDF

**Processamento:**
- Limpeza e normalização de dados tabulares
- Tratamento de valores ausentes (código `9999` no INMET)
- Extração de texto de PDFs para estruturação das informações

### 5.2 Construção do Grafo de Conhecimento

**Banco de dados de grafos** com as seguintes entidades:

| Entidade | Exemplos |
|---|---|
| Localização | Municípios, Estados |
| Infraestrutura | Estações meteorológicas |
| Eventos | Enchentes, Secas, Deslizamentos, Ondas de calor |
| Fenômenos | Precipitação extrema, La Niña, El Niño |

**Relações:**
- `município SOFREU evento`
- `evento CAUSADO_POR fenômeno`
- `estação REGISTROU medição`
- `estação PERTENCE_A município`

### 5.3 Implementação do Pipeline GraphRAG

Baseado na arquitetura **Microsoft GraphRAG (2024)**, adaptada para o domínio climático.

**Fluxo:**
1. Receber pergunta em linguagem natural
2. Identificar entidades relevantes
3. Percorrer o grafo de conhecimento para recuperar subgrafos pertinentes
4. Utilizar LLM para gerar resposta fundamentada nas informações recuperadas

**Stack técnico:**
- Linguagem: **Python**
- Orquestração: **LangChain** ou **LlamaIndex**
- Banco de grafos: a definir (Neo4j / Amazon Neptune / similar)

### 5.4 Avaliação

Framework **RAGAS** (Automated Evaluation of Retrieval Augmented Generation):

| Métrica | Descrição |
|---|---|
| Faithfulness | Fidelidade às fontes recuperadas |
| Answer Relevancy | Relevância da resposta à pergunta |
| Context Recall | Cobertura do contexto relevante |

Comparação com baseline de **RAG vetorial convencional** usando conjunto de perguntas elaborado manualmente com gabaritos baseados nos dados reais.

### 5.5 Interface Conversacional

Interface web simples para usuários sem conhecimento técnico interagirem com o sistema por meio de perguntas em linguagem natural.

---

## Cronograma

| Atividade | Mês 1 | Mês 2 | Mês 3 | Mês 4 | Mês 5 | Mês 6 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Revisão bibliográfica | X | X | | | | |
| Coleta e pré-processamento (INMET/CEMADEN) | | X | X | | | |
| Construção do grafo de conhecimento | | | | X | X | |
| Implementação do pipeline GraphRAG | | | | X | X | |
| Testes e avaliação (RAGAS) | | | | | X | X |
| Redação do texto final | | | | | | X |

---

## Referências Bibliográficas

- **CEMADEN.** Boletim Mensal de Impactos de Extremos Hidro-Geo-Climáticos. https://www.gov.br/cemaden/pt-br

- **EDGE, D. et al.** From Local to Global: A Graph RAG Approach to Query-Focused Summarization. *arXiv preprint arXiv:2404.16130*, 2024.

- **ES, S. et al.** RAGAS: Automated Evaluation of Retrieval Augmented Generation. *Proceedings of the 18th Conference of the European Chapter of the Association for Computational Linguistics*, p. 150–158, 2024.

- **INMET.** Banco de Dados Meteorológicos para Ensino e Pesquisa (BDMEP). https://bdmep.inmet.gov.br

- **LEWIS, P. et al.** Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems*, v. 33, p. 9459–9474, 2020.

- **STAMMBACH, D. et al. (Eds.).** Proceedings of the 1st Workshop on Natural Language Processing Meets Climate Change (ClimateNLP 2024). Association for Computational Linguistics, Bangkok, 2024.

- **VAGHEFI, S. A. et al.** Responsible Retrieval Augmented Generation for Climate Decision Making from Documents. *arXiv preprint arXiv:2410.23902*, 2024.

---

## Status do Projeto

- [ ] Revisão bibliográfica
- [ ] Fundamentação teórica
- [ ] Coleta de dados INMET/CEMADEN
- [ ] Pré-processamento dos dados
- [ ] Construção do grafo de conhecimento
- [ ] Implementação do pipeline GraphRAG
- [ ] Baseline RAG vetorial
- [ ] Avaliação com RAGAS
- [ ] Interface conversacional
- [ ] Redação final
