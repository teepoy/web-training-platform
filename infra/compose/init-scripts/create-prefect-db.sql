-- Auto-create the "prefect" database used by prefect-server.
-- Postgres only runs scripts in /docker-entrypoint-initdb.d on first
-- initialisation (empty data volume), so this is safe to mount always.

SELECT 'CREATE DATABASE prefect'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'prefect')\gexec
