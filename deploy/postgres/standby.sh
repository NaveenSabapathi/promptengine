#!/bin/sh
set -eu
export PGPASSWORD=$(cat /run/secrets/replication_password)
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    pg_basebackup -h db -U promptlogic_replica -D "$PGDATA" -R -X stream --checkpoint=fast
fi
unset PGPASSWORD
# pg_basebackup -R does not persist PGPASSWORD; pgpass is read by WAL receiver.
printf 'db:5432:replication:promptlogic_replica:%s\n' "$(cat /run/secrets/replication_password)" > "$PGDATA/.pgpass"
chmod 600 "$PGDATA/.pgpass"
exec postgres -c hot_standby=on -c "primary_conninfo=host=db port=5432 user=promptlogic_replica passfile=$PGDATA/.pgpass application_name=promptlogic_secondary"
