"""Runtime settings shared by ViGSQA database clients."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings loaded from standard libpq variables."""

    model_config = SettingsConfigDict(extra="ignore")

    host: str = Field("127.0.0.1", validation_alias="PGHOST")
    port: int = Field(5432, validation_alias="PGPORT")
    dbname: str = Field("osm_vn", validation_alias="PGDATABASE")
    user: str = Field("postgres", validation_alias="PGUSER")
    password: SecretStr = Field(SecretStr("postgres"), validation_alias="PGPASSWORD")

    def connection_kwargs(self) -> dict[str, str | int]:
        """Return keyword arguments accepted by psycopg clients."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password.get_secret_value(),
        }

    def libpq_environ(self) -> dict[str, str]:
        """Return standard libpq environment variables for subprocesses."""
        return {
            "PGHOST": self.host,
            "PGPORT": str(self.port),
            "PGDATABASE": self.dbname,
            "PGUSER": self.user,
            "PGPASSWORD": self.password.get_secret_value(),
        }
