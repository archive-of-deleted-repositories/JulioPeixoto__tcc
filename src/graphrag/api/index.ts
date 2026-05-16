import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { cors } from "hono/cors";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { extrairEntidades } from "../pipeline/entityExtractor.ts";
import { recuperarSubgrafo } from "../pipeline/graphRetriever.ts";
import { construirContexto } from "../pipeline/contextBuilder.ts";
import { gerarResposta } from "../pipeline/generator.ts";
import { gerarDatasetAvaliacao, PERGUNTAS_AVALIACAO } from "../evaluation/ragas.ts";

const app = new Hono();

app.use("*", cors());

const ChatSchema = z.object({
  pergunta: z.string().min(5).max(1000),
});

app.post("/chat", zValidator("json", ChatSchema), async (c) => {
  const { pergunta } = c.req.valid("json");

  return streamSSE(c, async (stream) => {
    try {
      const entidades = await extrairEntidades(pergunta);
      const subgrafos = await recuperarSubgrafo(entidades);
      const contexto = construirContexto(subgrafos);
      const resposta = gerarResposta(pergunta, contexto);

      // Envia metadados antes do texto
      await stream.writeSSE({
        event: "meta",
        data: JSON.stringify({ entidades, num_registros: subgrafos.reduce((a, s) => a + s.records.length, 0) }),
      });

      for await (const chunk of (await resposta).textStream) {
        await stream.writeSSE({ data: chunk });
      }

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
  const resultados = await gerarDatasetAvaliacao([...PERGUNTAS_AVALIACAO]);
  return c.json(resultados);
});

app.get("/", (c) => {
  return c.html(Bun.file(new URL("../frontend/index.html", import.meta.url).pathname).text());
});

export default app;
