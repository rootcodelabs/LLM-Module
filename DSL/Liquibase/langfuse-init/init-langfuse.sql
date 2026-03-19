SELECT 'CREATE DATABASE langfuse'
WHERE NOT EXISTS (
    SELECT FROM pg_catalog.pg_database WHERE datname = 'langfuse-db'
)\gexec
