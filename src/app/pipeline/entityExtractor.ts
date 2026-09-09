import { generateObject } from "ai";
import { z } from "zod";
import { modelos } from "../ai/index.ts";

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
  periodos: z
    .array(
      z.object({
        inicio: z.string().describe("Data de início no formato YYYY-MM-DD"),
        fim: z.string().describe("Data de fim no formato YYYY-MM-DD"),
        rotulo: z.string().describe("Rótulo curto da janela, ex: '2018' ou 'verão de 2022'"),
      })
    )
    .describe(
      "Uma entrada por janela temporal mencionada. Perguntas comparativas " +
        "('X em 2018 ou em 2020?', 'compare A com B') produzem DUAS ou mais janelas, " +
        "uma por época. Perguntas com um único recorte produzem uma. Lista vazia " +
        "quando nenhuma data é mencionada."
    ),
  comparativa: z
    .boolean()
    .describe(
      "true quando a pergunta contrasta explicitamente duas ou mais épocas entre si"
    ),
  intencao: z
    .enum([
      "factual",        // existe/houve tal evento em tal lugar e época?
      "agregacao",      // ranking ou contagem sobre muitos registros
      "comp_temporal",  // mesma região, épocas diferentes
      "comp_geografica",// mesma época, regiões diferentes
      "sazonalidade",   // em que meses/estação do ano ocorre
      "extremo",        // maior/menor valor, estação recordista
      "listagem",       // liste os eventos ocorridos
    ])
    .describe("Tipo de consulta — determina quais agregações do grafo serão recuperadas"),
});

export type Entidades = z.infer<typeof EntidadesSchema>;

export async function extrairEntidades(
  pergunta: string,
  historico: { role: string; content: string }[] = []
): Promise<Entidades> {
  const contextoHistorico = historico.length
    ? `Histórico recente da conversa:\n${historico.map(m => `${m.role === "user" ? "Usuário" : "Assistente"}: ${m.content}`).join("\n")}\n\n`
    : "";

  const { object } = await generateObject({
    model: modelos.rapido,
    schema: EntidadesSchema,
    prompt: `Extraia entidades climáticas e geográficas da pergunta abaixo sobre eventos climáticos no Brasil.
Hoje é ${new Date().toISOString().slice(0, 10)}.
Se a pergunta mencionar "este ano", "ano passado" ou similar, converta para datas absolutas.
Se nenhuma data for mencionada, retorne uma lista vazia em "periodos".

IMPORTANTE — janelas temporais. Distinga dois casos:

1) INTERVALO CONTÍNUO ("entre 2020 e 2024", "de 2018 a 2021", "nos últimos 3 anos",
   "em 2022"): é UMA única janela cobrindo todo o período, e comparativa=false.
   "entre 2020 e 2024" → [{inicio:"2020-01-01", fim:"2024-12-31", rotulo:"2020–2024"}]

2) ÉPOCAS CONTRASTADAS ("houve mais X em 2018 ou em 2020?", "compare 2019 com 2023",
   "2021 versus 2022"): UMA JANELA POR ÉPOCA, e comparativa=true.
   "2018 ou 2020" → [{inicio:"2018-01-01", fim:"2018-12-31", rotulo:"2018"},
                     {inicio:"2020-01-01", fim:"2020-12-31", rotulo:"2020"}]
   Nunca funda épocas contrastadas no intervalo 2018–2020.

IMPORTANTE — geografia: nomes de estados ("São Paulo", "Bahia", "Rio de Janeiro",
"Mato Grosso") vão em "estados" como sigla (SP, BA, RJ, MT) e NÃO em "municipios",
mesmo quando existe um município homônimo. Só coloque em "municipios" quando a
pergunta se refere claramente à cidade.

Use o histórico para resolver referências como "e em 2024?", "e no RS?", "e enchentes?" que dependem de contexto anterior.

${contextoHistorico}Pergunta: "${pergunta}"`,
  });
  return object;
}
