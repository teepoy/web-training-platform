#!/usr/bin/env node

import { readFile } from "node:fs/promises";

import { Command } from "commander";

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

async function loadJson(path: string): Promise<Record<string, unknown>> {
  const value: unknown = JSON.parse(await readFile(path, "utf8"));
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("request file must contain one JSON object");
  }
  return value as Record<string, unknown>;
}

async function request(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<void> {
  const baseUrl = requiredEnvironment("UPSTREAM_MOCK_URL").replace(/\/$/, "");
  const token = requiredEnvironment("UPSTREAM_MOCK_TOKEN");
  const timeoutSeconds = Number(requiredEnvironment("UPSTREAM_MOCK_TIMEOUT_SECONDS"));
  if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
    throw new Error("UPSTREAM_MOCK_TIMEOUT_SECONDS must be positive");
  }
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutSeconds * 1000),
  });
  if (!response.ok) throw new Error(await response.text());
  if (response.status !== 204) {
    console.log(JSON.stringify(await response.json(), null, 2));
  }
}

// This disposable control plane is intentionally outside the product OpenAPI.
// Keep its private route construction in one place instead of scattering URLs.
function controlPath(...segments: string[]): string {
  return `/${["api", "v1", ...segments].join("/")}`;
}

const controlRoutes = {
  inspections: controlPath("inspections"),
  records: controlPath("inspections", "records"),
  publish: controlPath("inspections", "publish"),
  inspect: controlPath("inspections", "inspect"),
  showcase: controlPath("scenarios", "dev-showcase"),
};

function fileCommand(program: Command, name: string, method: string, path: string) {
  program
    .command(name)
    .requiredOption("--file <path>", "JSON request body")
    .action(async ({ file }: { file: string }) => {
      await request(method, path, await loadJson(file));
    });
}

const program = new Command()
  .name("upstream-mock")
  .description("Control the independent development upstream mock over HTTP");

fileCommand(program, "create", "POST", controlRoutes.inspections);
fileCommand(program, "append", "POST", controlRoutes.records);
fileCommand(program, "update", "PATCH", controlRoutes.inspections);
fileCommand(program, "dev-showcase", "POST", controlRoutes.showcase);

program
  .command("publish")
  .requiredOption("--wafer-key <number>")
  .requiredOption("--inspection-time <timestamp>")
  .requiredOption("--published-at <timestamp>")
  .action(async (options) => {
    await request("POST", controlRoutes.publish, {
      wafer_key: Number(options.waferKey),
      inspection_time: options.inspectionTime,
      published_at: options.publishedAt,
    });
  });

program
  .command("inspect")
  .requiredOption("--wafer-key <number>")
  .requiredOption("--inspection-time <timestamp>")
  .action(async (options) => {
    await request("POST", controlRoutes.inspect, {
      wafer_key: Number(options.waferKey),
      inspection_time: options.inspectionTime,
    });
  });

program
  .command("list")
  .option("--state <state>", "draft or published")
  .action(async ({ state }: { state?: string }) => {
    if (state && state !== "draft" && state !== "published") {
      throw new Error("--state must be draft or published");
    }
    await request("GET", `${controlRoutes.inspections}${state ? `?state=${state}` : ""}`);
  });

program.parseAsync().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
