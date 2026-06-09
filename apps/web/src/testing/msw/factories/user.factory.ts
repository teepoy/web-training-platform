import type { UserResponse } from "@/generated/orval/models/userResponse";
import type { UserWithOrgsResponse } from "@/generated/orval/models/userWithOrgsResponse";
import type { LoginResponse } from "@/generated/orval/models/loginResponse";

export const defaultUser: UserResponse = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "test@example.com",
  name: "Test User",
  is_superadmin: false,
  created_at: "2025-01-01T00:00:00Z",
};

export function makeUser(overrides?: Partial<UserResponse>): UserResponse {
  return { ...defaultUser, ...overrides };
}

export const defaultUserWithOrgs: UserWithOrgsResponse = {
  ...defaultUser,
  organizations: [],
};

export function makeUserWithOrgs(
  overrides?: Partial<UserWithOrgsResponse>,
): UserWithOrgsResponse {
  return { ...defaultUserWithOrgs, ...overrides };
}

export const defaultLoginResponse: LoginResponse = {
  access_token: "mock-jwt-token",
  user: defaultUser,
};

export function makeLoginResponse(
  overrides?: Partial<LoginResponse>,
): LoginResponse {
  return { ...defaultLoginResponse, ...overrides };
}
