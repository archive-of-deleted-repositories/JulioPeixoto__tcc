import neo4j, { type QueryResult } from "neo4j-driver";

const driver = neo4j.driver(
  process.env.NEO4J_URI!,
  neo4j.auth.basic(process.env.NEO4J_USER!, process.env.NEO4J_PASSWORD!)
);

export async function runQuery(
  cypher: string,
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>[]> {
  const session = driver.session();
  try {
    const result: QueryResult = await session.run(cypher, params);
    return result.records.map((r) => r.toObject());
  } finally {
    await session.close();
  }
}

export async function closeDriver(): Promise<void> {
  await driver.close();
}
