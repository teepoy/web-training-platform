/**
 * Auth seed helpers — login / logout using orval-generated API functions.
 */
import type { LoginRequest, LoginResponse, UserResponse } from '../../src/generated/orval/models';
import { loginApiV1AuthLoginPost, authMeApiV1AuthMeGet } from '../../src/generated/orval/endpoints/api';

export interface SeedAuthResult {
  token: string;
  user: UserResponse;
}

/**
 * Authenticate against the backend and return the JWT token + user.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) BEFORE this
 * so the orval fetcher is configured (even without a token — login
 * itself is unauthenticated).
 */
export async function seedLogin(loginRequest: LoginRequest): Promise<SeedAuthResult> {
  const res = await loginApiV1AuthLoginPost(loginRequest);
  const body = res.data as LoginResponse;
  return { token: body.access_token, user: body.user };
}

/**
 * Invalidate the current session by clearing the configured token.
 *
 * There is no explicit logout endpoint in the API — the caller should
 * call {@link getSeedClient} (from `./client`) without a token to
 * reset the auth state.
 */
export async function seedLogout(): Promise<void> {
  // No-op: the caller should create a new seed client without a token.
}
