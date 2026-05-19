import { runQuery } from "./client.ts";
import { QUERIES } from "./queries.ts";
import type { Entidades } from "../pipeline/entityExtractor.ts";

export interface SubgrafoResult {
  records: Record<string, unknown>[];
  queryUsada: string;
}

const PERIODO_PADRAO_ANOS = 2;

function aplicarPeriodoPadrao(entidades: Entidades): Entidades {
  if (entidades.periodo_inicio !== null || entidades.periodo_fim !== null) return entidades;
  const hoje = new Date();
  const inicio = new Date(hoje);
  inicio.setFullYear(hoje.getFullYear() - PERIODO_PADRAO_ANOS);
  return {
    ...entidades,
    periodo_inicio: inicio.toISOString().slice(0, 10),
    periodo_fim: hoje.toISOString().slice(0, 10),
  };
}

export interface BuscarSubgrafoResult {
  subgrafos: SubgrafoResult[];
  entidadesEfetivas: Entidades;
}

export async function buscarSubgrafo(entidades: Entidades): Promise<BuscarSubgrafoResult> {
  const resultados: SubgrafoResult[] = [];
  const ent = aplicarPeriodoPadrao(entidades);

  // Busca por municípios mencionados
  for (const municipio of ent.municipios) {
    const records = await runQuery(QUERIES.eventosPorMunicipio, {
      nome: municipio,
      tipo: ent.tipos_evento[0] ?? null,
      data_inicio: ent.periodo_inicio,
      data_fim: ent.periodo_fim,
    });
    if (records.length > 0) {
      resultados.push({ records, queryUsada: "eventosPorMunicipio" });
    }
  }

  // Busca por estados mencionados
  for (const sigla of ent.estados) {
    const records = await runQuery(QUERIES.eventosPorEstado, {
      sigla: sigla.toUpperCase(),
      tipo: ent.tipos_evento[0] ?? null,
      data_inicio: ent.periodo_inicio,
      data_fim: ent.periodo_fim,
    });
    if (records.length > 0) {
      resultados.push({ records, queryUsada: "eventosPorEstado" });
    }
  }

  // Fallback: ranking geral se nenhuma entidade geográfica encontrou resultados
  if (resultados.length === 0 && ent.tipos_evento.length > 0) {
    const records = await runQuery(QUERIES.municipiosComMaisEventos, {
      fenomeno: ent.tipos_evento[0],
      data_inicio: ent.periodo_inicio,
      data_fim: ent.periodo_fim,
    });
    resultados.push({ records, queryUsada: "municipiosComMaisEventos" });
  }

  return { subgrafos: resultados, entidadesEfetivas: ent };
}
