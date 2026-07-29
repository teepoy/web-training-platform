import { requestData, type ApiError } from "./client";

export type ErrorType<ErrorBody> = ApiError<ErrorBody>;
export type BodyType<BodyData> = BodyData;

/**
 * Custom fetch mutator for Orval-generated Vue Query hooks.
 * Injects auth token, org ID, handles errors and 204/205 responses.
 * The `url` parameter already includes the full path from the OpenAPI spec
 * (e.g. `/api/v1/datasets`), so no base prefix is prepended.
 */
export const orvalFetcher = async <T>(url: string, options: RequestInit): Promise<T> =>
  requestData<T>(url, options);
