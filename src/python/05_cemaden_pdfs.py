"""
Processa boletins mensais do CEMADEN em PDF.

Fluxo:
  1. Extrai texto de cada PDF com pdfplumber
  2. Envia para Claude extrair eventos estruturados (JSON)
  3. Salva em data/processed/eventos_cemaden.jsonl
"""

import json
import os
from pathlib import Path

import anthropic
import pdfplumber
from tqdm import tqdm

RAW = Path(__file__).parents[2] / "data" / "raw"
PROCESSED = Path(__file__).parents[2] / "data" / "processed"
PDF_DIR = RAW / "cemaden_pdfs"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """Você é um extrator de informações sobre eventos climáticos extremos.
Dado o texto de um boletim do CEMADEN, extraia TODOS os eventos mencionados no formato JSON.
Retorne SOMENTE um array JSON, sem markdown, com objetos no formato:
{
  "municipio": "Nome do Município",
  "uf": "XX",
  "data": "YYYY-MM-DD",
  "tipo": "enchente|deslizamento|seca|granizo|vendaval|onda_de_calor|geada|outro",
  "descricao": "breve descrição do evento",
  "mortos": 0,
  "afetados": 0
}
Se uma informação não estiver disponível, use null."""


def extrair_texto_pdf(pdf_path: Path) -> str:
    textos = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                textos.append(texto)
    return "\n\n".join(textos)


def extrair_eventos_llm(texto: str, arquivo: str) -> list[dict]:
    # Trunca para caber no contexto (PDFs grandes)
    texto_trunc = texto[:40_000]
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Boletim: {arquivo}\n\n{texto_trunc}",
                }
            ],
        )
        conteudo = msg.content[0].text.strip()
        return json.loads(conteudo)
    except (json.JSONDecodeError, Exception) as e:
        print(f"  Erro LLM em {arquivo}: {e}")
        return []


if __name__ == "__main__":
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em {PDF_DIR}")
        print("Baixe os boletins manualmente em: https://www.cemaden.gov.br/boletins/")
        raise SystemExit(0)

    print(f"{len(pdfs)} PDFs encontrados")
    todos_eventos = []

    for pdf_path in tqdm(pdfs, desc="Processando PDFs"):
        texto = extrair_texto_pdf(pdf_path)
        if not texto.strip():
            continue
        eventos = extrair_eventos_llm(texto, pdf_path.name)
        for ev in eventos:
            ev["fonte_pdf"] = pdf_path.name
        todos_eventos.extend(eventos)

    out = PROCESSED / "eventos_cemaden.jsonl"
    with out.open("w") as f:
        for ev in todos_eventos:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"\nTotal: {len(todos_eventos)} eventos → {out}")
