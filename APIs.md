# APIs e Fontes de Dados — TCC GraphRAG Climático

> Verificação realizada em: 14/05/2026

---

## Resumo Executivo

| Fonte | Formato | Acesso | Cobertura | Status |
|---|---|---|---|---|
| INMET — API REST (estações) | JSON | Público, sem auth | 2000–presente | ✅ Funcional |
| INMET — Histórico anual (ZIP) | CSV | Público, URL direta | 2000–2024 | ✅ Funcional |
| INMET — Alertas RSS | XML/RSS | Público, sem auth | Tempo real | ✅ Funcional |
| CEMADEN — Pluviômetros | CSV | Cadastro + e-mail | 2013–presente | ⚠️ Semi-manual |
| CEMADEN — Boletins mensais | PDF | Público | 2016–presente | ✅ Funcional (requer parsing) |
| Atlas Digital de Desastres | Web interativo | Público | 1991–2022 | ⚠️ Sem API |

---

## 1. INMET — Instituto Nacional de Meteorologia

### 1.1 API REST — `apitempo.inmet.gov.br`

**Base URL:** `https://apitempo.inmet.gov.br`  
**Autenticação:** Nenhuma para endpoints públicos

#### Endpoints

**Listar estações**
```
GET https://apitempo.inmet.gov.br/estacoes/{tipo}
```
- `{tipo}` = `T` (automáticas ~566) ou `M` (convencionais ~250)

Campos retornados por estação:

| Campo | Descrição | Exemplo |
|---|---|---|
| `CD_ESTACAO` | Código | `"A652"` |
| `DC_NOME` | Nome | `"ALTAMIRA"` |
| `SG_ESTADO` | UF | `"PA"` |
| `VL_LATITUDE` | Latitude | `"-3.21416666"` |
| `VL_LONGITUDE` | Longitude | `"-52.21305555"` |
| `VL_ALTITUDE` | Altitude (m) | `"101.51"` |
| `TP_ESTACAO` | Tipo | `"Automatica"` |
| `CD_SITUACAO` | Situação | `"Operante"` |
| `DT_INICIO_OPERACAO` | Início de operação | `"1927-04-23T21:00:00"` |

**Dados horários de uma estação**
```
GET https://apitempo.inmet.gov.br/estacao/{data_inicio}/{data_fim}/{cod_estacao}
```
- Datas no formato `YYYY-MM-DD`
- Máximo recomendado: 1 mês por requisição
- Frequência: horária

Variáveis meteorológicas retornadas:

| Campo JSON | Variável | Unidade |
|---|---|---|
| `CHUVA` | Precipitação acumulada | mm |
| `TEM_INS` / `TEM_MAX` / `TEM_MIN` | Temperatura | °C |
| `UMD_INS` / `UMD_MAX` / `UMD_MIN` | Umidade relativa | % |
| `PRE_INS` / `PRE_MAX` / `PRE_MIN` | Pressão atmosférica | hPa |
| `VEN_VEL` | Velocidade do vento | m/s |
| `VEN_DIR` | Direção do vento | graus |
| `VEN_RAJ` | Rajada máxima | m/s |
| `RAD_GLO` | Radiação global | kJ/m² |
| `PTO_INS` / `PTO_MAX` / `PTO_MIN` | Ponto de orvalho | °C |
| `DT_MEDICAO` | Data da medição | YYYY-MM-DD |
| `HR_MEDICAO` | Hora (UTC) | HH00 |

**Dados de todas as estações em um momento**
```
GET https://apitempo.inmet.gov.br/estacao/dados/{dia}
GET https://apitempo.inmet.gov.br/estacao/dados/{dia}/{hora}
```

**Estação mais próxima por geocódigo**
```
GET https://apiprevmet3.inmet.gov.br/estacao/proxima/{geocode}
```

**Alertas meteorológicos (RSS)**
```
GET https://apiprevmet3.inmet.gov.br/avisos/rss
```
- Formato: XML/RSS com tabelas HTML embutidas
- Campos: tipo de evento, severidade, início/fim, área geográfica afetada
- Tipos cobertos: Chuvas Intensas, Acumulado de Chuva, Baixa Umidade, Geada, Vendaval, Ventos Costeiros, Declínio de Temperatura

> **Nota:** O endpoint `/CLIMADIARIO/{uf}/{inicio}/{fim}` retornou erro 404 — provavelmente descontinuado.

