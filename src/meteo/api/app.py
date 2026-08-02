"""API de lecture et front minimal.

L'API ne calcule rien : elle lit des Verdicts déjà matérialisés par le lot (ADR 0004).
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meteo.api import lecture
from meteo.collecte.climatologie import ATTRIBUTION as ATTRIBUTION_CLIMAT
from meteo.collecte.open_meteo import (
    FUSEAU,
    altitude_du_point,
    previsions_courantes,
    qualite_air,
)
from meteo.domaine import conditions, cycle, indicateurs, neige, secheresse, tendance
from meteo.domaine.modeles import ANTICIPATION_MAX, CATALOGUE, PAR_CLE
from meteo.domaine.saison import Saison, saison_de
from meteo.domaine.temps import INCONNU, temps_de
from meteo.domaine.verdict import SEUIL_PLUIE_MM
from meteo.lots import rafraichissement
from meteo.lots.verdicts import PLUIE, TEMPERATURE

app = FastAPI(
    title="Fiabilité des modèles météo",
    description=(
        "Quel modèle de prévision croire, station par station. "
        "Observations issues du réseau StatIC d'Infoclimat, prévisions via Open-Meteo."
    ),
)

_WEB = Path(__file__).parent.parent / "web"
gabarits = Jinja2Templates(directory=str(_WEB / "templates"))
app.mount("/static", StaticFiles(directory=str(_WEB / "static")), name="static")

# Les quantièmes sont partout en base et nulle part lisibles : le filtre les rend
# en clair sans obliger chaque gabarit à refaire la conversion.
gabarits.env.filters["quantieme"] = lambda rang: _date_du_quantieme(rang)

VARIABLES = (TEMPERATURE, PLUIE)


def _saison(valeur: str | None) -> Saison:
    if valeur is None:
        return saison_de(date.today())
    try:
        return Saison(valeur)
    except ValueError:
        raise HTTPException(400, f"Saison inconnue : {valeur}") from None


def _variable(valeur: str) -> str:
    if valeur not in VARIABLES:
        raise HTTPException(400, f"Variable inconnue : {valeur}")
    return valeur


@app.get("/api/stations")
def stations() -> list[dict]:
    return [
        {
            "code": s.code,
            "nom": s.nom,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "altitude": s.altitude,
            "derniere_activite": s.derniere_activite,
        }
        for s in lecture.stations_suivies()
    ]


@app.get("/api/rattachement")
def rattachement(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    altitude: float | None = None,
) -> dict:
    """La Station de référence d'un lieu, ou le refus motivé de le rattacher."""
    altitude = altitude if altitude is not None else altitude_du_point(lat, lon)
    resultat = lecture.rattachement(lat, lon, altitude)
    return {
        "altitude_lieu": altitude,
        "rattache": resultat.rattache,
        "reference": _candidate(resultat.reference) if resultat.reference else None,
        "candidates": [_candidate(c) for c in resultat.candidates],
    }


def _candidate(c) -> dict:
    return {
        "code": c.code,
        "nom": c.nom,
        "altitude": c.altitude,
        "distance_km": round(c.distance_km, 1),
        "denivele_m": round(c.denivele_m),
        "cout_km": round(c.cout_km, 1),
    }


@app.get("/api/verdict")
def verdict(
    station: str,
    variable: str = TEMPERATURE,
    anticipation: int = Query(1, ge=1, le=ANTICIPATION_MAX),
    saison: str | None = None,
) -> dict:
    """Le Verdict d'une case. 404 si la case n'a pas été publiée."""
    case = lecture.case(station, _variable(variable), anticipation, _saison(saison))
    if case is None:
        raise HTTPException(
            404,
            "Aucun verdict publié pour cette case : couverture insuffisante "
            "ou données pas encore collectées.",
        )
    return {
        "station": {"code": case.station_code, "nom": case.station_nom},
        "variable": case.variable,
        "anticipation": case.anticipation,
        "saison": case.saison,
        "vainqueurs": list(case.vainqueurs),
        "modeles": [
            {
                "modele": ligne.nom_modele,
                "cle": ligne.modele,
                "rang": ligne.rang,
                "ecart_moyen": round(ligne.ecart_moyen, 3),
                "biais": round(ligne.biais, 3) if ligne.biais is not None else None,
                "fausses_alertes": (
                    round(ligne.fausses_alertes, 3)
                    if ligne.fausses_alertes is not None
                    else None
                ),
                "pluies_manquees": (
                    round(ligne.pluies_manquees, 3)
                    if ligne.pluies_manquees is not None
                    else None
                ),
                "ex_aequo": ligne.ex_aequo,
            }
            for ligne in case.lignes
        ],
        "nb_heures": case.nb_heures,
        "nb_jours": case.nb_jours,
        "couverture": round(case.couverture, 3),
        "calcule_le": case.calcule_le,
    }


