/**
 * Gera as respostas dos três modos (No RAG, VectorRAG, GraphRAG) para todas as
 * perguntas do benchmark. Não sobe servidor HTTP.
 *
 * Uso:
 *   bun run src/evaluation/run_eval.ts            # benchmark completo
 *   bun run src/evaluation/run_eval.ts C3 C7      # só as categorias indicadas
 */

import { gerarDatasetAvaliacao, PERGUNTAS_AVALIACAO } from "../app/evaluation/ragas.ts";
import { mkdir } from "node:fs/promises";
import { closeDriver } from "../app/graph/client.ts";

const EVAL_DIR = new URL("../../data/evaluation/", import.meta.url).pathname.replace(
  /^\/([A-Za-z]:)/,
  "$1"
);
await mkdir(EVAL_DIR, { recursive: true });

const filtros = process.argv.slice(2);
const perguntas = filtros.length
  ? PERGUNTAS_AVALIACAO.filter((p) =>
      filtros.some((f: string) => (p.categoria ?? "").startsWith(f))
    )
  : [...PERGUNTAS_AVALIACAO];

if (perguntas.length === 0) {
  console.error(`Nenhuma pergunta casou com: ${filtros.join(", ")}`);
  process.exit(1);
}

const porCategoria = new Map<string, number>();
for (const p of perguntas) {
  const c = p.categoria ?? "legado";
  porCategoria.set(c, (porCategoria.get(c) ?? 0) + 1);
}

console.log(`\nAvaliação — ${perguntas.length} perguntas × 3 modos`);
for (const [cat, n] of [...porCategoria].sort()) console.log(`  ${cat.padEnd(22)} ${n}`);
console.log();

const inicio = Date.now();
const resultados = await gerarDatasetAvaliacao(perguntas);
const minutos = ((Date.now() - inicio) / 60000).toFixed(1);

const outPath = `${EVAL_DIR}respostas_brutas.json`;
await Bun.write(outPath, JSON.stringify(resultados, null, 2));

const semContextoGrafo = resultados.filter((r) =>
  r.contexto_graphrag.startsWith("Nenhum dado encontrado")
).length;
const semContextoVetor = resultados.filter((r) => !r.contexto_vectorrag.trim()).length;
const falhas = resultados.filter((r) =>
  [r.resposta_norag, r.resposta_vectorrag, r.resposta_graphrag].some((t) => t.startsWith("[falha"))
).length;

console.log(`\nRespostas salvas em: ${outPath}  (${minutos} min)`);
console.log(`  perguntas sem contexto do grafo : ${semContextoGrafo}`);
console.log(`  perguntas sem contexto vetorial : ${semContextoVetor}`);
console.log(`  gerações que falharam           : ${falhas}`);
console.log(`\nPróximo passo: .venv/Scripts/python.exe src/evaluation/ragas_eval.py`);

// O driver do Neo4j mantém sockets abertos e segura o event loop: sem fechar,
// o processo fica pendurado depois de imprimir o resumo — e um encadeamento
// `run_eval && ragas_eval` nunca chega no segundo comando.
await closeDriver();
process.exit(0);
