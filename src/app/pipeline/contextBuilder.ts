import type { SubgrafoResult } from "./graphRetriever.ts";

function formatarRegistro(record: Record<string, unknown>): string {
  const partes: string[] = [];
  if (record.municipio) partes.push(`Município: ${record.municipio} (${record.uf ?? ""})`);
  if (record.tipo) partes.push(`Tipo: ${record.tipo}`);
  if (record.fenomeno) partes.push(`Fenômeno: ${record.fenomeno}`);
  if (record.data) partes.push(`Data: ${record.data}`);
  if (record.valor != null) partes.push(`Valor medido: ${record.valor}`);
  if (record.descricao) partes.push(`Descrição: ${record.descricao}`);
  if (record.total != null) partes.push(`Total de eventos: ${record.total}`);
  if (record.fonte) partes.push(`Fonte: ${record.fonte}`);
  return partes.join(" | ");
}

export function construirContexto(subgrafos: SubgrafoResult[]): string {
  if (subgrafos.length === 0) {
    return "Nenhum dado encontrado no grafo para os critérios fornecidos.";
  }

  const secoes = subgrafos.map((sg) => {
    const linhas = sg.records.map(formatarRegistro).filter(Boolean);
    return `[${sg.queryUsada}]\n${linhas.join("\n")}`;
  });

  return secoes.join("\n\n");
}
