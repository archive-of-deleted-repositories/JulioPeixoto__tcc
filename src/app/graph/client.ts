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

export async function runQuery(
  cypher: string,
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>[]> {
  const session = getDriver().session();
  try {
    const result: QueryResult = await session.run(cypher, params);
    return result.records.map((r) => r.toObject());
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
