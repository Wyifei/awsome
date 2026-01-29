kubectl exec -it -n auth-platform deploy/postgres-client -- \
    psql -h $PGHOST -U $PGUSER -d $PGDATABASE