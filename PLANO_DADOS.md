# Plano de Coleta e Ingestão de Dados — GraphRAG Climático

> Baseado em: `APIs.md` + pré-projeto do TCC  
> Objetivo: produzir os nós e arestas do grafo de conhecimento climático

---

## Visão Geral do Pipeline

```
[INMET API]        → Estações (nós)
[INMET ZIP/CSV]    → Medições + Eventos extremos derivados (nós + arestas)
[INMET RSS]        → Alertas meteorológicos (nós de Evento)
[CEMADEN PDF]      → Ocorrências de desastre por município (nós de Evento + arestas)
[IBGE API]         → Municípios e Estados (nós de localização)
        ↓
  Normalização e linkagem
        ↓
  Carga no Neo4j (grafo de conhecimento)
```

---

## Entidades e Relações do Grafo

### Nós

| Label | Atributos principais | Fonte |
|---|---|---|
| `Estacao` | codigo, nome, tipo, lat, lon, altitude, uf, situacao | INMET API |
| `Municipio` | codigo_ibge, nome, uf, lat, lon | IBGE API |
| `Estado` | sigla, nome, regiao | IBGE API |
| `Evento` | id, tipo, data_inicio, data_fim, severidade, descricao | INMET RSS / CEMADEN PDF |
| `Fenomeno` | nome, categoria | Derivado (precipitação extrema, seca, etc.) |
| `Medicao` | data, hora, precipitacao, temp_max, temp_min, umidade, vento | INMET ZIP |

### Arestas

| Relação | De → Para | Atributos | Fonte |
|---|---|---|---|
| `PERTENCE_A` | Estacao → Municipio | — | Geocodificação lat/lon |
| `PERTENCE_A` | Municipio → Estado | — | IBGE |
| `REGISTROU` | Estacao → Medicao | — | INMET ZIP |
| `SOFREU` | Municipio → Evento | data, impacto | CEMADEN PDF |
| `AFETOU` | Evento → Municipio | severidade | INMET RSS |
| `CAUSADO_POR` | Evento → Fenomeno | — | Derivado do tipo de evento |
| `PRECEDIDA_POR` | Evento → Medicao | intervalo_horas | Cruzamento temporal |

---

## Etapa 1 — Municípios e Estados (IBGE)

**Por que primeiro:** todas as outras entidades dependem de município para linkagem.

### O que consumir

```
GET https://servicodados.ibge.gov.br/api/v1/localidades/municipios
```

Retorna ~5.570 municípios com: `id` (código IBGE 7 dígitos), `nome`, `microrregiao.mesorregiao.UF.sigla`, `microrregiao.mesorregiao.UF.nome`, `microrregiao.mesorregiao.UF.regiao.nome`.

```
GET https://servicodados.ibge.gov.br/api/v1/localidades/estados
```

Retorna 27 estados com: `id`, `sigla`, `nome`, `regiao`.

### Como consumir

```python
import requests, json

municipios = requests.get(
    "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
).json()

estados = requests.get(
    "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
).json()
```

### Saída

- `data/raw/ibge_municipios.json` — 5.570 municípios
- `data/raw/ibge_estados.json` — 27 estados

### Nós gerados

```
(:Estado {sigla, nome, regiao})                          → 27 nós
(:Municipio {codigo_ibge, nome, uf, lat, lon})           → 5.570 nós
(:Municipio)-[:PERTENCE_A]->(:Estado)                    → 5.570 arestas
```

> **Nota:** A API IBGE não retorna centróides. Para lat/lon dos municípios, usar o dataset de centroides do IBGE (shapefile) ou a API de malhas: `https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}?formato=application/vnd.geo+json`

---

## Etapa 2 — Estações Meteorológicas (INMET API)

### O que consumir

```
GET https://apitempo.inmet.gov.br/estacoes/T   → ~566 automáticas
GET https://apitempo.inmet.gov.br/estacoes/M   → ~250 convencionais
```

Campos relevantes: `CD_ESTACAO`, `DC_NOME`, `SG_ESTADO`, `VL_LATITUDE`, `VL_LONGITUDE`, `VL_ALTITUDE`, `TP_ESTACAO`, `CD_SITUACAO`, `DT_INICIO_OPERACAO`.

