#!/bin/sh
# First initialization only; apply manually via psql for an existing primary.
set -eu
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<'SQL'
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='promptlogic_replica') THEN
  CREATE ROLE promptlogic_replica WITH LOGIN REPLICATION NOSUPERUSER NOCREATEDB NOCREATEROLE;
END IF;
END $$;
SQL
# Never expose replication publicly. Dedicated internal network and SCRAM only.
printf '\nhost replication promptlogic_replica all scram-sha-256\n' >> "$PGDATA/pg_hba.conf"
