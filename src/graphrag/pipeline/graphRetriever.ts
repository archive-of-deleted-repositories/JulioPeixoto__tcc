import { buscarSubgrafo, type SubgrafoResult } from "../graph/retriever.ts";
import type { Entidades } from "./entityExtractor.ts";

export type { SubgrafoResult };

export async function recuperarSubgrafo(
  entidades: Entidades
): Promise<SubgrafoResult[]> {
  return buscarSubgrafo(entidades);
}
