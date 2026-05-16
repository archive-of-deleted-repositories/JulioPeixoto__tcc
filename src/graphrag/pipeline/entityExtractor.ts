import { createAnthropic } from "@ai-sdk/anthropic";
import { generateObject } from "ai";
import { z } from "zod";

const anthropic = createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const EntidadesSchema = z.object({
  municipios: z.array(z.string()).describe("Nomes de municípios mencionados"),
  estados: z.array(z.string()).describe("Siglas de estados brasileiros (ex: SP, RJ)"),
  tipos_evento: z
    .array(
      z.enum([
        "enchente",
        "deslizamento",
        "seca",
        "granizo",
        "vendaval",
        "onda_de_calor",
        "geada",
        "precipitacao_extrema",
        "chuva_muito_forte",
        "calor_extremo",
        "frio_extremo",
        "baixa_umidade",
      ])
    )
    .describe("Tipos de eventos climáticos mencionados"),
  periodo_inicio: z
    .string()
    .nullable()
    .describe("Data de início no formato YYYY-MM-DD"),
  periodo_fim: z
    .string()
    .nullable()
    .describe("Data de fim no formato YYYY-MM-DD"),
});

export type Entidades = z.infer<typeof EntidadesSchema>;

export async function extrairEntidades(pergunta: string): Promise<Entidades> {
  const { object } = await generateObject({
    model: anthropic("claude-haiku-4-5-20251001"),
    schema: EntidadesSchema,
    prompt: `Extraia entidades climáticas e geográficas da pergunta abaixo sobre eventos climáticos no Brasil.
Hoje é ${new Date().toISOString().slice(0, 10)}.
Se a pergunta mencionar "este ano", "ano passado" ou similar, converta para datas absolutas.
Se nenhuma data for mencionada, retorne null para período.

Pergunta: "${pergunta}"`,
  });
  return object;
}
