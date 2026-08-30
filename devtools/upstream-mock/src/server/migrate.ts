import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { pool } from "./db";

const migrationsDirectory = fileURLToPath(new URL("../../migrations", import.meta.url));

async function main(): Promise<void> {
  const migrations = (await readdir(migrationsDirectory))
    .filter((name) => name.endsWith(".sql"))
    .sort();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    for (const migration of migrations) {
      const sql = await readFile(`${migrationsDirectory}/${migration}`, "utf8");
      await client.query(sql);
    }
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
