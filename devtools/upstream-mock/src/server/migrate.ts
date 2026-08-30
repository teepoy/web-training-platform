import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { pool } from "./db";

const migration = fileURLToPath(new URL("../../migrations/0001_initial.sql", import.meta.url));

async function main(): Promise<void> {
  const sql = await readFile(migration, "utf8");
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(sql);
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
    await pool.end();
  }
}

void main();
