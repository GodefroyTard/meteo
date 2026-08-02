"""Constitution du périmètre de Stations suivies."""

from datetime import date

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from meteo.collecte import stations as collecte_stations
from meteo.config import config
from meteo.stockage.session import session
from meteo.stockage.tables import Station


def importer(aujourdhui: date | None = None) -> list[collecte_stations.StationTrouvee]:
    """Télécharge le référentiel StatIC et marque comme suivies les Stations du périmètre."""
    cfg = config()
    aujourdhui = aujourdhui or date.today()

    features = collecte_stations.telecharger()
    retenues = collecte_stations.autour(
        features, cfg.centre_lat, cfg.centre_lon, cfg.rayon_km, aujourdhui
    )

    with session() as s:
        s.execute(update(Station).values(suivie=False))
        for st in retenues:
            valeurs = {
                "code": st.code,
                "nom": st.nom,
                "latitude": st.latitude,
                "longitude": st.longitude,
                "altitude": st.altitude,
                "derniere_activite": st.derniere_activite,
                "suivie": True,
            }
            s.execute(
                insert(Station)
                .values(**valeurs)
                .on_conflict_do_update(index_elements=["code"], set_=valeurs)
            )
        s.commit()

    return retenues


def suivies() -> list[Station]:
    with session() as s:
        return list(s.query(Station).filter(Station.suivie.is_(True)).order_by(Station.code))
