import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import { upstreamMockConfig } from "./config";
import * as schema from "./schema";

const globalDatabase = globalThis as typeof globalThis & {
  upstreamMockPool?: Pool;
};

export const pool =
  globalDatabase.upstreamMockPool ??
  new Pool({ connectionString: upstreamMockConfig.databaseUrl() });

if (process.env.NODE_ENV !== "production") globalDatabase.upstreamMockPool = pool;

export const db = drizzle({ client: pool, schema });
