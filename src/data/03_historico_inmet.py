"""
Baixa ZIPs do histórico INMET (2015–2024), extrai CSVs e deriva eventos extremos.

Thresholds definidos no plano:
  - Precipitação extrema : CHUVA > 50 mm/dia
  - Chuva muito forte    : CHUVA > 100 mm/dia
  - Calor extremo        : TEM_MAX > 40 °C
  - Frio extremo / geada : TEM_MIN < 0 °C
  - Baixa umidade crítica: UMD_MIN < 12 %
"""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

RAW = Path(__file__).parents[2] / "data" / "raw"
PROCESSED = Path(__file__).parents[2] / "data" / "processed"
HIST_DIR = RAW / "inmet_historico"
HIST_DIR.mkdir(parents=True, exist_ok=True)

ANOS = range(2015, 2025)
ZIP_URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"

THRESHOLDS = {
    "precipitacao_extrema": ("CHUVA", ">", 50.0),
    "chuva_muito_forte":    ("CHUVA", ">", 100.0),
    "calor_extremo":        ("TEM_MAX", ">", 40.0),
    "frio_extremo":         ("TEM_MIN", "<", 0.0),
    "baixa_umidade":        ("UMD_MIN", "<", 12.0),
}

COLUNAS_INMET = {
    # Coluna de data — nome real no CSV
    "Data": "data",
    # Precipitação (com acento no CSV original)
    "PRECIPITAÇÃO TOTAL, HORÁRIO (mm)": "CHUVA",
    # Temperaturas (com acentos)
    "TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C)": "TEM_MAX",
    "TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C)": "TEM_MIN",
    # Umidade
    "UMIDADE REL. MAX. NA HORA ANT. (AUT) (%)": "UMD_MAX",
    "UMIDADE REL. MIN. NA HORA ANT. (AUT) (%)": "UMD_MIN",
}


def download_zip(ano: int) -> bytes | None:
    url = ZIP_URL.format(ano=ano)
    dest = HIST_DIR / f"{ano}.zip"
    if dest.exists():
        return dest.read_bytes()
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return r.content
    except Exception as e:
        print(f"  Erro ao baixar {ano}: {e}")
        return None


def parse_csv_inmet(raw_bytes: bytes, codigo_estacao: str) -> pd.DataFrame | None:
    """Lê CSV INMET (latin-1, sep=;, 8 linhas de cabeçalho)."""
    try:
        text = raw_bytes.decode("latin-1")
        df = pd.read_csv(
            io.StringIO(text),
            sep=";",
            skiprows=8,
            decimal=",",
            na_values=["-9999", "-9999.0"],
            usecols=range(19),
        )
        df = df.rename(columns={c: n for c, n in COLUNAS_INMET.items() if c in df.columns})
        df["estacao"] = codigo_estacao
        # Formato real: YYYY/MM/DD
        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], format="%Y/%m/%d", errors="coerce")
        return df
    except Exception:
        return None


def derivar_eventos(df: pd.DataFrame) -> list[dict]:
    eventos = []
    # Agrega por dia (CSV horário)
    diario = (
        df.groupby(["estacao", "data"])
        .agg(
            CHUVA=("CHUVA", "sum"),
            TEM_MAX=("TEM_MAX", "max"),
            TEM_MIN=("TEM_MIN", "min"),
            UMD_MIN=("UMD_MIN", "min"),
        )
        .reset_index()
    )
    for _, row in diario.iterrows():
        for tipo, (col, op, thresh) in THRESHOLDS.items():
            if col not in row or pd.isna(row[col]):
                continue
            val = row[col]
            if (op == ">" and val > thresh) or (op == "<" and val < thresh):
                eventos.append({
                    "estacao": row["estacao"],
                    "data": str(row["data"])[:10],
                    "tipo": tipo,
                    "valor": round(float(val), 2),
                    "threshold": thresh,
                    "unidade": "mm" if "CHUVA" in col else ("°C" if "TEM" in col else "%"),
                })
    return eventos


def processar_ano(ano: int) -> list[dict]:
    data = download_zip(ano)
    if data is None:
        return []

    eventos = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        csvs = [n for n in zf.namelist() if n.upper().endswith(".CSV")]
        for name in tqdm(csvs, desc=f"  {ano}", leave=False):
            codigo = Path(name).stem.split("_")[-1]
            df = parse_csv_inmet(zf.read(name), codigo)
            if df is not None:
                eventos.extend(derivar_eventos(df))
    return eventos


if __name__ == "__main__":
    todos_eventos = []
    for ano in ANOS:
        print(f"Processando {ano}...")
        ev = processar_ano(ano)
        todos_eventos.extend(ev)
        print(f"  {len(ev)} eventos derivados")

    out = PROCESSED / "eventos_extremos_inmet.jsonl"
    with out.open("w") as f:
        for ev in todos_eventos:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"\nTotal: {len(todos_eventos)} eventos → {out}")
