SELECT 'CREATE DATABASE upstream_mock'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'upstream_mock')\gexec