def _serialiser(v: lecture.Verification | None, seuil: float = SEUIL_PLUIE_MM) -> dict:
    """Les Prévisions sortent en liste, pas en objet.

    L'ordre porte du sens — celui du catalogue, du Modèle le plus fin au plus
    grossier — et c'est lui qui attribue sa couleur à chaque Modèle. Un objet JSON
    ne garantit pas cet ordre : le filtre `tojson` de Jinja2 trie ses clés, ce qui
    dissocierait les couleurs du graphe de celles du tableau.
    """
    if v is None:
        return {
            "instants": [],
            "observations": [],
            "previsions": [],
            "variable": TEMPERATURE,
            "seuil_pluie_mm": seuil,
        }
    return {
        "instants": [i.isoformat() for i in v.instants],
        "observations": list(v.observations),
        "previsions": [
            {"nom": nom, "valeurs": list(serie)} for nom, serie in v.previsions.items()
        ],
        "variable": v.variable,
        "seuil_pluie_mm": seuil,
    }


@app.get("/api/verification")
def api_verification(
    station: str,
    anticipation: int = Query(1, ge=1, le=ANTICIPATION_MAX),
    jours: int = Query(14, ge=1, le=90),
    saison: str | None = None,
    variable: str = TEMPERATURE,
) -> dict:
    restriction = _saison(saison) if saison else None
    return _serialiser(
        lecture.verification(station, anticipation, jours, restriction, _variable(variable))
    )


def _point(
    stations: list, station_choisie: str | None, lat: float | None, lon: float | None
) -> tuple[float, float, float] | None:
    """Où l'on se tient : latitude, longitude, altitude. Une position prime sur une Station."""
    if lat is not None and lon is not None:
        return lat, lon, altitude_du_point(lat, lon)
    station = next((s for s in stations if s.code == station_choisie), None)
    if station is None:
        return None
    return station.latitude, station.longitude, station.altitude


def _cartes(
    stations: list,
    station_choisie: str | None,
    lat: float | None,
    lon: float | None,
    case: lecture.CaseVerdict | None,
) -> list[dict]:
    """Ce que chaque Modèle annonce en ce moment, au point de l'utilisateur.

    C'est la météo proprement dite, en tête de page. Le Verdict ne dit pas le temps
    qu'il fera : il désigne celui de ces Modèles qu'il vaut mieux croire ici.

    Les Modèles conseillés passent en premier, mais chacun garde sa couleur : un
    changement de saison ou d'anticipation réordonne les cartes sans les repeindre.
    """
    point = _point(stations, station_choisie, lat, lon)
    if point is None:
        return []
    latitude, longitude, altitude = point

    try:
        courantes = previsions_courantes(latitude, longitude, altitude, CATALOGUE)
    except (httpx.HTTPError, RuntimeError):
        # Une météo indisponible ne doit pas emporter le reste de la page.
        return []

    conseilles = set(case.vainqueurs) if case else set()
    rang_catalogue = {m.cle: i for i, m in enumerate(CATALOGUE)}

    cartes = [_carte(c, rang_catalogue, conseilles) for c in courantes if c.modele in PAR_CLE]
    cartes.sort(key=lambda c: (not c["conseille"], rang_catalogue[c["cle"]]))
    return cartes


JOURS_HORAIRES = 3
"""Nombre de journées détaillées heure par heure. Au-delà, la journée suffit : sept
bandes de vingt-quatre heures ne se lisent plus."""


def _carte(c, rang_catalogue: dict, conseilles: set) -> dict:
    aujourdhui = c.jours[0] if c.jours else None
    demain = c.jours[1] if len(c.jours) > 1 else None
    return {
        "cle": c.modele,
        "nom": PAR_CLE[c.modele].nom,
        "maille_km": PAR_CLE[c.modele].maille_km,
        "couleur": rang_catalogue[c.modele] + 1,
        "conseille": PAR_CLE[c.modele].nom in conseilles,
        "maintenant_c": c.maintenant_c,
        "aujourdhui_min_c": aujourdhui.min_c if aujourdhui else None,
        "aujourdhui_max_c": aujourdhui.max_c if aujourdhui else None,
        "aujourdhui_pluie_mm": aujourdhui.pluie_mm if aujourdhui else None,
        "demain_min_c": demain.min_c if demain else None,
        "demain_max_c": demain.max_c if demain else None,
        "demain_pluie_mm": demain.pluie_mm if demain else None,
        "temps": temps_de(c.maintenant_code, c.maintenant_jour),
        "jour": c.maintenant_jour,
        "vent": conditions.vent(c.vent_kmh, c.rafales_kmh, c.vent_degres),
        "uv": conditions.uv(c.uv),
        "uv_max": conditions.uv(c.uv_max),
        "ressenti": conditions.ressenti(c.ressenti_c, c.maintenant_c),
        "humidite": conditions.humidite(c.humidite_pct),
        "pression": conditions.pression(c.pression_hpa, c.pression_avant_hpa),
        "isotherme_m": c.isotherme_m,
        "lever": c.lever,
        "coucher": c.coucher,
        "lever_demain": c.lever_demain,
        "coucher_demain": c.coucher_demain,
        "annonce_le_temps": any(h.code_temps is not None for h in c.heures),
        "jours": _par_jour(c.heures, JOURS_HORAIRES),
        "semaine": _semaine(c.jours[JOURS_HORAIRES:]),
        # Jusqu'où va ce Modèle : de quoi le dire quand il s'arrête avant les autres.
        "derniere_echeance": _libelle_jour(c.jours[-1].jour) if c.jours else None,
    }


