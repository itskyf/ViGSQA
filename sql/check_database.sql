SELECT
    EXISTS(
        SELECT 1
        FROM pg_database
        WHERE datname = :'db_name'
    )::int AS database_exists,
    EXISTS(
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'db_user'
    )::int AS role_exists;
