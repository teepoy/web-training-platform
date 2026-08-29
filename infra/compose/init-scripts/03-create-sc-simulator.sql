SELECT 'CREATE DATABASE sc_simulator'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sc_simulator')\gexec
