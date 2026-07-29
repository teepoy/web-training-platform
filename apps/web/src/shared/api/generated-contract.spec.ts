import { describe, expectTypeOf, it } from "vitest";
import {
  getDatasetApiV1DatasetsDatasetIdGet,
  listDatasetsApiV1DatasetsGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, PaginatedResponseDataset } from "@/generated/orval/models";

describe("generated success contracts", () => {
  it("return success DTOs rather than HTTP response envelopes or validation unions", () => {
    expectTypeOf(getDatasetApiV1DatasetsDatasetIdGet).returns.resolves.toEqualTypeOf<Dataset>();
    expectTypeOf(
      listDatasetsApiV1DatasetsGet,
    ).returns.resolves.toEqualTypeOf<PaginatedResponseDataset>();
  });
});
