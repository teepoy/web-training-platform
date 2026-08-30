function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function databaseUrl(): string {
  const value = required("UPSTREAM_MOCK_DATABASE_URL");
  if (!value.startsWith("postgresql://") && !value.startsWith("postgres://")) {
    throw new Error("UPSTREAM_MOCK_DATABASE_URL must use PostgreSQL");
  }
  return value;
}

export const upstreamMockConfig = {
  databaseUrl,
  apiToken: () => required("UPSTREAM_MOCK_API_TOKEN"),
  s3: () => ({
    endpoint: required("UPSTREAM_MOCK_S3_ENDPOINT"),
    accessKeyId: required("UPSTREAM_MOCK_S3_ACCESS_KEY"),
    secretAccessKey: required("UPSTREAM_MOCK_S3_SECRET_KEY"),
    region: required("UPSTREAM_MOCK_S3_REGION"),
    patchBucket: required("UPSTREAM_MOCK_PATCH_BUCKET"),
    reviewBucket: required("UPSTREAM_MOCK_REVIEW_BUCKET"),
  }),
};
