import { req, getApiBase } from "../client/apiClient";

export type OrgRole = "admin" | "member";

export interface User {
  id: string;
  email: string;
  name: string;
  is_superadmin: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface OrgMembership {
  id: string;
  user_id: string;
  org_id: string;
  role: OrgRole;
  created_at: string;
}

export interface UserWithOrgs extends User {
  organizations: OrgMembership[];
}

export interface LoginResponse {
  access_token: string;
  user: User;
}

export interface PersonalAccessToken {
  id: string;
  user_id: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface PersonalAccessTokenCreated extends PersonalAccessToken {
  token: string;
}

export interface OrgMember {
  user_id: string;
  org_id: string;
  role: OrgRole;
  user: User;
}

export function fetchOrganizations(): Promise<Organization[]> {
  return req<Organization[]>("/organizations");
}

export function authLogin(email: string, password: string): Promise<LoginResponse> {
  return req<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function authRegister(name: string, email: string, password: string): Promise<User> {
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

export async function fetchHealthStatus(): Promise<{ status: string; auth_enabled: boolean }> {
  const r = await fetch(`${getApiBase()}/health`);
  if (!r.ok) throw new Error(`health check failed: ${r.status}`);
  return r.json() as Promise<{ status: string; auth_enabled: boolean }>;
}
