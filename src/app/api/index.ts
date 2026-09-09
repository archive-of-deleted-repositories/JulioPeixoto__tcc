import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import { getCookie, setCookie } from "hono/cookie";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { extrairEntidades } from "../pipeline/entityExtractor.ts";
import { recuperarSubgrafo } from "../pipeline/graphRetriever.ts";
import { construirContexto } from "../pipeline/contextBuilder.ts";
import { gerarResposta } from "../pipeline/generator.ts";
import { getHistorico, salvarMensagem } from "../memory/index.ts";

const app = new Hono();

app.use("*", logger());
app.use("*", cors({ origin: "*", credentials: true }));

const ChatSchema = z.object({
  pergunta: z.string().max(1000),
});

app.post("/chat", zValidator("json", ChatSchema, (result, c) => {
  if (!result.success) return c.json({ erro: result.error.flatten().fieldErrors }, 400);
}), async (c) => {
  const { pergunta } = c.req.valid("json");

  // Obtém ou cria sessão via cookie
  let sessaoId = getCookie(c, "sessao_id");
  if (!sessaoId) {
    sessaoId = crypto.randomUUID();
    setCookie(c, "sessao_id", sessaoId, { httpOnly: true, sameSite: "Lax", maxAge: 60 * 60 * 24 * 7 });
  }

  const historico = getHistorico(sessaoId);
  salvarMensagem(sessaoId, "user", pergunta);

  return streamSSE(c, async (stream) => {
    let respostaCompleta = "";
    try {
      const entidades = await extrairEntidades(pergunta, historico);
      const { subgrafos, entidadesEfetivas } = await recuperarSubgrafo(entidades);
      const contexto = construirContexto(subgrafos);
      const resposta = gerarResposta(pergunta, contexto, historico);

      await stream.writeSSE({
        event: "meta",
        data: JSON.stringify({ entidades: entidadesEfetivas, num_registros: subgrafos.reduce((a, s) => a + s.records.length, 0) }),
      });

      for await (const chunk of (await resposta).textStream) {
        respostaCompleta += chunk;
        await stream.writeSSE({ data: chunk });
      }

      salvarMensagem(sessaoId!, "assistant", respostaCompleta);
      await stream.writeSSE({ event: "done", data: "" });
    } catch (err) {
      await stream.writeSSE({
        event: "error",
        data: err instanceof Error ? err.message : "Erro interno",
      });
    }
  });
});

app.get("/saude", (c) => c.json({ status: "ok", timestamp: new Date().toISOString() }));

app.post("/avaliar", async (c) => {
  const { gerarDatasetAvaliacao, PERGUNTAS_AVALIACAO } = await import("../evaluation/ragas.ts");
  const resultados = await gerarDatasetAvaliacao([...PERGUNTAS_AVALIACAO]);
  return c.json(resultados);
});

app.post("/indexar", async (c) => {
  const { runQuery } = await import("../graph/client.ts");
  const { indexarEventos, LABEL_INDEXADO } = await import("../baseline/vectorRag.ts");

  // Apaga o corpus anterior por inteiro. Remover só a propriedade `embedding`
  // deixava os nós para trás e cada reindexação duplicava o corpus.
  await runQuery(`MATCH (n:${LABEL_INDEXADO}) DETACH DELETE n`);

  const records = await runQuery(`
    MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
    WHERE e.fonte = 'INMET'
    RETURN m.nome AS municipio, m.uf AS uf,
           e.tipo AS tipo, toString(e.data) AS data,
           e.valor AS valor, f.nome AS fenomeno
  `);

  const eventos = records.map((r) => ({
    descricao: `${r.municipio} (${r.uf}) — ${r.fenomeno} — ${r.data} — valor: ${r.valor}`,
    metadata: { municipio: r.municipio, uf: r.uf, tipo: r.tipo, data: r.data, valor: r.valor },
  }));

  await indexarEventos(eventos);
  return c.json({ indexados: eventos.length });
});

app.get("/", async (c) => {
  const htmlPath = new URL("../frontend/index.html", import.meta.url).pathname
    .replace(/^\/([A-Za-z]:)/, "$1");
  const html = await Bun.file(htmlPath).text();
  return c.html(html);
});

export default app;
