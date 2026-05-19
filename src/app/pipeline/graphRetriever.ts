import { buscarSubgrafo, type SubgrafoResult, type BuscarSubgrafoResult } from "../graph/retriever.ts";
import type { Entidades } from "./entityExtractor.ts";

export type { SubgrafoResult, BuscarSubgrafoResult };

export async function recuperarSubgrafo(
  entidades: Entidades
): Promise<BuscarSubgrafoResult> {
  return buscarSubgrafo(entidades);
}
