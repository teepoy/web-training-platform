import { setupServer } from "msw/node";
import { authHandlers } from "./handlers/auth";
import { datasetHandlers } from "./handlers/datasets";

const defaultHandlers = [...authHandlers, ...datasetHandlers];

export const server = setupServer(...defaultHandlers);
