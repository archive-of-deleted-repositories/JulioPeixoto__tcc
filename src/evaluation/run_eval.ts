/**
 * Roda a avaliação diretamente (sem servidor HTTP).
 * Uso: bun run src/evaluation/run_eval.ts
 */

import { gerarDatasetAvaliacao, PERGUNTAS_AVALIACAO } from "../app/evaluation/ragas.ts";
import { mkdir } from "node:fs/promises";

const EVAL_DIR = new URL("../../data/evaluation/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");

await mkdir(EVAL_DIR, { recursive: true });

console.log(`\nIniciando avaliação — ${PERGUNTAS_AVALIACAO.length} perguntas × 3 modos\n`);

const resultados = await gerarDatasetAvaliacao([...PERGUNTAS_AVALIACAO]);

const outPath = `${EVAL_DIR}respostas_brutas.json`;
await Bun.write(outPath, JSON.stringify(resultados, null, 2));

console.log(`\nRespostas salvas em: ${outPath}`);
console.log("\n=== RESUMO ===");
for (const r of resultados) {
  console.log(`\nPergunta: ${r.pergunta.slice(0, 70)}...`);
  console.log(`  [No RAG]     ${r.resposta_norag.slice(0, 80)}...`);
  console.log(`  [VectorRAG]  ${r.resposta_vectorrag.slice(0, 80)}...`);
  console.log(`  [GraphRAG]   ${r.resposta_graphrag.slice(0, 80)}...`);
}
