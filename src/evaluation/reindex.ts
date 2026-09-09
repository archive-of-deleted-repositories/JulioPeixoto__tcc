/**
 * Reconstrói o índice vetorial do baseline VectorRAG.
 *
 * O corpus indexado fica no label `EventoIndexado`, separado do `Evento` do
 * grafo (ver comentário em src/app/baseline/vectorRag.ts). Este script:
 *   1. apaga o corpus anterior e o índice vetorial;
 *   2. remove os nós órfãos que versões antigas criaram dentro de `:Evento`;
 *   3. reindexa todos os eventos INMET ligados a um município.
 *
 * Uso: bun run src/evaluation/reindex.ts
 */

import { runQuery } from "../app/graph/client.ts";
import { indexarEventos, LABEL_INDEXADO } from "../app/baseline/vectorRag.ts";

console.log("Limpando corpus vetorial anterior...");
await runQuery(`MATCH (n:${LABEL_INDEXADO}) DETACH DELETE n`);
try {
  await runQuery(`DROP INDEX eventos_vector IF EXISTS`);
} catch (err) {
  console.warn(`  (índice não removido: ${(err as Error).message})`);
}

// Nós que o LangChain criou dentro de :Evento em execuções anteriores.
// Reconhecíveis por não terem fonte e por não terem nenhuma aresta.
const [orfaos] = await runQuery(`
  MATCH (e:Evento) WHERE e.fonte IS NULL AND NOT (e)--()
  RETURN count(e) AS total
`);
const totalOrfaos = Number(orfaos?.total ?? 0);
if (totalOrfaos > 0) {
  console.log(`Removendo ${totalOrfaos} nós :Evento órfãos de indexações antigas...`);
  await runQuery(`
    MATCH (e:Evento) WHERE e.fonte IS NULL AND NOT (e)--()
    CALL { WITH e DELETE e } IN TRANSACTIONS OF 5000 ROWS
  `);
}

console.log("Carregando eventos do grafo...");
const records = await runQuery(`
  MATCH (m:Municipio)-[:SOFREU]->(e:Evento)-[:CAUSADO_POR]->(f:Fenomeno)
  MATCH (s:Estacao)-[:REGISTROU]->(e)
  WHERE e.fonte = 'INMET'
  RETURN m.nome AS municipio, m.uf AS uf,
         e.tipo AS tipo, toString(e.data) AS data,
         e.valor AS valor, f.nome AS fenomeno,
         s.codigo AS estacao, s.nome AS estacao_nome
`);

console.log(`${records.length} eventos carregados. Indexando (alguns minutos)...`);

const eventos = records.map((r) => ({
  // A estação entra na descrição para que perguntas de travessia
  // (qual estação registrou o extremo) sejam ao menos alcançáveis
  // pela busca por similaridade — sem isso o baseline seria injusto.
  descricao:
    `${r.municipio} (${r.uf}) — ${r.fenomeno} — ${r.data} — ` +
    `valor: ${r.valor} — estação ${r.estacao} (${r.estacao_nome})`,
  metadata: {
    municipio: r.municipio,
    uf: r.uf,
    tipo: r.tipo,
    data: r.data,
    valor: r.valor,
    estacao: r.estacao,
    ano: Number(String(r.data).slice(0, 4)),
  },
}));

await indexarEventos(eventos);

const [conferencia] = await runQuery(`
  MATCH (n:${LABEL_INDEXADO}) RETURN count(n) AS total
`);
const [grafo] = await runQuery(`MATCH (e:Evento) RETURN count(e) AS total`);

console.log(`\nCorpus vetorial : ${conferencia?.total} nós :${LABEL_INDEXADO}`);
console.log(`Grafo           : ${grafo?.total} nós :Evento`);
process.exit(0);
