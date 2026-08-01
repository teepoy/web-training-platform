import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const artifacts = path.join(root, ".artifacts");

export const E2E_PATHS = Object.freeze({
  root,
  specs: path.join(root, "specs"),
  artifacts,
  authState: path.join(artifacts, "auth", "state.json"),
  report: path.join(artifacts, "report"),
  testResults: path.join(artifacts, "test-results"),
});
