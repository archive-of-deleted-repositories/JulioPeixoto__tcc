import { db } from "./db.ts";

export type Mensagem = { role: "user" | "assistant"; content: string };

const MAX_HISTORICO = 10; // últimas 5 trocas

export function getHistorico(sessaoId: string): Mensagem[] {
  return db
    .query<Mensagem, string>(
      `SELECT role, content FROM mensagens
       WHERE sessao_id = ?
       ORDER BY criada_em DESC LIMIT ${MAX_HISTORICO}`
    )
    .all(sessaoId)
    .reverse();
}

export function salvarMensagem(
  sessaoId: string,
  role: "user" | "assistant",
  content: string
) {
  db.run(
    `INSERT INTO mensagens (sessao_id, role, content) VALUES (?, ?, ?)`,
    [sessaoId, role, content]
  );
}
