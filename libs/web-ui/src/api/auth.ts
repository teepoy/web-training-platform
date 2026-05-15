import { req, getApiBase } from "./client";
import { ApiError } from "./client";
import type {
  LoginResponse,
  PersonalAccessToken,
  PersonalAccessTokenCreated,
  User,
  UserWithOrgs,
  OAuthRegisterRequest,
  OAuthProviderInfo,
} from "./types";

export function authLogin(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return req<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function authRegister(
  name: string,
  email: string,
  password: string,
): Promise<User> {
  return req<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
}

export function authMe(token?: string | null): Promise<UserWithOrgs> {
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return req<UserWithOrgs>("/auth/me", { headers });
}

export function authOAuthRegister(
  body: OAuthRegisterRequest,
): Promise<LoginResponse> {
  return req<LoginResponse>("/auth/oauth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchOAuthProviders(): Promise<OAuthProviderInfo[]> {
  return req<OAuthProviderInfo[]>("/auth/oauth/providers");
}

export async function fetchHealthStatus(): Promise<{
  status: string;
  auth_enabled: boolean;
}> {
  const r = await fetch(`${getApiBase()}/health`);
  if (!r.ok) {
    throw new ApiError(`health failed: ${r.status}`, r.status);
  }
  return r.json() as Promise<{ status: string; auth_enabled: boolean }>;
}

export function createToken(name: string): Promise<PersonalAccessTokenCreated> {
  return req<PersonalAccessTokenCreated>("/auth/tokens", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function listTokens(): Promise<PersonalAccessToken[]> {
  return req<PersonalAccessToken[]>("/auth/tokens");
}

export function deleteToken(id: string): Promise<void> {
  return req<void>(`/auth/tokens/${id}`, { method: "DELETE" });
}

export type { LoginResponse, User, UserWithOrgs, Organization, OrgRole, OrgMembership, PersonalAccessToken, PersonalAccessTokenCreated, OrgMember, OAuthCallbackResponse, OAuthProviderInfo, OAuthRegisterRequest } from "./types";
