-- Roles applicatifs en lecture seule. Script idempotent, execute au premier demarrage de
-- PostgreSQL puis a chaque deploiement.
-- Variables psql attendues : pw_monitoring et pw_api.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

-- Supervision : Grafana et postgres-exporter
SELECT format('CREATE ROLE monitoring_ro LOGIN PASSWORD %L', :'pw_monitoring')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitoring_ro') \gexec
SELECT format('ALTER ROLE monitoring_ro PASSWORD %L', :'pw_monitoring') \gexec
ALTER ROLE monitoring_ro SET default_transaction_read_only = on;
GRANT pg_monitor TO monitoring_ro;
GRANT pg_read_all_data TO monitoring_ro;

-- API : lecture des marts et de ops uniquement, jamais des donnees brutes
SELECT format('CREATE ROLE api_ro LOGIN CONNECTION LIMIT 10 PASSWORD %L', :'pw_api')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') \gexec
SELECT format('ALTER ROLE api_ro PASSWORD %L', :'pw_api') \gexec
ALTER ROLE api_ro SET default_transaction_read_only = on;
ALTER ROLE api_ro SET statement_timeout = '10s';
GRANT USAGE ON SCHEMA marts, ops TO api_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA marts, ops TO api_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO api_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT SELECT ON TABLES TO api_ro;
