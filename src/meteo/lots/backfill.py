"""Alimentation de la base en Prévisions et en Observations.

Les deux collectes sont indépendantes et rejouables : réexécuter un backfill sur une
période déjà chargée met à jour les lignes au lieu de les dupliquer.
"""

from collections.abc import Iterable, Iterator
from datetime import date
from itertools import islice

from sqlalchemy.dialects.postgresql import insert

from meteo.collecte.infoclimat import ClientInfoclimat, ValeurObservee
from meteo.collecte.open_meteo import ClientOpenMeteo, ValeurPrevue
from meteo.config import config
from meteo.domaine.modeles import CATALOGUE
from meteo.domaine.qualite import MesureBrute, valider
from meteo.lots.referentiel import suivies
from meteo.stockage.session import session
from meteo.stockage.tables import Observation, Prevision

TAILLE_LOT = 5000


def _par_paquets(source: Iterable[dict], taille: int) -> Iterator[list[dict]]:
    it = iter(source)
    while paquet := list(islice(it, taille)):
        yield paquet


def _enregistrer(table, lignes: Iterable[dict], cles: list[str]) -> int:
    total = 0
    with session() as s:
        for paquet in _par_paquets(lignes, TAILLE_LOT):
            requete = insert(table)
            colonnes = [c for c in paquet[0] if c not in cles]
            s.execute(
                requete.on_conflict_do_update(
                    index_elements=cles,
                    set_={c: getattr(requete.excluded, c) for c in colonnes},
                ),
                paquet,
            )
            s.commit()
            total += len(paquet)
    return total


def _ligne_prevision(code: str, v: ValeurPrevue) -> dict:
    return {
        "station_code": code,
        "modele": v.modele,
        "anticipation": v.anticipation,
        "instant": v.instant,
        "temperature_c": v.temperature_c,
        "precipitation_mm": v.precipitation_mm,
    }


def previsions(debut: date | None = None, fin: date | None = None) -> int:
    """Télécharge les Prévisions passées de tous les Modèles pour les Stations suivies."""
    cfg = config()
    debut = debut or cfg.debut_historique
    fin = fin or date.today()

    client = ClientOpenMeteo()
    total = 0
    try:
        for station in suivies():
            for modele in CATALOGUE:
                valeurs = client.previsions(
                    latitude=station.latitude,
                    longitude=station.longitude,
                    altitude=station.altitude,
                    modele=modele,
                    debut=debut,
                    fin=fin,
                )
                total += _enregistrer(
                    Prevision,
                    (_ligne_prevision(station.code, v) for v in valeurs),
                    ["station_code", "modele", "anticipation", "instant"],
                )
    finally:
        client.close()
    return total


def observations(debut: date | None = None, fin: date | None = None) -> int:
    """Télécharge les Observations des Stations suivies et applique les garde-fous.

    Ne fonctionne que depuis la machine dont l'adresse IP est déclarée auprès
    d'Infoclimat.
    """
    cfg = config()
    debut = debut or cfg.debut_historique
    fin = fin or date.today()

    codes = [s.code for s in suivies()]
    if not codes:
        return 0

    client = ClientInfoclimat(cfg.jeton_infoclimat)
    total = 0
    try:
        # Toutes les Stations sont demandées ensemble : le plafond de 7 jours porte
        # sur la période et non sur le nombre de Stations.
        brutes: dict[str, list[ValeurObservee]] = {c: [] for c in codes}
        for v in client.observations(codes, debut, fin):
            brutes.setdefault(v.station_code, []).append(v)

        for code, valeurs in brutes.items():
            if not valeurs:
                continue
            valeurs.sort(key=lambda v: v.instant)
            marques = valider([MesureBrute(v.temperature_c, v.precipitation_mm) for v in valeurs])
            total += _enregistrer(
                Observation,
                (
                    {
                        "station_code": code,
                        "instant": v.instant,
                        "temperature_c": v.temperature_c,
                        "precipitation_mm": v.precipitation_mm,
                        "valide": ok,
                    }
                    for v, ok in zip(valeurs, marques, strict=True)
                ),
                ["station_code", "instant"],
            )
    finally:
        client.close()
    return total