### Como consumir

```python
import requests

def get_estacoes(tipo: str) -> list[dict]:
    url = f"https://apitempo.inmet.gov.br/estacoes/{tipo}"
    return requests.get(url, timeout=30).json()

automaticas   = get_estacoes("T")
convencionais = get_estacoes("M")
estacoes = automaticas + convencionais  # ~820 estações
```

### Linkagem estação → município

Para cada estação, encontrar o município mais próximo via lat/lon:

```python
from scipy.spatial import KDTree
import pandas as pd

# Carregar municípios com lat/lon
df_mun = pd.read_csv("data/processed/municipios_centroides.csv")
tree = KDTree(df_mun[["lat", "lon"]].values)

def vincular_municipio(lat: float, lon: float) -> dict:
    _, idx = tree.query([lat, lon])
    return df_mun.iloc[idx][["codigo_ibge", "nome", "uf"]].to_dict()

for estacao in estacoes:
    estacao["municipio"] = vincular_municipio(
        float(estacao["VL_LATITUDE"]),
        float(estacao["VL_LONGITUDE"])
    )
```

### Saída

- `data/raw/estacoes_automaticas.json`
- `data/raw/estacoes_convencionais.json`
- `data/processed/estacoes_com_municipio.json`

### Nós e arestas gerados

```
(:Estacao {codigo, nome, tipo, lat, lon, altitude, uf, situacao})   → ~820 nós
(:Estacao)-[:PERTENCE_A]->(:Municipio)                              → ~820 arestas
```

---

## Etapa 3 — Dados Históricos Meteorológicos (INMET ZIP)

**Foco:** não armazenar todas as medições horárias no grafo (seria volumoso demais). Em vez disso, **derivar eventos extremos** a partir das séries.

### O que baixar

```
https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip
```

Anos recomendados para o TCC: **2015–2024** (10 anos, balanço entre volume e relevância).

### Como consumir

```python
import requests, zipfile, io, os
import pandas as pd

ANOS = range(2015, 2025)
OUTPUT_DIR = "data/raw/inmet_historico"

def baixar_ano(ano: int):
    url = f"https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
    r = requests.get(url, timeout=120, stream=True)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(f"{OUTPUT_DIR}/{ano}/")

for ano in ANOS:
    baixar_ano(ano)
```

### Como parsear os CSVs

```python
def ler_csv_inmet(caminho: str) -> tuple[dict, pd.DataFrame]:
    # Linha 1-8: metadados da estação
    meta = {}
    with open(caminho, encoding="latin-1") as f:
        for i, linha in enumerate(f):
            if i == 0: meta["regiao"]    = linha.split(";")[1].strip()
            if i == 1: meta["uf"]        = linha.split(";")[1].strip()
            if i == 2: meta["nome"]      = linha.split(";")[1].strip()
            if i == 3: meta["codigo"]    = linha.split(";")[1].strip()
            if i == 4: meta["latitude"]  = linha.split(";")[1].strip()
            if i == 5: meta["longitude"] = linha.split(";")[1].strip()
            if i == 6: meta["altitude"]  = linha.split(";")[1].strip()
            if i == 7: meta["fundacao"]  = linha.split(";")[1].strip()
            if i >= 8: break

    df = pd.read_csv(
        caminho,
        sep=";",
        decimal=",",
        na_values=["-9999", "-9999.0", ""],
        encoding="latin-1",
        skiprows=8,
        usecols=range(19),
    )
    return meta, df
```

### Derivação de Eventos Extremos

Em vez de carregar medições brutas no grafo, agregar por dia e identificar **thresholds de extremo**:

