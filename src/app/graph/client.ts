import neo4j, { type Driver, type QueryResult } from "neo4j-driver";

let _driver: Driver | null = null;

function getDriver(): Driver {
  if (!_driver) {
    const uri = process.env.NEO4J_URI;
    const user = process.env.NEO4J_USER;
    const password = process.env.NEO4J_PASSWORD;
    if (!uri || !user || !password) {
      throw new Error(
        "Variáveis NEO4J_URI, NEO4J_USER e NEO4J_PASSWORD são obrigatórias no .env"
      );
    }
    _driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  }
  return _driver;
}

/**
 * Converte os tipos próprios do driver Neo4j em valores JS nativos.
 *
 * Sem isso, um `count(e)` chega como `Integer {low: 227, high: 0}` e uma data
 * como `Date {year: {low: 2024...}, month: {...}}`. Esses objetos acabavam
 * serializados crus dentro do contexto enviado ao LLM — ruído que gasta tokens
 * e atrapalha a leitura dos números que a resposta precisa citar.
 */
function normalizar(valor: unknown): unknown {
  if (valor === null || valor === undefined) return valor;

  if (neo4j.isInt(valor)) {
    return (valor as { inSafeRange(): boolean; toNumber(): number; toString(): string })
      .inSafeRange()
      ? (valor as { toNumber(): number }).toNumber()
      : valor.toString();
  }

  // Date, DateTime, LocalDateTime, Time, Duration, Point: todos têm toString() útil.
  if (
    neo4j.isDate(valor) || neo4j.isDateTime(valor) || neo4j.isLocalDateTime(valor) ||
    neo4j.isLocalTime(valor) || neo4j.isTime(valor) || neo4j.isDuration(valor) ||
    neo4j.isPoint(valor)
  ) {
    return valor.toString();
  }

  if (Array.isArray(valor)) return valor.map(normalizar);

  if (typeof valor === "object") {
    const props = (valor as { properties?: Record<string, unknown> }).properties ?? valor;
    return Object.fromEntries(
      Object.entries(props as Record<string, unknown>).map(([k, v]) => [k, normalizar(v)])
    );
  }

  return valor;
}

export async function runQuery(
  cypher: string,
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>[]> {
  const session = getDriver().session();
  try {
    const result: QueryResult = await session.run(cypher, params);
    return result.records.map((r) => normalizar(r.toObject()) as Record<string, unknown>);
  } finally {
    await session.close();
  }
}

export async function closeDriver(): Promise<void> {
  if (_driver) {
    await _driver.close();
    _driver = null;
  }
}
