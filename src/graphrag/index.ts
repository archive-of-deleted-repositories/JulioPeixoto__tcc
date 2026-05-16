import app from "./api/index.ts";

export default {
  port: Number(process.env.PORT ?? 3000),
  fetch: app.fetch,
};