```python
THRESHOLDS = {
    "precipitacao_extrema":  {"col": "CHUVA",    "op": ">", "valor": 50.0,  "fenomeno": "Precipitação Extrema"},
    "chuva_muito_forte":     {"col": "CHUVA",    "op": ">", "valor": 100.0, "fenomeno": "Chuva Muito Forte"},
    "calor_extremo":         {"col": "TEM_MAX",  "op": ">", "valor": 40.0,  "fenomeno": "Onda de Calor"},
    "frio_extremo":          {"col": "TEM_MIN",  "op": "<", "valor": 0.0,   "fenomeno": "Geada"},
    "baixa_umidade":         {"col": "UMD_MIN",  "op": "<", "valor": 12.0,  "fenomeno": "Baixa Umidade Crítica"},
}

def derivar_eventos(df: pd.DataFrame, codigo_estacao: str) -> list[dict]:
    eventos = []
    df["data"] = pd.to_datetime(df["DT_MEDICAO"])
    diario = df.groupby("data").agg({
        "CHUVA": "sum", "TEM_MAX": "max",
        "TEM_MIN": "min", "UMD_MIN": "min"
    }).reset_index()

    for nome_evento, regra in THRESHOLDS.items():
        col, op, val = regra["col"], regra["op"], regra["valor"]
        mask = diario[col] > val if op == ">" else diario[col] < val
        for _, row in diario[mask].iterrows():
            eventos.append({
                "estacao":   codigo_estacao,
                "data":      str(row["data"].date()),
                "tipo":      nome_evento,
                "fenomeno":  regra["fenomeno"],
                "valor":     row[col],
                "coluna":    col,
            })
    return eventos
```

### Saída

- `data/raw/inmet_historico/{ano}/` — ZIPs extraídos (~10 anos × ~820 CSVs)
- `data/processed/eventos_extremos_inmet.jsonl` — eventos derivados (linha por evento)

### Nós e arestas gerados

```
(:Fenomeno {nome, categoria})                              → 5 nós fixos
(:Evento {id, tipo, data, valor, coluna})                  → variável (~milhares)
(:Evento)-[:CAUSADO_POR]->(:Fenomeno)
(:Estacao)-[:DETECTOU]->(:Evento)
(:Evento)-[:OCORREU_EM]->(:Municipio)    ← via estação → município (Etapa 2)
```

---

## Etapa 4 — Alertas Meteorológicos (INMET RSS)

### O que consumir

```
GET https://apiprevmet3.inmet.gov.br/avisos/rss
```

XML/RSS com alertas ativos. Atualizado diariamente.

### Como consumir

```python
import feedparser, re
from bs4 import BeautifulSoup

def parsear_alertas_rss() -> list[dict]:
    feed = feedparser.parse("https://apiprevmet3.inmet.gov.br/avisos/rss")
    alertas = []
    for entry in feed.entries:
        soup = BeautifulSoup(entry.summary, "html.parser")
        linhas = {
            tr.find_all("td")[0].text.strip(): tr.find_all("td")[1].text.strip()
            for tr in soup.find_all("tr")
            if len(tr.find_all("td")) >= 2
        }
        alertas.append({
            "titulo":      entry.title,
            "evento":      linhas.get("Evento", ""),
            "severidade":  linhas.get("Severidade", ""),
            "inicio":      linhas.get("Início", ""),
            "fim":         linhas.get("Fim", ""),
            "descricao":   linhas.get("Descrição", ""),
            "area":        linhas.get("Área", ""),
        })
    return alertas
```

### Mapeamento área → municípios

O campo `area` contém nomes de mesorregiões ou listas de municípios em texto livre. Normalizar com fuzzy matching contra a lista IBGE:

```python
from rapidfuzz import process

nomes_municipios = df_mun["nome"].tolist()

def extrair_municipios_do_alerta(area_texto: str) -> list[str]:
    candidatos = [t.strip() for t in re.split(r"[,;/\n]", area_texto) if len(t.strip()) > 3]
    municipios_encontrados = []
    for cand in candidatos:
        match, score, _ = process.extractOne(cand, nomes_municipios)
        if score >= 85:
            municipios_encontrados.append(match)
    return municipios_encontrados
```

### Saída

- `data/processed/alertas_inmet.jsonl` — alertas com municípios linkados

### Nós e arestas gerados

```
(:Evento {id, tipo, severidade, data_inicio, data_fim, descricao})
(:Evento)-[:AFETOU]->(:Municipio)           ← um por município no campo área
(:Evento)-[:CAUSADO_POR]->(:Fenomeno)       ← derivado do campo "Evento"
```