TEINTES_TEMPERATURE = {
    "glacial": "froid",
    "froid": "glace",
    "doux": "neutre",
    "chaud": "chaud",
    "torride": "risque-4",
}
"""L'échelle thermique réutilise les teintes déjà posées plutôt que d'en inventer :
moins il y a de couleurs sur la page, plus chacune veut dire quelque chose."""

TEINTES_VENT = {
    1: "souffle",
    2: "souffle",
    3: "souffle",
    4: "risque-3",
    5: "risque-4",
    6: "risque-5",
}
"""Le vent garde sa turquoise tant qu'il reste tenable ; au-delà de « soutenu » il
bascule sur l'échelle de risque, comme l'indice UV et la qualité de l'air."""

ECART_NEGLIGEABLE_C = 0.5
"""En deçà, la journée est dans la moyenne : annoncer « +0,2 °C au-dessus » donnerait
à un demi-degré une signification qu'il n'a pas."""


def _conditions(cartes: list[dict], station_code: str | None, point) -> dict | None:
    """Ce qui décrit la journée sans juger personne.

    Aucune comparaison de Modèles ici : chaque valeur vient du Modèle qui porte déjà
    la bande de ciel, et pour celles qu'il n'annonce pas — la pression chez AROME,
    l'isotherme et l'indice UV chez plusieurs — du premier qui les annonce. Chaque
    emprunt est nommé sous le bloc. Rien n'est anonyme, même quand rien n'est jugé.
    """
    if not cartes:
        return None

    tete = cartes[0]
    emprunts: list[tuple[str, str]] = []

    def prendre(cle: str, etiquette: str):
        """La valeur du Modèle de tête, ou du premier qui l'annonce — en le nommant."""
        porteur = next((c for c in cartes if c[cle] is not None), None)
        if porteur is None:
            return None
        if porteur is not tete:
            emprunts.append((etiquette, porteur["nom"]))
        return porteur[cle]

    altitude_lieu = point[2] if point else None
    latitude, longitude = (point[0], point[1]) if point else (None, None)

    moyenne = lecture.normale(station_code, date.today()) if station_code else None
    ecart = None
    if moyenne is not None and tete["aujourdhui_max_c"] is not None:
        ecart = tete["aujourdhui_max_c"] - moyenne.max_c

    air = None
    if latitude is not None:
        brut = qualite_air(latitude, longitude)
        if brut is not None:
            air = conditions.qualite_air(brut.indice, brut.sous_indices)

    bloc = {
        "modele": tete["nom"],
        "vent": tete["vent"],
        "ressenti": tete["ressenti"],
        "humidite": tete["humidite"],
        "pression": prendre("pression", "la pression"),
        "uv": prendre("uv", "l'indice UV"),
        "uv_max": tete["uv_max"] or next((c["uv_max"] for c in cartes if c["uv_max"]), None),
        "isotherme": conditions.isotherme(
            prendre("isotherme_m", "l'isotherme 0 °C"), altitude_lieu
        ),
        "soleil": _soleil(tete),
        "air": air,
        "normale": moyenne,
        "ecart_c": ecart,
        "max_prevu_c": tete["aujourdhui_max_c"],
        "dans_la_moyenne": ecart is not None and abs(ecart) < ECART_NEGLIGEABLE_C,
        "emprunts": emprunts,
    }
    # Chaque mesure porte sa teinte : c'est elle qui dit l'état, pas la place dans
    # la grille. Les échelles de risque sont partagées entre l'UV, l'air et le vent
    # fort — un seul barème de gravité pour toute la page.
    # Le ressenti se teinte de la température elle-même, pas de son écart au
    # thermomètre : ce qu'on lit dans cette cellule, c'est « il fait 26° », et un
    # écart d'un demi-degré ne mérite pas de peindre la case en gris.
    bloc["teinte_ressenti"] = TEINTES_TEMPERATURE.get(
        conditions.ton_temperature(bloc["ressenti"].valeur_c if bloc["ressenti"] else None),
        "neutre",
    )
    bloc["teinte_ecart"] = conditions.ton_thermique(ecart, ECART_NEGLIGEABLE_C)
    bloc["teinte_vent"] = TEINTES_VENT[bloc["vent"].cran] if bloc["vent"] else "souffle"
    mesures = ("vent", "ressenti", "humidite", "pression", "uv", "isotherme", "soleil", "air")
    if not any(bloc[c] for c in mesures) and ecart is None:
        return None
    return bloc


