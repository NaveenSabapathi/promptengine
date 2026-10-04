#!/bin/sh
# Official PostgreSQL entrypoint sources this only on first-volume initialization.
# psql literal interpolation safely quotes punctuation in the password.
set -eu
psql --username postgres --dbname postgres --set=ON_ERROR_STOP=1 \
    --set=app_password="$(cat /run/secrets/postgres_password)" <<'SQL'
CREATE ROLE promptengine WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
CREATE DATABASE promptengine OWNER promptengine;
SQL
