import { defineConfig } from "orval";

export default defineConfig({
  api: {
    input: {
      target: "../../openapi/openapi.yaml",
    },
    output: {
      mode: "single",
      target: "src/generated/orval/endpoints/api.ts",
      schemas: "src/generated/orval/models",
      client: "vue-query",
      httpClient: "fetch",
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: "src/shared/api/orval-fetcher.ts",
          name: "orvalFetcher",
        },
      },
    },
  },
});
