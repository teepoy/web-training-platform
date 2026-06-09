import type { UserWithOrgsResponse } from '@/generated/orval/models'
import type { MembershipResponse } from '@/generated/orval/models'

/**
 * Extended mock user type matching the shape the app's auth/me endpoint
 * returns in mock mode. Differs from orval's UserWithOrgsResponse by including
 * `is_active` and richer membership fields.
 */
export interface MockUser extends UserWithOrgsResponse {
  is_active: boolean
  organizations: MockMembership[]
}

export interface MockMembership extends MembershipResponse {
  id: string
  user_id: string
  created_at: string
}

export function makeUser(overrides?: Partial<MockUser>): MockUser {
  return {
    id: 'user-e2e-1',
    email: 'e2e@example.com',
    name: 'E2E User',
    is_superadmin: false,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    organizations: [
      {
        id: 'membership-e2e-1',
        user_id: 'user-e2e-1',
        org_id: 'org-e2e-1',
        org_name: 'E2E Org',
        org_slug: 'e2e-org',
        role: 'admin',
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
    ...overrides,
  }
}