def _soleil(carte: dict) -> dict | None:
    """Lever, coucher, durée du jour — et de combien elle change demain.

    C'est la variation qui se remarque : au solstice elle tombe à quelques secondes,
    aux équinoxes elle dépasse trois minutes par jour.
    """
    if not carte["lever"] or not carte["coucher"]:
        return None

    duree = carte["coucher"] - carte["lever"]
    variation = None
    if carte["lever_demain"] and carte["coucher_demain"]:
        demain = carte["coucher_demain"] - carte["lever_demain"]
        variation = round((demain - duree).total_seconds() / 60)

    return {
        "lever": carte["lever"],
        "coucher": carte["coucher"],
        "heures": int(duree.total_seconds() // 3600),
        "minutes": int(duree.total_seconds() % 3600 // 60),
        "variation_min": variation,
    }


def _semaine(jours) -> list[dict]:
    """Les journées qui suivent le détail horaire, avec leur barre d'amplitude.

    La barre est cadrée sur l'amplitude de ces journées-là, propre à ce Modèle : elle
    dit quel jour est plus doux que les autres, jamais comment ce Modèle se situe
    face à ses concurrents — cette comparaison-là appartient au rail et au verdict.
    """
    mesures = [j for j in jours if j.min_c is not None and j.max_c is not None]
    if not mesures:
        return []

    bas = min(j.min_c for j in mesures)
    haut = max(j.max_c for j in mesures)
    etendue = haut - bas

    sorties = []
    for j in mesures:
        depart = 0.0 if etendue == 0 else 100.0 * (j.min_c - bas) / etendue
        largeur = 100.0 if etendue == 0 else 100.0 * (j.max_c - j.min_c) / etendue
        sorties.append(
            {
                "libelle": _libelle_jour(j.jour),
                "temps": temps_de(j.code_temps),
                "min_c": j.min_c,
                "max_c": j.max_c,
                "pluie_mm": j.pluie_mm,
                "depart": depart,
                # Une journée sans écart doit rester visible : la barre garde un corps.
                "largeur": max(largeur, 3.0),
            }
        )
    return sorties


def _ciel(cartes: list[dict]) -> dict | None:
    """Ce qui ouvre la page : une température, un Temps, et qui les annonce.

    Rien n'est anonyme. La température vient du premier Modèle de la liste — le
    Modèle conseillé quand un Verdict en désigne un, sinon le plus fin du catalogue.
    Le Temps vient du même Modèle s'il en annonce un ; sinon du premier qui en
    annonce, et l'attribution le dit. AROME, qui ne publie jamais de code de temps,
    rendrait autrement un ciel vide alors qu'il est souvent le mieux placé ici.
    """
    if not cartes:
        return None

    tete = cartes[0]
    porteur = next(
        (c for c in cartes if c["temps"].famille != INCONNU),
        None,
    )
    temps = porteur["temps"] if porteur else tete["temps"]

    return {
        "temperature_c": tete["maintenant_c"],
        "modele": tete["nom"],
        "conseille": tete["conseille"],
        "temps": temps,
        "nuit": not tete["jour"],
        # Nommé seulement quand le Temps ne vient pas du Modèle qui donne la température.
        "temps_modele": porteur["nom"] if porteur and porteur is not tete else None,
        "min_c": tete["aujourdhui_min_c"],
        "max_c": tete["aujourdhui_max_c"],
        "pluie_mm": tete["aujourdhui_pluie_mm"],
    }


ECART_PASTILLES = 2.5
"""Écart minimal, en pourcentage du rail, sous lequel deux pastilles se recouvrent."""


def _desaccord(cartes: list[dict]) -> dict | None:
    """L'écart entre ce qu'annoncent les Modèles à l'instant présent.

    C'est la raison d'être du projet, rendue visible en une ligne : six Modèles, six
    températures, un intervalle. Chaque Modèle garde la teinte qui lui est attachée
    (ADR 0006) — la position sur le rail dit la valeur, la teinte dit qui parle.
    """
    valeurs = [c for c in cartes if c["maintenant_c"] is not None]
    if len(valeurs) < 2:
        return None

    bas = min(c["maintenant_c"] for c in valeurs)
    haut = max(c["maintenant_c"] for c in valeurs)
    etendue = haut - bas

    def position(t: float) -> float:
        """En pourcentage de la piste, 6 % de marge pour que les bords tiennent."""
        return 50.0 if etendue == 0 else 6.0 + 88.0 * (t - bas) / etendue

    # Deux Modèles d'accord donneraient deux pastilles superposées, dont l'une
    # invisible. On les empile alors en rangées : l'accord doit se voir, pas se
    # traduire par un Modèle escamoté.
    occupees: list[float] = []
    points = []
    for c in sorted(valeurs, key=lambda c: c["maintenant_c"]):
        x = position(c["maintenant_c"])
        rangee = 0
        while rangee < len(occupees) and x - occupees[rangee] < ECART_PASTILLES:
            rangee += 1
        if rangee == len(occupees):
            occupees.append(x)
        else:
            occupees[rangee] = x
        points.append(
            {
                "nom": c["nom"],
                "couleur": c["couleur"],
                "temperature_c": c["maintenant_c"],
                "conseille": c["conseille"],
                "position": x,
                "rangee": rangee,
            }
        )

    return {
        "min_c": bas,
        "max_c": haut,
        "amplitude_c": etendue,
        "points": points,
        "rangees": len(occupees),
    }


_NOMS_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

_NOMS_MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _date_du_quantieme(rang: int) -> str:
    """« 102 » devient « 12 avril ».

    Calé sur une année non bissextile, comme l'axe des cycles : un quantième ne désigne
    une date que si l'on dit laquelle des deux années on prend pour référence.
    """
    return _libelle_date_annuelle(date(2001, 1, 1) + timedelta(days=rang - 1))


def _libelle_date_annuelle(jour: date) -> str:
    """« 2 août » : la date sans son année, puisque c'est la date qui est le sujet.

    Distinct de _libelle_jour, qui situe une journée par rapport à aujourd'hui. Ici
    l'année n'a pas de sens — c'est justement toutes les années qu'on regarde.
    """
    quantieme = "1er" if jour.day == 1 else str(jour.day)
    return f"{quantieme} {_NOMS_MOIS[jour.month - 1]}"


def _libelle_jour(jour: date) -> str:
    """Le nom d'une journée, relatif tant qu'il porte : aujourd'hui, demain, puis le jour."""
    ecart = (jour - datetime.now(ZoneInfo(FUSEAU)).date()).days
    if ecart == 0:
        return "Aujourd'hui"
    if ecart == 1:
        return "Demain"
    return f"{_NOMS_JOURS[jour.weekday()].capitalize()} {jour.day:02d}"


def _par_jour(heures, limite: int) -> list[dict]:
    """Regroupe le détail horaire par journée, pour un affichage en bandes."""
    groupes: dict[date, list] = {}
    for h in heures:
        groupes.setdefault(h.instant.date(), []).append(h)

    sorties = []
    for jour, liste in sorted(groupes.items())[:limite]:
        sorties.append(
            {
                "libelle": _libelle_jour(jour),
                "heures": [
                    {
                        "heure": h.instant.hour,
                        "temperature_c": h.temperature_c,
                        "pluie_mm": h.pluie_mm,
                        "temps": temps_de(h.code_temps, h.jour),
                        "jour": h.jour,
                    }
                    for h in liste
                ],
            }
        )
    return sorties


@app.post("/api/rafraichir", status_code=202)
def rafraichir() -> dict:
    """Déclenche une collecte des derniers jours puis le recalcul des Verdicts.

    Répond immédiatement : le travail se poursuit en tâche de fond, à suivre sur
    /api/rafraichissement.
    """
    try:
        return rafraichissement.lancer()
    except rafraichissement.DejaEnCours as exc:
        raise HTTPException(409, str(exc)) from None
    except rafraichissement.TropTot as exc:
        raise HTTPException(429, str(exc)) from None


@app.get("/api/rafraichissement")
def etat_rafraichissement() -> dict:
    return rafraichissement.etat()


ANTICIPATION_CONSEIL = 1
"""L'Anticipation qui désigne le Modèle mis en avant sur la page de prévision.

La question qu'on se pose en regardant la météo est « à qui me fier pour demain » :
c'est l'échéance d'un jour, sur la température, dans la saison en cours. Les autres
combinaisons se règlent sur la page de fiabilité, à qui elles appartiennent.
"""


def _lieu(station: str | None, lat: float | None, lon: float | None):
    """Résout le lieu commun aux deux pages.

    Une position prime sur un choix manuel de Station : c'est la promesse « chez toi ».
    Rend aussi le fragment d'URL qui transporte ce lieu d'une page à l'autre — le menu
    ne doit pas ramener l'utilisateur à Engins parce qu'il a changé de rubrique.
    """
    toutes = lecture.stations_suivies()

    resultat = None
    if lat is not None and lon is not None:
        resultat = lecture.rattachement(lat, lon, altitude_du_point(lat, lon))
        choisie = resultat.reference.code if resultat.reference else None
        lien = "?" + urlencode({"lat": lat, "lon": lon})
    else:
        choisie = station or (toutes[0].code if toutes else None)
        lien = "?" + urlencode({"station": choisie}) if choisie else ""

    return toutes, choisie, resultat, lien


def _menu(page: str, action: str, lieu, position, reglages: dict) -> dict:
    """Le contexte du menu latéral, identique sur toutes les pages."""
    toutes, choisie, resultat, lien = lieu
    return {
        "page": page,
        "action": action,
        "stations": toutes,
        "station_choisie": choisie,
        "rattachement": resultat,
        "position": position,
        "lien_lieu": lien,
        # Le formulaire de station reporte les réglages de la page, sans quoi changer
        # de station renverrait le verdict à ses valeurs par défaut.
        "champs_caches": list(reglages.items()),
        "suite_params": "".join(f"&{c}={v}" for c, v in reglages.items()),
        # Affiché en heure locale : le reste de la page l'est, la fraîcheur aussi.
        "dernier_lot": _en_heure_locale(lecture.dernier_rafraichissement()),
    }


def _en_heure_locale(instant: datetime | None) -> datetime | None:
    return instant.astimezone(ZoneInfo(FUSEAU)) if instant else None


@app.get("/", response_class=HTMLResponse)
def previsions(
    request: Request,
    station: str | None = None,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
) -> HTMLResponse:
    """La météo elle-même : ce que chaque Modèle annonce pour ce lieu, maintenant."""
    lieu = _lieu(station, lat, lon)
    toutes, choisie, _, _ = lieu
    saison_courante = saison_de(date.today())

    case = (
        lecture.case(choisie, TEMPERATURE, ANTICIPATION_CONSEIL, saison_courante)
        if choisie
        else None
    )
    cartes = _cartes(toutes, choisie, lat, lon, case)
    point = _point(toutes, choisie, lat, lon)
    position = (lat, lon) if lat is not None and lon is not None else None

    return gabarits.TemplateResponse(
        request=request,
        name="previsions.html",
        context={
            **_menu("previsions", "/", lieu, position, {}),
            "station_nom": next((s.nom for s in toutes if s.code == choisie), None),
            "station_altitude": next((s.altitude for s in toutes if s.code == choisie), None),
            "case": case,
            "anticipation": ANTICIPATION_CONSEIL,
            "saison": saison_courante,
            "cartes": cartes,
            "ciel": _ciel(cartes),
            "desaccord": _desaccord(cartes),
            "conditions": _conditions(cartes, choisie, point),
            "crans_uv": conditions.CRANS_UV,
            "crans_air": conditions.CRANS_AIR,
            "crans_vent": conditions.CRANS_VENT,
            "crans_humidite": conditions.CRANS_HUMIDITE,
        },
    )


@app.get("/fiabilite", response_class=HTMLResponse)
def fiabilite(
    request: Request,
    station: str | None = None,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    variable: str = TEMPERATURE,
    anticipation: int = Query(1, ge=1, le=ANTICIPATION_MAX),
    saison: str | None = None,
    jours: int = Query(14, ge=1, le=90),
) -> HTMLResponse:
    """Le jugement : quel Modèle se trompe le moins ici, et sur quelles mesures."""
    lieu = _lieu(station, lat, lon)
    _, choisie, _, _ = lieu
    variable = _variable(variable)
    saison_choisie = _saison(saison)

    case = lecture.case(choisie, variable, anticipation, saison_choisie) if choisie else None
    # Le graphe est restreint à la saison et à la variable du verdict : il doit le justifier.
    v = (
        lecture.verification(choisie, anticipation, jours, saison_choisie, variable)
        if choisie
        else None
    )
    # Quand il n'y a pas de verdict, on explique ce qui manque plutôt que de se taire.
    raison = lecture.manque(choisie, variable, saison_choisie) if choisie and not case else None
    position = (lat, lon) if lat is not None and lon is not None else None
    reglages = {
        "variable": variable,
        "anticipation": anticipation,
        "saison": saison_choisie.value,
        "jours": jours,
    }

    return gabarits.TemplateResponse(
        request=request,
        name="fiabilite.html",
        context={
            **_menu("fiabilite", "/fiabilite", lieu, position, reglages),
            "variable": variable,
            "variables": VARIABLES,
            "anticipation": anticipation,
            "anticipations": range(1, ANTICIPATION_MAX + 1),
            "saison": saison_choisie,
            "saisons": list(Saison),
            "saisons_disponibles": (
                lecture.saisons_publiees(choisie, variable) if choisie else set()
            ),
            "jours": jours,
            "case": case,
            "manque": raison,
            "verification": v,
            "donnees": _serialiser(v),
            # Le rang du Modèle dans le catalogue, qui lui attribue sa teinte (ADR 0006).
            "teintes": {m.cle: i + 1 for i, m in enumerate(CATALOGUE)},
        },
    )


def _jour_demande(brut: str | None) -> date:
    """La date dont on veut l'histoire. Seuls le mois et le quantième comptent.

    L'année transportée par le formulaire est ignorée : la question est « le 2 août »,
    pas « le 2 août 2026 ». On la conserve néanmoins dans la valeur du champ, sans quoi
    un `input type="date"` refuserait de s'afficher.
    """
    if brut:
        try:
            return date.fromisoformat(brut)
        except ValueError:
            pass
    return date.today()


def _serie_tendance(t, debut: int, fin: int, decimales: int = 2) -> dict | None:
    """La droite et sa bande d'incertitude, année par année, prêtes à tracer.

    Calculées ici et non dans le navigateur : la formule de l'incertitude est le cœur
    de ce que la page affirme, elle n'a rien à faire dans une feuille de script où
    personne ne viendra la relire.
    """
    if t is None:
        return None
    return {
        # Deux décimales, la même précision que le gabarit : arrondir ici à trois puis
        # laisser le navigateur réarrondir à deux ferait afficher +0,31 dans la phrase
        # et +0,32 dans la légende, pour la même pente.
        "pente_par_decennie": round(t.pente_par_decennie, decimales),
        "incertitude_par_decennie": round(t.incertitude_par_decennie, decimales),
        "r2": round(t.r2, 3),
        "significative": t.significative,
        "nb_annees": t.nb_annees,
        "premiere_annee": t.premiere_annee,
        "derniere_annee": t.derniere_annee,
        "evolution_totale": round(t.evolution_totale, decimales),
        "courbe": [
            {
                "annee": annee,
                "valeur": round(t.valeur(annee), 2),
                "bas": round(t.valeur(annee) - t.incertitude(annee), 2),
                "haut": round(t.valeur(annee) + t.incertitude(annee), 2),
            }
            for annee in range(debut, fin + 1)
        ],
    }


def _serie_neige(n) -> dict | None:
    """L'enneigement saison après saison, avec ses deux tendances.

    Deux grandeurs d'unités différentes : le graphe les met sur deux panneaux empilés
    plutôt que sur un axe partagé, qui serait une comparaison truquée.
    """
    if n is None or not n.saisons:
        return None
    debut, fin = n.saisons[0].saison, n.saisons[-1].saison
    return {
        "saisons": [
            {
                "saison": s.saison,
                "libelle": s.libelle,
                "jours": s.jours_au_sol,
                "epaisseur": round(s.epaisseur_max_cm),
                "premiere": s.premiere.isoformat() if s.premiere else None,
                "derniere": s.derniere.isoformat() if s.derniere else None,
            }
            for s in n.saisons
        ],
        "tendances": {
            "jours": _serie_tendance(n.tendance_jours, debut, fin, decimales=1),
            "epaisseur": _serie_tendance(n.tendance_epaisseur, debut, fin, decimales=1),
        },
    }


def _serie_secheresse(s) -> dict | None:
    """Le bilan hydrique estival et l'état standardisé de chaque saison."""
    if s is None or not s.bilans:
        return None
    debut, fin = s.bilans[0].annee, s.bilans[-1].annee
    return {
        "source": s.source,
        "saisons": [
            {
                "annee": b.annee,
                "apport": round(b.apport_mm),
                "demande": round(b.demande_mm),
                "bilan": round(b.bilan_mm),
            }
            for b in s.bilans
        ],
        "etats": [
            {
                "annee": e.annee,
                "indice": round(e.indice, 2),
                "classe": e.classe,
                "libelle": e.libelle,
                "bilan": round(e.bilan_mm),
                "sec": e.sec,
            }
            for e in s.etats
        ],
        "tendances": {
            "apport": _serie_tendance(s.tendance_apport, debut, fin, decimales=1),
            "demande": _serie_tendance(s.tendance_demande, debut, fin, decimales=1),
            "bilan": _serie_tendance(s.tendance_bilan, debut, fin, decimales=1),
        },
        "seuil_sec": secheresse.SEUIL_SEC,
        "mois": list(secheresse.MOIS_SAISON),
    }


def _serie_franchissements(series) -> dict | None:
    """Les décomptes annuels des trois seuils, sur un axe commun.

    La droite s'arrête à la dernière année mesurée, sans prolongement. Prolonger un
    comptage n'aurait pas de sens : une droite descendante finirait par annoncer un
    nombre de jours de gel négatif, ce qui n'existe pas.
    """
    seuils = []
    for s in series:
        if not s.annees:
            continue
        seuils.append(
            {
                "cle": s.seuil.cle,
                "nom": s.seuil.nom,
                "definition": s.seuil.definition,
                "points": [{"annee": a.annee, "jours": a.jours} for a in s.annees],
                "tendance": _serie_tendance(
                    s.tendance, s.annees[0].annee, s.annees[-1].annee, decimales=1
                ),
            }
        )
    return {"seuils": seuils} if seuils else None


def _serie_gel(gel) -> dict | None:
    """Les saisons sans gel, bornées par leurs deux dates."""
    if not gel.saisons:
        return None
    return {
        "saisons": [
            {
                "annee": s.annee,
                "dernier_gel": s.dernier_gel,
                "premier_gel": s.premier_gel,
                "duree": s.duree,
            }
            for s in gel.saisons
        ],
        "debuts_de_mois": list(cycle.DEBUTS_DE_MOIS),
        "jours_an": cycle.JOURS_AN,
        "tendance": _serie_tendance(
            gel.tendance, gel.saisons[0].annee, gel.saisons[-1].annee, decimales=1
        ),
    }


def _serie_records(records) -> dict | None:
    """Les parts de records par décennie, chaud et froid appariés.

    Les deux séries partagent l'axe : c'est leur divergence qui porte le message, et la
    lire demande de les voir côte à côte plutôt que sur deux graphiques.
    """
    if not records.chaleur and not records.froid:
        return None
    par_decennie = {p.decennie: {"chaleur": p} for p in records.chaleur}
    for p in records.froid:
        par_decennie.setdefault(p.decennie, {})["froid"] = p

    def part(p):
        if p is None:
            return None
        return {
            "records": p.records,
            "attendus": round(p.attendus, 1),
            "indice": round(p.indice, 2),
            "bruit": round(p.bruit, 2),
            "remarquable": p.remarquable,
        }

    return {
        "decennies": [
            {
                "decennie": d,
                "annees": max(
                    (v.annees for v in par_decennie[d].values()), default=0
                ),
                "chaleur": part(par_decennie[d].get("chaleur")),
                "froid": part(par_decennie[d].get("froid")),
            }
            for d in sorted(par_decennie)
        ],
        "dernier_chaud": records.dernier_chaud,
        "dernier_froid": records.dernier_froid,
    }


def _serie_climat(serie: lecture.SerieJour) -> dict:
    """La Série longue d'un jour, sérialisée pour le graphique."""
    fin = tendance.HORIZON_PROJECTION
    mesurees = [a.annee for a in serie.maxima] + [a.annee for a in serie.minima]
    debut = min(mesurees) if mesurees else serie.poste.premiere_annee

    def points(agregees):
        return [
            {"annee": a.annee, "valeur": round(a.valeur, 2), "jours": a.nb_jours}
            for a in agregees
        ]

    return {
        "derniere_annee_mesuree": max(mesurees) if mesurees else None,
        "horizon": fin,
        "series": [
            {
                "cle": "maxi",
                "nom": "Maximales",
                "points": points(serie.maxima),
                "tendance": _serie_tendance(serie.tendance_max, debut, fin),
            },
            {
                "cle": "mini",
                "nom": "Minimales",
                "points": points(serie.minima),
                "tendance": _serie_tendance(serie.tendance_min, debut, fin),
            },
        ],
    }


def _serie_cycle(sc: lecture.SerieCycle, jour: date) -> dict | None:
    """Toutes les années d'un Poste, prêtes à superposer.

    Les courbes de fond partent aussi : c'est leur épaisseur collective qui donne son
    sens aux décennies mises en avant. Après lissage et sous-échantillonnage, un Poste
    centenaire tient dans quelques dizaines de milliers de nombres.
    """
    if not sc.annees:
        return None
    return {
        "annees": [
            {
                "annee": a.annee,
                "quantiemes": list(a.quantiemes),
                "valeurs": [round(v, 1) for v in a.valeurs_c],
                "complete": a.complete,
            }
            for a in sc.annees
        ],
        "decennies": list(sc.decennies),
        "debuts_de_mois": list(cycle.DEBUTS_DE_MOIS),
        "jours_an": cycle.JOURS_AN,
        "pas_j": cycle.PAS_TRACE_J,
        # Reporté du premier graphe : les deux parlent du même moment.
        "quantieme_choisi": cycle.quantieme(jour),
    }


def _mensuelles(sc: lecture.SerieCycle) -> list[dict]:
    """Les moyennes mensuelles des décennies mises en avant, pour le tableau."""
    par_annee = {a.annee: a for a in sc.annees}
    return [
        {"annee": annee, "valeurs": cycle.moyennes_mensuelles(par_annee[annee])}
        for annee in sc.decennies
        if annee in par_annee
    ]


@app.get("/api/climat")
def api_climat(poste: str, jour: str | None = None) -> dict:
    """La Série longue d'un Poste sur un jour de l'année."""
    cible = _jour_demande(jour)
    serie = lecture.serie_jour(poste, cible.month, cible.day)
    if serie is None:
        raise HTTPException(status_code=404, detail="Poste inconnu.")
    return _serie_climat(serie)


@app.get("/climat", response_class=HTMLResponse)
def climat(
    request: Request,
    station: str | None = None,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    poste: str | None = None,
    jour: str | None = None,
) -> HTMLResponse:
    """La mémoire du lieu : ce qu'un jour de l'année pesait, année après année."""
    lieu = _lieu(station, lat, lon)
    toutes, choisie, _, _ = lieu
    point = _point(toutes, choisie, lat, lon)

    postes = lecture.postes_utilisables()
    rattache = lecture.rattachement_climatique(*point) if point else None
    # Un Poste choisi à la main l'emporte sur le rattachement, et se transporte d'une
    # date à l'autre. Sans choix explicite, changer de lieu doit changer de Poste.
    retenu = poste or (rattache.reference.code if rattache and rattache.reference else None)
    if retenu is None and postes:
        retenu = postes[0].numero

    cible = _jour_demande(jour)
    # Une seule lecture de la Série longue nourrit les cinq graphes de la page.
    dossier = lecture.dossier(retenu, cible.month, cible.day) if retenu else None
    serie = dossier.jour if dossier else None
    annuel = dossier.cycle if dossier else None
    reglages = {"jour": cible.isoformat()}
    if poste:
        reglages["poste"] = poste

    return gabarits.TemplateResponse(
        request=request,
        name="climat.html",
        context={
            **_menu("climat", "/climat", lieu, (lat, lon) if point and lat else None, reglages),
            "postes": postes,
            "poste_retenu": retenu,
            "rattachement_climat": rattache,
            "point": point,
            "jour": cible,
            "libelle_jour": _libelle_date_annuelle(cible),
            "serie": serie,
            "donnees": _serie_climat(serie) if serie else None,
            "cycle": annuel,
            "donnees_cycle": _serie_cycle(annuel, cible) if annuel else None,
            "mensuelles": _mensuelles(annuel) if annuel else [],
            "noms_mois": [m[:3] for m in _NOMS_MOIS],
            "lissage_j": cycle.DEMI_LISSAGE_J * 2 + 1,
            "franchissements": dossier.franchissements if dossier else (),
            "donnees_seuils": _serie_franchissements(dossier.franchissements)
            if dossier
            else None,
            "gel": dossier.gel if dossier else None,
            "donnees_gel": _serie_gel(dossier.gel) if dossier else None,
            "records": dossier.records if dossier else None,
            "donnees_records": _serie_records(dossier.records) if dossier else None,
            "neige": dossier.neige if dossier else None,
            "donnees_neige": _serie_neige(dossier.neige) if dossier else None,
            "mois_saison_neige": neige.MOIS_DEBUT_SAISON,
            "secheresse": dossier.secheresse if dossier else None,
            "donnees_secheresse": _serie_secheresse(dossier.secheresse) if dossier else None,
            "noms_mois_complets": list(_NOMS_MOIS),
            "ecarts_types_bruit": indicateurs.ECARTS_TYPES_BRUIT,
            "annees_minimum": tendance.ANNEES_MINIMUM,
            "annee_pleine_j": tendance.JOURS_ANNEE_PLEINE,
            "fenetre_j": tendance.FENETRE_J,
            "horizon": tendance.HORIZON_PROJECTION,
            "attribution": ATTRIBUTION_CLIMAT,
        },
    )