---

### 1.2 BDMEP — Download de Histórico Anual

**URL de download:**
```
https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip
```
Exemplo: `https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip`

**Cobertura:** 2000 a 2025 (arquivo 2026 parcial disponível)  
**Formato:** ZIP → um CSV por estação automática  
**Atualização:** a cada 90 dias

**Estrutura do CSV:**
- Linhas 1–8: metadados da estação (Região, UF, Nome, Código WMO, Lat, Lon, Altitude, Data de Fundação)
- Linha 9+: dados horários com 19 colunas

**Encoding e parsing:**
- Encoding: `latin-1`
- Separador: `;`
- Decimal: `,`
- Valor nulo: `-9999`

```python
df = pd.read_csv(
    arquivo,
    sep=";",
    decimal=",",
    na_values="-9999",
    encoding="latin-1",
    skiprows=8,
    usecols=range(19)
)
```

**19 variáveis disponíveis:** precipitação, pressão (inst/max/min), radiação, temperatura ar (inst/max/min), ponto de orvalho (inst/max/min), umidade relativa (inst/max/min), direção do vento, rajada máxima, velocidade do vento.

---

### 1.3 WIS2BRA — OGC API (INMET)

**Base URL:** `http://wis2bra.inmet.gov.br/oapi/`

> ⚠️ Servidor inacessível em 14/05/2026 (ECONNREFUSED). Endpoints documentados mas instáveis.

| Coleção | Descrição |
|---|---|
| `urn:wmo:md:br-inmet:daycli` | Valores diários de estações terrestres |
| `urn:wmo:md:br-inmet:synop` | Observações sinópticas horárias automáticas |
| `urn:wmo:md:br-inmet:synop-man` | Observações sinópticas convencionais |
| `urn:wmo:md:br-inmet:upper-air` | Radiossondagem (temperatura/umidade/vento em altitude) |

Swagger UI: `http://wis2bra.inmet.gov.br/oapi/openapi?f=html`

---

### 1.4 Biblioteca Python — `inmetpy`

```bash
pip install inmetpy
```

Wrapper não-oficial para a API REST do INMET. Simplifica a coleta de dados por estação e período sem gerenciar manualmente os endpoints.

---

## 2. CEMADEN — Centro Nacional de Monitoramento e Alertas de Desastres Naturais

### 2.1 Pluviômetros — Download de Dados

**Cobertura:** 1.133 municípios monitorados (desde 2013)  
**Frequência:** Acumulado de chuva a cada 10 minutos  
**Fuso horário:** UTC

**Formulário de download:**
```
http://www2.cemaden.gov.br/mapainterativo/download/downpluv.php
```

**Processo:**
1. Preencher formulário com UF, município, mês/ano e e-mail
2. Resolver CAPTCHA
3. Receber link de download por e-mail com CSV mensal

> ⚠️ Processo semi-manual — necessário automatizar via Selenium/Playwright ou requisitar dados institucionalmente.

**Campos do CSV entregue:**
- latitude, longitude, dataHora (UTC), código da estação, acumulado de chuva (mm)

**Mapa interativo:** `https://mapainterativo.cemaden.gov.br/`

---

### 2.2 Boletins Mensais (PDF)

**Portal:** `https://www.gov.br/cemaden/pt-br/assuntos/monitoramento`

| Boletim | Periodicidade | Conteúdo principal |
|---|---|---|
| Estado do Clima, Extremos e Desastres | Mensal/Bimestral | Alertas, ocorrências, extremos climáticos (integração INMET/INPE) |
| Impactos de Extremos Hidro-Geo-Climáticos | Mensal | Alertas por região, ocorrências geo/hidrológicas, índices de seca, reservatórios |
| Monitoramento de Secas | Mensal | IIS-3, IIS-6, TSI (índices de seca), impactos vegetação/agricultura |
| Monitoramento Hidrológico | Mensal | Nível de rios, Sistema Cantareira, projeções sazonais |
| Boletim Trimestral de Alertas | Trimestral | Distribuição geográfica e temporal de alertas |
| Notas Técnicas | Irregular | Análises de eventos específicos |

**Variáveis reportadas:**
- Número e distribuição de alertas por região/estado
- Tipo de evento (geológico / hidrológico)
- Ocorrências (mortes, desabrigados, danos)
- Nível de rios vs. média climatológica
- Índice Integrado de Seca (IIS-3 e IIS-6)
- Índice Bivariado de Seca (TSI)
- Vazões afluentes e armazenamento de reservatórios

