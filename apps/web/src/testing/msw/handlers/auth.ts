import { http, HttpResponse } from "msw";
import { defaultUserWithOrgs, makeLoginResponse } from "../factories/user.factory";
import type { LoginResponse } from "@/generated/orval/models/loginResponse";

export const authMeHandler = http.get("/api/v1/auth/me", () => {
  return HttpResponse.json(defaultUserWithOrgs);
});

export const loginHandler = http.post("/api/v1/auth/login", async ({ request }) => {
  const body = (await request.json()) as { email: string; password: string };

  if (body.email && body.password) {
    const response: LoginResponse = makeLoginResponse({
      user: {
        ...makeLoginResponse().user,
        email: body.email,
      },
    });
    return HttpResponse.json(response);
  }

  return HttpResponse.json(
    { detail: "Invalid credentials" },
    { status: 401 },
  );
});

export const authHandlers = [authMeHandler, loginHandler];
