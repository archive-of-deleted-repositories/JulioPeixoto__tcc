import { runQuery } from "./client.ts";
import { QUERIES } from "./queries.ts";
import type { Entidades } from "../pipeline/entityExtractor.ts";

export interface SubgrafoResult {
  records: Record<string, unknown>[];
  queryUsada: string;
}

export async function buscarSubgrafo(entidades: Entidades): Promise<SubgrafoResult[]> {
  const resultados: SubgrafoResult[] = [];

  // Busca por municípios mencionados
  for (const municipio of entidades.municipios) {
    const records = await runQuery(QUERIES.eventosPorMunicipio, {
      nome: municipio,
    });
    if (records.length > 0) {
      resultados.push({ records, queryUsada: "eventosPorMunicipio" });
    }
  }

  // Busca por estados mencionados
  for (const sigla of entidades.estados) {
    const records = await runQuery(QUERIES.eventosPorEstado, {
      sigla: sigla.toUpperCase(),
      tipo: entidades.tipos_evento[0] ?? null,
      data_inicio: entidades.periodo_inicio,
      data_fim: entidades.periodo_fim,
    });
    if (records.length > 0) {
      resultados.push({ records, queryUsada: "eventosPorEstado" });
    }
  }

  // Fallback: ranking geral se nenhuma entidade geográfica encontrou resultados
  if (resultados.length === 0 && entidades.tipos_evento.length > 0) {
    const records = await runQuery(QUERIES.municipiosComMaisEventos, {
      fenomeno: entidades.tipos_evento[0],
      data_inicio: entidades.periodo_inicio,
      data_fim: entidades.periodo_fim,
    });
    resultados.push({ records, queryUsada: "municipiosComMaisEventos" });
  }

  return resultados;
}
