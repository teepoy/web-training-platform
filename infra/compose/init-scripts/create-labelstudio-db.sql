SELECT 'CREATE DATABASE labelstudio'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'labelstudio')\gexec
