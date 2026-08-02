"""Configuration lue depuis l'environnement."""

from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METEO_", env_file=".env", extra="ignore")

    dsn: str = "postgresql+psycopg://meteo:meteo@localhost:5433/meteo"

    # Le jeton Infoclimat est lié à une adresse IP déclarée : la collecte des
    # Observations ne fonctionne que depuis la machine déclarée.
    jeton_infoclimat: str = ""

    centre_lat: float = 45.1885
    centre_lon: float = 5.7245
    rayon_km: float = 20.0

    debut_historique: date = date(2024, 2, 4)


@lru_cache
def config() -> Config:
    return Config()
