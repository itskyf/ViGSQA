SET client_min_messages = warning;

CREATE OR REPLACE FUNCTION pg_temp.configure_role(
    role_name text,
    role_password text
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    EXECUTE format(
        'ALTER ROLE %I WITH PASSWORD %L',
        role_name,
        role_password
    );
END
$$;

SELECT pg_temp.configure_role(:'db_user', :'db_password');

CREATE EXTENSION IF NOT EXISTS postgis;
