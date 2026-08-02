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

    # Départements dont la Série longue est chargée, séparés par des virgules. Les
    # fichiers Météo-France sont départementaux : c'est la maille de téléchargement,
    # pas un choix de périmètre. Un département voisin s'ajoute sans rien recharger.
    departements_climat: str = "38"

    @property
    def departements(self) -> list[str]:
        return [d.strip() for d in self.departements_climat.split(",") if d.strip()]


@lru_cache
def config() -> Config:
    return Config()
