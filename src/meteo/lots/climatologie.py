"""Chargement des Séries longues Météo-France.

Le fichier départemental porte l'identité de son Poste sur chaque ligne : on écrit les
deux tables dans la même traversée, sans second téléchargement. Les Postes doivent
précéder leurs Journées — c'est la clé étrangère qui l'impose, et c'est aussi l'ordre
qui a du sens : un jour ne se rattache pas à un lieu inconnu.

La couverture (`annees_pleines`) n'est pas déduite à la volée mais recalculée à la fin,
en base. C'est la seule mesure honnête : elle ne dépend ni de l'ordre des fichiers ni
du fait qu'on ait rechargé un département entier ou seulement sa dernière tranche.

Opération idempotente : recharger deux fois le même département ne crée pas de doublon
et ne perd rien.
"""

from collections.abc import Iterable, Iterator
from itertools import islice

from sqlalchemy import Integer, cast, extract, func, select, update
from sqlalchemy.dialects.postgresql import insert

from meteo.collecte.climatologie import ClientClimatologie, JourneeMesuree
from meteo.config import config
from meteo.domaine.tendance import JOURS_ANNEE_PLEINE
from meteo.stockage.session import session
from meteo.stockage.tables import Journee, Poste

TAILLE_LOT = 5000


def _par_paquets(source: Iterable, taille: int) -> Iterator[list]:
    it = iter(source)
    while paquet := list(islice(it, taille)):
        yield paquet


def _ligne_poste(j: JourneeMesuree) -> dict:
    return {
        "numero": j.poste_numero,
        "nom": j.nom,
        "latitude": j.latitude,
        "longitude": j.longitude,
        "altitude": j.altitude,
        # Remplacés par _recalculer_couverture une fois toutes les Journées écrites.
        "premiere_annee": 0,
        "derniere_annee": 0,
        "annees_pleines": 0,
    }


def _ligne_journee(j: JourneeMesuree) -> dict:
    return {
        "poste_numero": j.poste_numero,
        "jour": j.jour,
        "tn_c": j.tn_c,
        "tx_c": j.tx_c,
    }


def _charger_departement(client: ClientClimatologie, departement: str) -> tuple[int, int]:
    connus: set[str] = set()
    total = 0
    with session() as s:
        for paquet in _par_paquets(client.journees(departement), TAILLE_LOT):
            nouveaux = {j.poste_numero: j for j in paquet if j.poste_numero not in connus}
            if nouveaux:
                requete = insert(Poste)
                s.execute(
                    requete.on_conflict_do_update(
                        index_elements=["numero"],
                        # L'identité seule est rafraîchie : les statistiques de
                        # couverture appartiennent à _recalculer_couverture.
                        set_={
                            c: getattr(requete.excluded, c)
                            for c in ("nom", "latitude", "longitude", "altitude")
                        },
                    ),
                    [_ligne_poste(j) for j in nouveaux.values()],
                )
                connus.update(nouveaux)

            requete = insert(Journee)
            s.execute(
                requete.on_conflict_do_update(
                    index_elements=["poste_numero", "jour"],
                    set_={c: getattr(requete.excluded, c) for c in ("tn_c", "tx_c")},
                ),
                [_ligne_journee(j) for j in paquet],
            )
            s.commit()
            total += len(paquet)
    return total, len(connus)


def _recalculer_couverture() -> int:
    """Réécrit les statistiques de couverture de chaque Poste depuis les Journées."""
    annee = cast(extract("year", Journee.jour), Integer).label("annee")
    par_annee = (
        select(Journee.poste_numero, annee, func.count().label("jours"))
        .where(Journee.tx_c.is_not(None) | Journee.tn_c.is_not(None))
        .group_by(Journee.poste_numero, annee)
        .subquery()
    )
    par_poste = select(
        par_annee.c.poste_numero,
        func.min(par_annee.c.annee).label("premiere"),
        func.max(par_annee.c.annee).label("derniere"),
        func.count()
        .filter(par_annee.c.jours >= JOURS_ANNEE_PLEINE)
        .label("pleines"),
    ).group_by(par_annee.c.poste_numero)

    with session() as s:
        lignes = s.execute(par_poste).all()
        for ligne in lignes:
            s.execute(
                update(Poste)
                .where(Poste.numero == ligne.poste_numero)
                .values(
                    premiere_annee=ligne.premiere,
                    derniere_annee=ligne.derniere,
                    annees_pleines=ligne.pleines,
                )
            )
        s.commit()
    return len(lignes)


def charger(departements: list[str] | None = None) -> dict:
    """Charge les Séries longues des départements demandés.

    Sans argument, prend ceux de la configuration. Retourne de quoi écrire une ligne
    de journal : c'est un lot, il tourne sans témoin.
    """
    departements = departements or config().departements
    client = ClientClimatologie()
    try:
        journees = 0
        for departement in departements:
            n, _ = _charger_departement(client, departement)
            journees += n
    finally:
        client.close()

    return {
        "departements": departements,
        "journees": journees,
        "postes": _recalculer_couverture(),
    }