> ⚠️ Formato PDF não estruturado — requer extração de texto (pdfminer, pdfplumber) e NLP para uso no GraphRAG.

---

### 2.3 Estatísticas de Alertas 2024

- **3.620 alertas** emitidos (recorde histórico desde 2011)
- **1.690 ocorrências** de desastres registradas
- 53% alertas geológicos (deslizamentos), 47% hidrológicos (enchentes)
- Municípios com mais alertas: Manaus/AM (50), Belo Horizonte/MG (41), São Paulo/SP (41)

---

## 3. Atlas Digital de Desastres no Brasil

**URL:** `http://atlasdigital.mdr.gov.br/`  
**Fonte:** Defesa Civil Nacional + UFSC (2023)  
**Cobertura temporal:** 1991–2022  
**Cobertura geográfica:** Todos os municípios do Brasil  

> ⚠️ Plataforma interativa sem API REST ou download estruturado confirmado. Útil para validação histórica de longo prazo.

---

## 4. Estratégia de Coleta para o TCC

### Dados Estruturados (base do grafo)

```
INMET histórico anual (ZIP/CSV)
→ 2000–2024, ~820 estações, 19 variáveis horárias
→ Entidades: Estação → Município → Estado
→ Relações: PERTENCE_A, REGISTROU_MEDIÇÃO (precipitação, temperatura, etc.)
```

### Dados de Eventos e Alertas (arestas do grafo)

```
INMET Alertas RSS
→ Tempo real + histórico de alertas
→ Entidades: Evento → Mesorregião → Tipo de Fenômeno
→ Relações: AFETOU_ÁREA, CAUSADO_POR

CEMADEN Boletins PDF (parsing)
→ Mensal, 2016–presente
→ Entidades: Município → Ocorrência → Tipo de Desastre
→ Relações: SOFREU_EVENTO, REGISTROU_DANO
```

### Dados de Precipitação de Alta Resolução (validação)

```
CEMADEN Pluviômetros (formulário + e-mail)
→ 2013–presente, 10 minutos, 1.133 municípios
→ Útil para validar eventos extremos com dados finos
```

### Fluxo de Ingestão Recomendado

```
1. Download automático dos ZIPs INMET (loop por ano)
2. Parsing CSVs → filtragem de valores -9999
3. Scraping/download boletins CEMADEN PDF
4. Extração de texto PDF (pdfplumber)
5. Extração de entidades via NLP (spaCy + modelo pt)
6. Carga no banco de grafos (Neo4j)
```

---

## 5. Limitações Identificadas

| Limitação | Impacto | Mitigação |
|---|---|---|
| CEMADEN sem API REST pública | Necessário formulário manual ou acordo institucional | Automatizar com Selenium ou contatar CEMADEN |
| Boletins CEMADEN em PDF | Requer OCR/parsing | pdfplumber + regex ou LLM para extração |
| INMET endpoint CLIMADIARIO descontinuado | Não usar | Usar download histórico ZIP |
| WIS2BRA instável | Não confiar para produção | Usar API REST principal |
| INMET cobre estações, não municípios | Necessário geocodificação | Vincular estação → município via lat/lon |
| Valor nulo INMET = `-9999` | Distorção de análises | Substituir por `NaN` no pandas |

---

## 6. Referências e Links Úteis

| Recurso | URL |
|---|---|
| INMET — Dados Históricos | https://portal.inmet.gov.br/dadoshistoricos |
| INMET — API Estações | https://apitempo.inmet.gov.br/estacoes/T |
| INMET — Alertas RSS | https://apiprevmet3.inmet.gov.br/avisos/rss |
| BDMEP | https://bdmep.inmet.gov.br |
| CEMADEN | https://www.gov.br/cemaden/pt-br |
| CEMADEN — Mapa Interativo | https://mapainterativo.cemaden.gov.br |
| CEMADEN — Download Pluviômetros | http://www2.cemaden.gov.br/mapainterativo/download/downpluv.php |
| Atlas Digital de Desastres | http://atlasdigital.mdr.gov.br |
| inmetpy (PyPI) | https://pypi.org/project/inmetpy |
| Base dos Dados — INMET | https://basedosdados.org/dataset/782c5607-9f69-4e12-b0d5-aa0f1a7a94e2 |
