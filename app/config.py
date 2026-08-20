from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración central de la app.

    Lee las variables desde `.env` (véase `.env.example`). Los campos marcados
    como `SecretStr` nunca se exponen en logs ni en la serialización: evita que
    credenciales de Supabase viajen al frontend.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Identidad de la aplicación
    app_name: str = "Sistema Generador de Horarios"
    app_version: str = "0.1.0"

    # --- Credenciales Supabase (SecretStr: no se imprimen) ---
    # URL base del proyecto (https://<ref>.supabase.co)
    supabase_url: SecretStr = SecretStr("")
    # Clave pública "anon" (frontend) o de servicio (backend), según el rol
    supabase_key: SecretStr = SecretStr("")
    # Cadena de conexión del pooler de Postgres (usuaria de la base)
    database_url: SecretStr = SecretStr("")

    # --- CORS: orígenes permitidos, separados por coma ---
    cors_origins: str = "http://localhost:3000"
    # Patrón regex opcional para orígenes dinámicos (ej. previews de Vercel).
    # Vacío = desactivado. Ej: "https://.*\.vercel\.app"
    cors_origin_regex: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        """Lista de orígenes CORS (a partir del string plano)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex_value(self) -> str | None:
        """Regex de CORS como string o None si no está definida."""
        return self.cors_origin_regex.strip() or None

    @property
    def database_url_value(self) -> str:
        return self.database_url.get_secret_value()

    @property
    def supabase_url_value(self) -> str:
        return self.supabase_url.get_secret_value()

    @property
    def supabase_key_value(self) -> str:
        return self.supabase_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Singleton: la configuración se lee una sola vez y se reutiliza."""
    return Settings()