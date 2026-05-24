/**
 * Reindexação standalone de todos os eventos no Neo4j Vector Index.
 *
 * Remove embeddings antigos e recria o índice com todos os 33.501 eventos.
 * Não requer o servidor HTTP — conecta-se diretamente ao Neo4j.
 *
 * Uso: bun run src/evaluation/reindex.ts
 */

import { runQuery } from "../app/graph/client.ts";
import { indexarEventos } from "../app/baseline/vectorRag.ts";

console.log("Removendo embeddings existentes...");
await runQuery(`MATCH (n:Evento) WHERE n.embedding IS NOT NULL REMOVE n.embedding`);
console.log("Embeddings anteriores removidos.");

console.log("Carregando todos os eventos do grafo...");
const records = await runQuery(`
  MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
  WHERE e.fonte = 'INMET'
  RETURN m.nome AS municipio, m.uf AS uf,
         e.tipo AS tipo, toString(e.data) AS data,
         e.valor AS valor, f.nome AS fenomeno
`);

console.log(`${records.length} eventos carregados. Iniciando indexação (pode levar alguns minutos)...`);

const eventos = records.map((r) => ({
  descricao: `${r.municipio} (${r.uf}) — ${r.fenomeno} — ${r.data} — valor: ${r.valor}`,
  metadata: {
    municipio: r.municipio,
    uf: r.uf,
    tipo: r.tipo,
    data: r.data,
    valor: r.valor,
  },
}));

await indexarEventos(eventos);

console.log(`\nReindexação concluída: ${eventos.length} eventos no vector index.`);
process.exit(0);
