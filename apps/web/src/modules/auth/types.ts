export type OrgRole = "admin" | "member";

export interface User {
  id: string;
  email: string;
  name: string;
  is_superadmin: boolean;
  is_active?: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface OrgMembership {
  id?: string;
  user_id?: string;
  org_id: string;
  org_name?: string;
  org_slug?: string;
  role: OrgRole;
  created_at?: string;
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
  user_id?: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface PersonalAccessTokenCreated extends PersonalAccessToken {
  token: string;
}

export interface OrgMember {
  id?: string;
  user_id: string;
  user_email?: string;
  user_name?: string;
  org_id?: string;
  role: OrgRole;
  created_at?: string;
  user?: User;
}

export interface OAuthCallbackResponse {
  action: "login" | "register";
  access_token?: string | null;
  user?: User | null;
  state_token?: string | null;
  email?: string | null;
  name?: string | null;
  provider?: string | null;
  provider_id?: string | null;
}

export interface OAuthProviderInfo {
  id: string;
  display_name: string;
  enabled: boolean;
}

export interface OAuthRegisterRequest {
  state_token: string;
  name: string;
}
