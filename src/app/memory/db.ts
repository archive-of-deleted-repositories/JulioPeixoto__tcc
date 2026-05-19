import { Database } from "bun:sqlite";
import { join } from "path";

const db = new Database(join(import.meta.dir, "../../../data/chat.db"), { create: true });

db.run(`
  CREATE TABLE IF NOT EXISTS mensagens (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id TEXT    NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    criada_em INTEGER DEFAULT (unixepoch())
  )
`);

db.run(`CREATE INDEX IF NOT EXISTS idx_sessao ON mensagens (sessao_id, criada_em)`);

export { db };