---

## Etapa 5 — Boletins CEMADEN (PDF)

### O que baixar

Boletins mensais de **Impactos de Extremos Hidro-Geo-Climáticos** (2020–2024 = ~60 PDFs, escopo viável para TCC).

URL padrão:
```
https://www.gov.br/cemaden/pt-br/assuntos/monitoramento/
boletim-de-impactos-de-extremos-de-origem-hidro-geo-climatico-em-atividades-estrategicas-para-o-brasil/
```

### Como baixar (scraping do índice)

```python
import requests
from bs4 import BeautifulSoup

BASE = "https://www.gov.br/cemaden/pt-br/assuntos/monitoramento/boletim-de-impactos-de-extremos-de-origem-hidro-geo-climatico-em-atividades-estrategicas-para-o-brasil"

def listar_boletins() -> list[str]:
    r = requests.get(BASE, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    links = [
        a["href"] for a in soup.find_all("a", href=True)
        if "boletim" in a["href"].lower() and a["href"].endswith(".pdf")
    ]
    return links

def baixar_pdf(url: str, destino: str):
    r = requests.get(url, timeout=60, stream=True)
    with open(destino, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
```

### Como parsear os PDFs

```python
import pdfplumber

def extrair_texto_pdf(caminho_pdf: str) -> str:
    texto = ""
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto += pagina.extract_text() or ""
    return texto
```

### Extração de entidades via LLM

Para cada página ou seção do boletim, usar um LLM (Claude) para estruturar as informações:

```python
import anthropic

client = anthropic.Anthropic()

PROMPT_EXTRACAO = """
Você é um extrator de informações climáticas. A partir do trecho de boletim abaixo,
extraia eventos de desastre mencionados no formato JSON com os campos:
- municipio (string)
- estado (string, sigla UF)
- tipo_evento (string: "enchente" | "deslizamento" | "seca" | "granizo" | "vendaval" | "outro")
- data (string YYYY-MM ou YYYY-MM-DD se disponível)
- impactos (objeto com: mortos, desabrigados, desalojados — null se não mencionado)
- descricao (string curta)

Responda APENAS com um array JSON válido. Se não houver eventos, responda [].

Trecho:
{trecho}
"""

def extrair_eventos_do_boletim(texto: str) -> list[dict]:
    # Dividir em chunks de ~2000 chars para processar por seção
    chunks = [texto[i:i+2000] for i in range(0, len(texto), 1800)]
    eventos = []
    for chunk in chunks:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": PROMPT_EXTRACAO.format(trecho=chunk)
            }]
        )
        try:
            import json
            dados = json.loads(resp.content[0].text)
            eventos.extend(dados)
        except Exception:
            pass
    return eventos
```

### Saída

- `data/raw/cemaden_pdfs/` — ~60 PDFs
- `data/processed/eventos_cemaden.jsonl` — eventos estruturados com município, tipo, data, impactos

### Nós e arestas gerados

```
(:Evento {id, tipo, data, descricao, mortos, desabrigados})
(:Municipio)-[:SOFREU]->(:Evento)
(:Evento)-[:CAUSADO_POR]->(:Fenomeno)
```

---

## Etapa 6 — Normalização e Carga no Neo4j

### Deduplicação de eventos

Antes de carregar, unificar eventos de fontes diferentes que referenciam o mesmo acontecimento:

```python
# Critério de deduplicação: mesmo município + mesmo tipo + mesma semana
def chave_evento(e: dict) -> str:
    from datetime import datetime, timedelta
    data = datetime.fromisoformat(e["data"][:10])
    semana = data - timedelta(days=data.weekday())
    return f"{e['municipio']}|{e['tipo_evento']}|{semana.isoformat()}"
```

### Carga no Neo4j

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "senha"))

def carregar_estacao(tx, estacao: dict):
    tx.run("""
        MERGE (e:Estacao {codigo: $codigo})
        SET e.nome = $nome, e.lat = $lat, e.lon = $lon,
            e.uf = $uf, e.tipo = $tipo, e.altitude = $altitude
    """, **estacao)

