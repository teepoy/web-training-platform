/** Shared mock constants for Playwright route handlers and factories. */
export const MOCK_AUTH_TOKEN = "e2e-token";
const mockPort = process.env.PLAYWRIGHT_PORT || "5174";
export const MOCK_BASE_URL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${mockPort}`;
export const MOCK_ORG_ID = "org-e2e-1";