def carregar_evento(tx, evento: dict):
    tx.run("""
        MERGE (ev:Evento {id: $id})
        SET ev.tipo = $tipo, ev.data = $data,
            ev.descricao = $descricao, ev.severidade = $severidade
        WITH ev
        MATCH (m:Municipio {nome: $municipio, uf: $uf})
        MERGE (m)-[:SOFREU]->(ev)
        WITH ev
        MATCH (f:Fenomeno {nome: $fenomeno})
        MERGE (ev)-[:CAUSADO_POR]->(f)
    """, **evento)

with driver.session() as session:
    for estacao in estacoes_processadas:
        session.execute_write(carregar_estacao, estacao)
    for evento in todos_eventos:
        session.execute_write(carregar_evento, evento)
```

---

## Ordem de Execução e Dependências

```
Etapa 1 (IBGE)          ← sem dependências — EXECUTAR PRIMEIRO
    ↓
Etapa 2 (INMET Estações) ← depende de Etapa 1 (municípios para linkagem)
    ↓
Etapa 3 (INMET ZIP)      ← depende de Etapa 2 (código de estação)
Etapa 4 (INMET RSS)      ← depende de Etapa 1 (municípios para fuzzy match)
Etapa 5 (CEMADEN PDF)    ← depende de Etapa 1 (municípios para validação)
    ↓
Etapa 6 (Neo4j)          ← depende de todas as anteriores
```

Etapas 3, 4 e 5 podem rodar em paralelo após a Etapa 2.

---

## Volume Estimado de Dados

| Fonte | Volume bruto | Nós gerados | Arestas geradas |
|---|---|---|---|
| IBGE | ~2 MB JSON | 5.597 (mun + est) | 5.570 |
| INMET Estações | ~500 KB JSON | ~820 | ~820 |
| INMET ZIP 2015–2024 | ~15 GB total | ~50k–200k eventos | ~200k |
| INMET RSS | ~100 KB/dia | ~20–50/dia | ~100/dia |
| CEMADEN PDFs | ~300 MB total | ~2k–5k eventos | ~5k |
| **Total estimado no grafo** | — | **~60k nós** | **~210k arestas** |

---

## Stack de Ferramentas

| Ferramenta | Uso |
|---|---|
| `requests` | Download de APIs e PDFs |
| `pandas` | Parsing e agregação de CSVs INMET |
| `pdfplumber` | Extração de texto dos boletins CEMADEN |
| `feedparser` | Parsing do RSS INMET |
| `beautifulsoup4` | Parsing HTML dentro do RSS |
| `rapidfuzz` | Fuzzy match de nomes de municípios |
| `scipy` | KDTree para geocodificação por proximidade |
| `anthropic` | Extração de entidades dos PDFs via LLM |
| `neo4j` (driver Python) | Carga do grafo |
| `tqdm` | Barra de progresso nos loops de download |

```bash
pip install requests pandas pdfplumber feedparser beautifulsoup4 \
            rapidfuzz scipy anthropic neo4j tqdm
```

---

## Estrutura de Diretórios Sugerida

```
tcc/
├── data/
│   ├── raw/
│   │   ├── ibge_municipios.json
│   │   ├── ibge_estados.json
│   │   ├── estacoes_automaticas.json
│   │   ├── estacoes_convencionais.json
│   │   ├── inmet_historico/
│   │   │   ├── 2015/
│   │   │   └── ...
│   │   └── cemaden_pdfs/
│   └── processed/
│       ├── municipios_centroides.csv
│       ├── estacoes_com_municipio.json
│       ├── eventos_extremos_inmet.jsonl
│       ├── alertas_inmet.jsonl
│       └── eventos_cemaden.jsonl
├── src/
│   ├── 01_ibge.py
│   ├── 02_estacoes.py
│   ├── 03_historico_inmet.py
│   ├── 04_alertas_rss.py
│   ├── 05_cemaden_pdfs.py
│   └── 06_carga_neo4j.py
├── TCC.md
├── APIs.md
└── PLANO_DADOS.md
```
