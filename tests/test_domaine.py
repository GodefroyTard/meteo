from datetime import date, timedelta

import numpy as np
import pytest

from meteo.domaine import cycle, indicateurs, neige, qualite, secheresse, tendance
from meteo.domaine.conditions import (
    CRANS_AIR,
    CRANS_UV,
    humidite,
    isotherme,
    pression,
    provenance,
    qualite_air,
    ressenti,
    ton_temperature,
    uv,
    vent,
)
from meteo.domaine.modeles import (
    CATALOGUE,
    debut_fenetre_recente,
    etablis,
    modeles_couvrant,
    nouveaux,
)
from meteo.domaine.rattachement import COUT_MAXIMAL_KM, distance_km, rattacher
from meteo.domaine.saison import Saison, saison_de
from meteo.domaine.temps import NON_ANNONCE, pleut, temps_de
from meteo.domaine.verdict import comparer_pluie, comparer_temperature, il_a_plu

# --- Stations réelles du périmètre grenoblois, pour ancrer les tests dans le terrain.
SAINT_MARTIN = ("00014", "Saint-Martin-d'Hères", 45.1667, 5.7667, 220.0)
MOUCHEROLLE = ("STATIC0479", "Crête de la Moucherolle", 45.0093, 5.55754, 1965.0)
LANS_BRUYERES = ("000T0", "Lans-en-Vercors - Les Bruyères", 45.128, 5.590, 990.0)
ENGINS = ("000HT", "Engins", 45.17957, 5.6172, 905.0)
TOUTES = [SAINT_MARTIN, MOUCHEROLLE, LANS_BRUYERES, ENGINS]


class TestSaison:
    def test_hiver_court_de_decembre_a_fevrier(self):
        assert saison_de(date(2025, 12, 15)) is Saison.HIVER
        assert saison_de(date(2025, 1, 31)) is Saison.HIVER
        assert saison_de(date(2025, 2, 28)) is Saison.HIVER

    def test_mars_est_deja_le_printemps(self):
        assert saison_de(date(2025, 3, 1)) is Saison.PRINTEMPS


class TestPortee:
    def test_le_peloton_se_reduit_avec_l_anticipation(self):
        assert len(modeles_couvrant(1)) == len(CATALOGUE)
        assert {m.nom for m in modeles_couvrant(7)} == {"ECMWF", "GFS", "AIFS"}

    def test_arome_ne_court_pas_au_dela_d_un_jour(self):
        arome = next(m for m in CATALOGUE if m.nom == "AROME")
        assert arome.couvre(1)
        assert not arome.couvre(2)


class TestPeloton:
    def test_les_etablis_n_ont_pas_de_date_d_archive(self):
        assert all(m.debut_archive is None for m in etablis())
        assert {m.nom for m in etablis()} | {m.nom for m in nouveaux()} == {
            m.nom for m in CATALOGUE
        }

    def test_aifs_est_un_nouveau_venu(self):
        # Ses runs passés ne sont archivés que depuis mars 2025 : le verser dans le
        # peloton principal tronquerait l'historique de tous les autres.
        (aifs,) = nouveaux()
        assert aifs.nom == "AIFS"
        assert aifs.debut_archive == date(2025, 3, 1)

    def test_la_fenetre_recente_part_du_plus_jeune(self):
        assert debut_fenetre_recente() == max(m.debut_archive for m in nouveaux())

    def test_sans_nouveau_venu_il_n_y_a_pas_de_seconde_fenetre(self):
        # Le second classement n'existe que s'il y a quelqu'un à y comparer.
        assert (debut_fenetre_recente() is None) == (len(nouveaux()) == 0)


class TestRattachement:
    def test_grenoble_centre_va_au_fond_de_vallee(self):
        r = rattacher(TOUTES, latitude=45.1885, longitude=5.7245, altitude=212.0)
        assert r.rattache
        assert r.reference.nom == "Saint-Martin-d'Hères"

    def test_l_altitude_prime_sur_la_distance_a_villard(self):
        """Villard-de-Lans est à 1050 m : la station de crête est plus proche à vol
        d'oiseau, mais 1000 m de dénivelé la disqualifient."""
        r = rattacher(TOUTES, latitude=45.0703, longitude=5.5514, altitude=1050.0)
        assert r.reference.nom == "Lans-en-Vercors - Les Bruyères"

    def test_chamrousse_n_est_rattache_a_rien(self):
        """1750 m, autre massif : aucune station comparable, on refuse."""
        r = rattacher(TOUTES, latitude=45.1219, longitude=5.8783, altitude=1750.0)
        assert not r.rattache
        assert r.reference is None
        assert len(r.candidates) == 3, "les candidates restent listées pour motiver le refus"
        assert all(c.cout_km > COUT_MAXIMAL_KM for c in r.candidates[:1])

    def test_distance_grenoble_moucherolle(self):
        d = distance_km(45.1885, 5.7245, 45.0093, 5.55754)
        assert 23 < d < 25


class TestQualite:
    def _mesures(self, temperatures):
        return [qualite.MesureBrute(t, 0.0) for t in temperatures]

    def test_capteur_fige_est_ecarte(self):
        valides = qualite.valider(self._mesures([12.3] * 10))
        assert not any(valides)

    def test_une_courte_stagnation_reste_acceptable(self):
        valides = qualite.valider(self._mesures([12.3] * 4 + [12.9]))
        assert all(valides)

    def test_valeur_hors_bornes_physiques(self):
        valides = qualite.valider(self._mesures([15.0, 120.0, 15.5]))
        assert valides == [True, False, True]

    def test_saut_horaire_impossible_ecarte_les_deux_mesures(self):
        valides = qualite.valider(self._mesures([10.0, 11.0, 40.0, 41.0]))
        assert valides[1] is False and valides[2] is False

    def test_refus_de_publier_sous_le_seuil_de_couverture(self):
        assert qualite.publiable(700, 1000)
        assert not qualite.publiable(500, 1000)


class TestVerdictTemperature:
    def _jours(self, nb_jours, par_jour=24):
        return np.repeat(np.arange(nb_jours), par_jour)

    def test_le_modele_le_plus_juste_gagne(self):
        rng = np.random.default_rng(1)
        jours = self._jours(120)
        reel = rng.normal(10, 6, size=jours.size)
        previsions = {
            "precis": reel + rng.normal(0, 0.4, size=jours.size),
            "vague": reel + rng.normal(0, 3.0, size=jours.size),
        }
        c = comparer_temperature(jours, previsions, reel)
        assert c.scores[0].modele == "precis"
        assert c.vainqueurs == ("precis",)
        assert "vague" not in c.vainqueurs

    def test_deux_modeles_identiques_sont_ex_aequo(self):
        rng = np.random.default_rng(2)
        jours = self._jours(120)
        reel = rng.normal(10, 6, size=jours.size)
        bruit = rng.normal(0, 1.5, size=jours.size)
        previsions = {
            "jumeau_a": reel + bruit,
            "jumeau_b": reel + bruit + rng.normal(0, 0.01, size=jours.size),
        }
        c = comparer_temperature(jours, previsions, reel)
        assert set(c.vainqueurs) == {"jumeau_a", "jumeau_b"}

    def test_le_biais_distingue_l_erreur_systematique(self):
        jours = self._jours(60)
        reel = np.zeros(jours.size)
        previsions = {
            "toujours_trop_chaud": np.full(jours.size, 2.0),
            "instable": np.tile([2.0, -2.0], jours.size // 2),
        }
        c = comparer_temperature(jours, previsions, reel)
        scores = {s.modele: s for s in c.scores}
        assert scores["toujours_trop_chaud"].biais == pytest.approx(2.0)
        assert scores["instable"].biais == pytest.approx(0.0)
        # Même écart moyen, biais opposés : le classement ne doit pas les séparer.
        assert scores["toujours_trop_chaud"].ecart_moyen == pytest.approx(
            scores["instable"].ecart_moyen
        )

    def test_le_reechantillonnage_est_reproductible(self):
        rng = np.random.default_rng(3)
        jours = self._jours(60)
        reel = rng.normal(10, 5, size=jours.size)
        previsions = {"a": reel + 0.5, "b": reel + 1.5}
        premier = comparer_temperature(jours, previsions, reel)
        second = comparer_temperature(jours, previsions, reel)
        assert premier.scores == second.scores

    def test_les_journees_entieres_servent_de_bloc(self):
        jours = self._jours(30)
        reel = np.zeros(jours.size)
        c = comparer_temperature(jours, {"a": reel, "b": reel + 1}, reel)
        assert c.nb_jours == 30
        assert c.nb_heures == 720


class TestVerdictPluie:
    def test_seuil_de_pluie(self):
        assert il_a_plu(np.array([0.0, 0.1, 0.2, 5.0])).tolist() == [False, False, True, True]

    def test_fausses_alertes_et_pluies_manquees_sont_distinguees(self):
        jours = np.repeat(np.arange(4), 24)
        reel = np.zeros(96)
        reel[:24] = 1.0  # il a plu toute la première journée

        previsions = {
            "alarmiste": np.ones(96),  # annonce de la pluie partout
            "optimiste": np.zeros(96),  # n'en annonce jamais
        }
        c = comparer_pluie(jours, previsions, reel)
        scores = {s.modele: s for s in c.scores}

        assert scores["alarmiste"].pluies_manquees == pytest.approx(0.0)
        assert scores["alarmiste"].fausses_alertes == pytest.approx(0.75)
        assert scores["optimiste"].pluies_manquees == pytest.approx(1.0)
        assert scores["optimiste"].fausses_alertes is None

    def test_le_modele_le_plus_juste_gagne(self):
        rng = np.random.default_rng(4)
        jours = np.repeat(np.arange(120), 24)
        reel = (rng.random(jours.size) < 0.2).astype(float)
        previsions = {
            "fiable": np.where(rng.random(jours.size) < 0.95, reel, 1 - reel),
            "hasard": (rng.random(jours.size) < 0.2).astype(float),
        }
        c = comparer_pluie(jours, previsions, reel)
        assert c.scores[0].modele == "fiable"
        assert c.vainqueurs == ("fiable",)


class TestTemps:
    """Le Temps annoncé, traduit du barème WMO."""

    def test_un_code_connu_donne_libelle_et_famille(self):
        t = temps_de(95)
        assert t.famille == "orage"
        assert t.libelle == "Orage"
        assert t.icone == "orage"

    def test_le_ciel_degage_change_d_icone_la_nuit(self):
        assert temps_de(0, jour=True).icone == "soleil"
        assert temps_de(0, jour=False).icone == "lune"
        # Le libellé, lui, ne bouge pas : le ciel est dégagé de jour comme de nuit.
        assert temps_de(0, jour=False).libelle == temps_de(0, jour=True).libelle

    def test_la_pluie_garde_la_meme_icone_de_nuit(self):
        assert temps_de(63, jour=False).icone == temps_de(63, jour=True).icone

    def test_un_modele_sans_code_n_invente_pas_de_ciel(self):
        # AROME ne publie aucun code de temps : on l'affiche, on ne le devine pas.
        assert temps_de(None) is NON_ANNONCE
        assert temps_de(None).famille == "inconnu"

    def test_un_code_hors_bareme_vaut_une_absence(self):
        assert temps_de(1234) is NON_ANNONCE

    def test_seules_les_familles_humides_mouillent(self):
        assert pleut(temps_de(80)) is True
        assert pleut(temps_de(73)) is True
        assert pleut(temps_de(3)) is False
        assert pleut(temps_de(45)) is False

    def test_toute_famille_a_une_icone(self):
        for code in range(0, 100):
            for jour in (True, False):
                assert temps_de(code, jour).icone


class TestVent:
    """Le vent, traduit en mots. Convention météo : l'angle dit d'où il vient."""

    def test_la_provenance_suit_la_rose(self):
        assert provenance(0) == "nord"
        assert provenance(90) == "est"
        assert provenance(225) == "sud-ouest"

    def test_la_rose_boucle_sur_le_nord(self):
        assert provenance(359) == "nord"
        assert provenance(360) == "nord"

    def test_la_fleche_pointe_a_l_oppose_de_la_provenance(self):
        # Un vent de nord souffle vers le sud : la flèche doit descendre.
        assert vent(10, None, 0).vers == 180
        assert vent(10, None, 270).vers == 90

    def test_la_force_se_dit_en_mots(self):
        assert vent(2, None, None).libelle == "calme"
        assert vent(25, None, None).libelle == "modéré"
        assert vent(120, None, None).libelle == "violent"

    def test_sans_vitesse_il_n_y_a_pas_de_vent_a_montrer(self):
        assert vent(None, 40, 180) is None

    def test_une_direction_absente_n_empeche_pas_d_afficher_la_vitesse(self):
        v = vent(14, None, None)
        assert v.provenance is None and v.vers is None
        assert v.vitesse_kmh == 14


class TestUv:
    """L'indice UV, sur l'échelle de l'OMM."""

    def test_chaque_palier_a_son_mot(self):
        assert uv(1).libelle == "faible"
        assert uv(4).libelle == "modéré"
        assert uv(7).libelle == "fort"
        assert uv(9).libelle == "très fort"
        assert uv(12).libelle == "extrême"

    def test_les_bornes_appartiennent_au_palier_superieur(self):
        assert uv(2.9).libelle == "faible"
        assert uv(3).libelle == "modéré"
        assert uv(11).libelle == "extrême"

    def test_les_crans_montent_avec_l_indice(self):
        assert uv(1).cran == 1
        assert uv(12).cran == CRANS_UV
        assert [uv(i).cran for i in (1, 4, 7, 9, 12)] == [1, 2, 3, 4, 5]

    def test_la_protection_commence_a_trois(self):
        assert uv(2.9).protection is False
        assert uv(3).protection is True

    def test_un_modele_qui_n_annonce_pas_l_uv_ne_rend_rien(self):
        assert uv(None) is None


class TestRessenti:
    def test_un_ecart_sous_le_degre_ne_se_dit_pas(self):
        assert ressenti(20.4, 20.0).libelle == "comme au thermomètre"

    def test_au_dessus_il_fait_plus_lourd(self):
        r = ressenti(34.0, 30.0)
        assert r.libelle == "plus lourd qu'au thermomètre"
        assert r.ecart_c == pytest.approx(4.0)

    def test_en_dessous_il_fait_plus_frais(self):
        assert ressenti(-5.0, 0.0).libelle == "plus frais qu'au thermomètre"

    def test_sans_temperature_apparente_il_n_y_a_rien_a_dire(self):
        assert ressenti(None, 20.0) is None


class TestHumidite:
    def test_chaque_palier_a_son_mot(self):
        assert humidite(20).libelle == "air sec"
        assert humidite(50).libelle == "confortable"
        assert humidite(75).libelle == "humide"
        assert humidite(95).libelle == "très humide"

    def test_les_bornes_appartiennent_au_palier_superieur(self):
        assert humidite(34.9).libelle == "air sec"
        assert humidite(35).libelle == "confortable"


class TestPression:
    def test_sans_reference_la_tendance_est_inconnue(self):
        p = pression(1013.0, None)
        assert p.variation_hpa is None
        assert p.libelle == "tendance inconnue"

    def test_une_variation_infime_est_dite_stable(self):
        assert pression(1013.5, 1013.0).libelle == "stable"

    def test_la_hausse_et_la_baisse_se_distinguent(self):
        assert pression(1015.0, 1013.0).libelle == "en hausse"
        assert pression(1011.0, 1013.0).libelle == "en baisse"

    def test_au_dela_de_trois_hectopascals_la_variation_est_forte(self):
        assert pression(1017.0, 1013.0).libelle == "en forte hausse"
        assert pression(1009.0, 1013.0).libelle == "en forte baisse"

    def test_la_variation_est_signee(self):
        assert pression(1009.0, 1013.0).variation_hpa == pytest.approx(-4.0)


class TestIsotherme:
    def test_au_dessus_du_lieu_le_denivele_est_positif(self):
        i = isotherme(2500.0, 905.0)
        assert i.au_dessus is True
        assert i.denivele_m == pytest.approx(1595.0)

    def test_sous_le_lieu_il_peut_neiger(self):
        i = isotherme(600.0, 905.0)
        assert i.au_dessus is False
        assert i.denivele_m == pytest.approx(-305.0)

    def test_sans_altitude_du_lieu_on_ne_situe_pas(self):
        assert isotherme(2500.0, None).denivele_m is None

    def test_un_modele_qui_n_annonce_pas_l_isotherme_ne_rend_rien(self):
        assert isotherme(None, 905.0) is None


class TestQualiteAir:
    def test_chaque_palier_a_son_mot(self):
        vide = {}
        assert qualite_air(10, vide).libelle == "bon"
        assert qualite_air(30, vide).libelle == "correct"
        assert qualite_air(50, vide).libelle == "moyen"
        assert qualite_air(70, vide).libelle == "mauvais"
        assert qualite_air(90, vide).libelle == "très mauvais"
        assert qualite_air(120, vide).libelle == "extrêmement mauvais"

    def test_les_crans_couvrent_toute_l_echelle(self):
        assert qualite_air(10, {}).cran == 1
        assert qualite_air(120, {}).cran == CRANS_AIR

    def test_le_polluant_dominant_est_celui_qui_tire_l_indice(self):
        q = qualite_air(35, {"ozone": 35, "pm2_5": 12, "pm10": 9})
        assert q.dominant == "ozone"

    def test_des_sous_indices_absents_n_empechent_pas_l_indice(self):
        q = qualite_air(35, {"ozone": None, "pm2_5": None})
        assert q.indice == 35
        assert q.dominant is None

    def test_sans_indice_il_n_y_a_rien_a_montrer(self):
        assert qualite_air(None, {"ozone": 35}) is None


class TestTonTemperature:
    """L'échelle thermique, qui décide de la teinte du ressenti."""

    def test_elle_diverge_autour_du_doux(self):
        assert ton_temperature(-5) == "glacial"
        assert ton_temperature(5) == "froid"
        assert ton_temperature(15) == "doux"
        assert ton_temperature(24) == "chaud"
        assert ton_temperature(33) == "torride"

    def test_les_bornes_appartiennent_au_palier_superieur(self):
        assert ton_temperature(-0.1) == "glacial"
        assert ton_temperature(0) == "froid"
        assert ton_temperature(28) == "torride"

    def test_sans_temperature_il_n_y_a_pas_de_ton(self):
        assert ton_temperature(None) is None


# --- Séries longues : la tendance d'un jour de l'année, et son refus de conclure.


def _serie_reguliere(debut, fin, valeur):
    """Un dictionnaire jour → valeur couvrant entièrement une plage d'années."""
    valeurs = {}
    for annee in range(debut, fin + 1):
        jour = date(annee, 1, 1)
        while jour.year == annee:
            valeurs[jour] = valeur(annee)
            jour += timedelta(days=1)
    return valeurs


class TestFenetre:
    def test_quinze_jours_centres(self):
        f = tendance.fenetre(2000, 8, 2)
        assert len(f) == 15
        assert f[0] == date(2000, 7, 26)
        assert f[7] == date(2000, 8, 2)
        assert f[-1] == date(2000, 8, 9)

    def test_debut_janvier_emprunte_a_decembre_precedent(self):
        f = tendance.fenetre(2000, 1, 3)
        assert f[0] == date(1999, 12, 27)
        assert f[-1] == date(2000, 1, 10)

    def test_le_29_fevrier_se_replie_sur_le_28(self):
        # Sans ce repli, la série n'aurait de point qu'une année sur quatre.
        assert tendance.fenetre(2001, 2, 29)[7] == date(2001, 2, 28)
        assert tendance.fenetre(2000, 2, 29)[7] == date(2000, 2, 29)


class TestAgregation:
    def test_une_annee_par_annee_couverte(self):
        valeurs = _serie_reguliere(1990, 1995, lambda a: 20.0)
        points = tendance.agreger(valeurs, 8, 2, range(1990, 1996))
        assert [p.annee for p in points] == [1990, 1991, 1992, 1993, 1994, 1995]
        assert all(p.nb_jours == 15 for p in points)
        assert points[0].valeur == 20.0

    def test_les_jours_de_decembre_comptent_pour_l_annee_visee(self):
        # Fenêtre du 3 janvier 1991 : du 27 au 31 décembre 1990, puis du 1er au
        # 10 janvier 1991 — cinq jours empruntés à l'année civile précédente, dix
        # de l'année visée, et le tout compte pour 1991.
        valeurs = _serie_reguliere(1990, 1991, lambda a: float(a))
        points = tendance.agreger(valeurs, 1, 3, range(1991, 1992))
        assert points[0].annee == 1991
        assert points[0].valeur == pytest.approx((5 * 1990 + 10 * 1991) / 15)

    def test_une_annee_trop_creuse_est_omise_et_non_mise_a_zero(self):
        valeurs = _serie_reguliere(1990, 1991, lambda a: 20.0)
        for jour in tendance.fenetre(1991, 8, 2)[:10]:
            valeurs.pop(jour, None)
        points = tendance.agreger(valeurs, 8, 2, range(1990, 1992))
        assert [p.annee for p in points] == [1990]


class TestAjustement:
    def _points(self, debut, fin, valeur):
        return [
            tendance.AnneeAgregee(annee=a, valeur=valeur(a), nb_jours=15)
            for a in range(debut, fin + 1)
        ]

    def test_refus_sous_trente_annees(self):
        assert tendance.ajuster(self._points(1990, 2010, lambda a: 20.0)) is None

    def test_retrouve_une_pente_connue(self):
        # +0,03 °C par an, soit +0,3 °C par décennie, sans bruit.
        points = self._points(1970, 2020, lambda a: 10.0 + 0.03 * (a - 1970))
        t = tendance.ajuster(points)
        assert t.pente_par_decennie == pytest.approx(0.3)
        assert t.r2 == pytest.approx(1.0)
        assert t.evolution_totale == pytest.approx(1.5)
        assert t.significative

    def test_un_bruit_sans_pente_n_est_pas_declare_significatif(self):
        points = self._points(1970, 2020, lambda a: 10.0 + (1.0 if a % 2 else -1.0))
        t = tendance.ajuster(points)
        assert abs(t.pente_par_decennie) < t.incertitude_par_decennie
        assert not t.significative

    def test_l_incertitude_s_evase_en_s_eloignant_des_annees_mesurees(self):
        bruite = lambda a: 10.0 + 0.03 * (a - 1970) + (0.5 if a % 3 else -0.5)  # noqa: E731
        t = tendance.ajuster(self._points(1970, 2020, bruite))
        assert t.incertitude(t.annee_pivot) < t.incertitude(2020) < t.incertitude(2050)


# --- Cycle annuel : toutes les années superposées sur l'axe des quantièmes.


class TestQuantieme:
    def test_le_29_fevrier_n_a_pas_de_rang(self):
        assert cycle.quantieme(date(2000, 2, 29)) is None

    def test_le_1er_mars_tombe_au_meme_rang_les_annees_bissextiles(self):
        # Sans ce décalage, une courbe sur quatre serait décalée d'un jour par
        # rapport aux autres sur les trois quarts de l'année.
        assert cycle.quantieme(date(2000, 3, 1)) == cycle.quantieme(date(2001, 3, 1)) == 60

    def test_les_bornes_de_l_annee(self):
        assert cycle.quantieme(date(2001, 1, 1)) == 1
        assert cycle.quantieme(date(2001, 12, 31)) == 365
        assert cycle.quantieme(date(2000, 12, 31)) == 365

    def test_avant_fevrier_rien_ne_bouge(self):
        assert cycle.quantieme(date(2000, 2, 28)) == cycle.quantieme(date(2001, 2, 28)) == 59


class TestMoyennesQuotidiennes:
    def test_la_demi_somme_des_extremes(self):
        jour = date(2001, 7, 1)
        assert cycle.moyennes_quotidiennes({jour: 10.0}, {jour: 20.0}) == {jour: 15.0}

    def test_une_journee_a_un_seul_extreme_est_ecartee(self):
        # Ne garder que le maximum ferait pencher la moyenne du même côté toute l'année.
        complet, boiteux = date(2001, 7, 1), date(2001, 7, 2)
        moyennes = cycle.moyennes_quotidiennes(
            {complet: 10.0, boiteux: 12.0}, {complet: 20.0}
        )
        assert moyennes == {complet: 15.0}


class TestLissage:
    def _dix_jours(self):
        return {date(2001, 1, j): float(j) for j in range(1, 11)}

    def test_moyenne_centree(self):
        lissees = cycle.lisser(self._dix_jours(), demi_largeur=2, couverture=0.0)
        assert lissees[date(2001, 1, 5)] == pytest.approx(5.0)

    def test_les_bords_incomplets_sont_ecartes(self):
        lissees = cycle.lisser(self._dix_jours(), demi_largeur=2, couverture=1.0)
        assert min(lissees) == date(2001, 1, 3)
        assert max(lissees) == date(2001, 1, 8)

    def test_la_fenetre_du_1er_janvier_va_chercher_decembre(self):
        valeurs = {date(2000, 12, 30): 0.0, date(2000, 12, 31): 0.0, date(2001, 1, 1): 3.0}
        lissees = cycle.lisser(valeurs, demi_largeur=2, couverture=0.0)
        assert lissees[date(2001, 1, 1)] == pytest.approx(1.0)

    def test_une_lacune_ne_produit_pas_de_point(self):
        valeurs = {date(2001, 1, 1): 5.0, date(2001, 6, 1): 20.0}
        assert cycle.lisser(valeurs, demi_largeur=2, couverture=1.0) == {}


class TestCycles:
    def _annee(self, annee, valeur=10.0):
        jour, valeurs = date(annee, 1, 1), {}
        while jour.year == annee:
            valeurs[jour] = valeur
            jour += timedelta(days=1)
        return valeurs

    def test_un_point_tous_les_cinq_jours(self):
        (courbe,) = cycle.cycles(self._annee(2001), pas=5, minimum=3)
        assert courbe.quantiemes[:4] == (1, 6, 11, 16)
        assert len(courbe.quantiemes) == 73
        assert courbe.complete

    def test_une_annee_trop_courte_est_ecartee(self):
        valeurs = {date(2001, 1, j): 10.0 for j in range(1, 20)}
        assert cycle.cycles(valeurs, pas=5, minimum=10) == []

    def test_une_annee_partielle_n_est_pas_declaree_complete(self):
        valeurs = {d: v for d, v in self._annee(2001).items() if d.month <= 6}
        (courbe,) = cycle.cycles(valeurs, pas=5, minimum=3)
        assert not courbe.complete


class TestMoyennesMensuelles:
    def test_chaque_mois_recoit_ses_points(self):
        courbe = cycle.CycleAnnuel(
            annee=2001, quantiemes=(1, 31, 32, 59, 335), valeurs_c=(0.0, 2.0, 10.0, 10.0, 5.0)
        )
        mensuelles = cycle.moyennes_mensuelles(courbe)
        assert mensuelles[0] == pytest.approx(1.0)   # janvier : quantièmes 1 et 31
        assert mensuelles[1] == pytest.approx(10.0)  # février : 32 et 59
        assert mensuelles[11] == pytest.approx(5.0)  # décembre : 335
        assert mensuelles[5] is None                 # juin : aucun point


class TestDecennies:
    def test_de_dix_en_dix_depuis_la_derniere_annee(self):
        # L'ancrage est la dernière année et non un multiple rond : la question est
        # « où en est-on par rapport à il y a dix ans », pas « que valait 1980 ».
        assert cycle.decennies(2026, 1998) == [2026, 2016, 2006]

    def test_une_seule_annee_disponible(self):
        assert cycle.decennies(2026, 2026) == [2026]


# --- Indicateurs comptés : franchissements, saison sans gel, records.


def _annee_de_valeurs(annee, valeur):
    """Une année civile complète, la même valeur chaque jour."""
    jour, valeurs = date(annee, 1, 1), {}
    while jour.year == annee:
        valeurs[jour] = valeur(jour) if callable(valeur) else valeur
        jour += timedelta(days=1)
    return valeurs


class TestFranchissements:
    GEL = indicateurs.PAR_CLE["gel"]
    CHALEUR = indicateurs.PAR_CLE["chaleur"]

    def test_compte_les_jours_sous_zero(self):
        valeurs = _annee_de_valeurs(2001, lambda j: -5.0 if j.month == 1 else 10.0)
        (annee,) = indicateurs.compter(valeurs, self.GEL)
        assert annee.jours == 31
        assert annee.mesures == 365

    def test_le_seuil_haut_est_inclusif(self):
        # « a atteint 30 °C » : la journée à 30,0 compte.
        valeurs = _annee_de_valeurs(2001, lambda j: 30.0 if j.month == 7 else 5.0)
        (annee,) = indicateurs.compter(valeurs, self.CHALEUR)
        assert annee.jours == 31

    def test_une_annee_lacunaire_est_ecartee_et_non_extrapolee(self):
        # Sans ce garde-fou, une demi-année dessinerait une fausse accalmie.
        valeurs = {d: -5.0 for d in _annee_de_valeurs(2001, -5.0) if d.month <= 6}
        assert indicateurs.compter(valeurs, self.GEL) == []

    def test_les_annees_sortent_dans_l_ordre(self):
        valeurs = _annee_de_valeurs(2002, -1.0) | _annee_de_valeurs(2001, -1.0)
        assert [a.annee for a in indicateurs.compter(valeurs, self.GEL)] == [2001, 2002]


class TestSaisonSansGel:
    def _annee_avec_gels(self, annee, dernier, premier):
        return {
            d: (-1.0 if d.timetuple().tm_yday in (dernier, premier) else 10.0)
            for d in _annee_de_valeurs(annee, 0.0)
        }

    def test_les_deux_bornes_et_la_duree(self):
        (saison,) = indicateurs.saisons_sans_gel(self._annee_avec_gels(2001, 100, 300))
        assert saison.dernier_gel == 100
        assert saison.premier_gel == 300
        assert saison.duree == 200

    def test_seul_le_dernier_gel_de_printemps_compte(self):
        valeurs = self._annee_avec_gels(2001, 100, 300)
        valeurs[date(2001, 1, 15)] = -3.0
        (saison,) = indicateurs.saisons_sans_gel(valeurs)
        assert saison.dernier_gel == 100

    def test_une_annee_sans_gel_d_automne_est_omise(self):
        # Sa saison déborde de l'année civile : la borner au 31 décembre inventerait
        # une date que la mesure ne donne pas.
        valeurs = self._annee_avec_gels(2001, 100, 300)
        valeurs[date(2001, 10, 27)] = 10.0
        assert indicateurs.saisons_sans_gel(valeurs) == []


class TestRecords:
    def _serie(self, valeurs_par_annee):
        serie = {}
        for annee, valeur in valeurs_par_annee.items():
            serie.update(_annee_de_valeurs(annee, valeur))
        return serie

    def test_le_record_de_chaleur_revient_a_l_annee_la_plus_chaude(self):
        serie = self._serie({2001: 10.0, 2002: 30.0, 2003: 20.0})
        tenus = indicateurs.records(serie, au_plus_haut=True)
        assert len(tenus) == 365
        assert {r.annee for r in tenus} == {2002}

    def test_le_record_de_froid_revient_a_l_annee_la_plus_froide(self):
        serie = self._serie({2001: 10.0, 2002: 30.0, 2003: 20.0})
        assert {r.annee for r in indicateurs.records(serie, au_plus_haut=False)} == {2001}

    def test_un_climat_stable_donne_un_indice_proche_de_un(self):
        # Vingt années identiques : chacune détient le record d'autant de jours que
        # l'ordre de parcours le veut, mais chaque décennie reste à sa part.
        serie = self._serie({a: 10.0 + (a % 7) for a in range(2001, 2021)})
        tenus = indicateurs.records(serie, au_plus_haut=True)
        parts = indicateurs.parts_par_decennie(serie, tenus)
        assert sum(p.attendus for p in parts) == pytest.approx(len(tenus))
        assert sum(p.records for p in parts) == len(tenus)

    # Années volontairement non bissextiles : le 29 février ne concourt qu'avec les
    # autres 29 février, ce qui est correct mais brouillerait l'arithmétique du test.
    ANCIENNES = (2001, 2002, 2003)
    RECENTES = (2011, 2013)

    def test_une_decennie_qui_rafle_tout_depasse_sa_bande_de_bruit(self):
        serie = self._serie(
            dict.fromkeys(self.ANCIENNES, 10.0) | dict.fromkeys(self.RECENTES, 40.0)
        )
        parts = indicateurs.parts_par_decennie(serie, indicateurs.records(serie, True))
        par_decennie = {p.decennie: p for p in parts}
        # Deux années sur cinq détiennent la totalité des records : 1 / (2/5) = 2,5.
        assert par_decennie[2010].indice == pytest.approx(2.5)
        assert par_decennie[2010].remarquable
        assert par_decennie[2000].indice == pytest.approx(0.0)
        assert par_decennie[2000].remarquable

    def test_une_decennie_partielle_n_est_pas_penalisee(self):
        # Deux années dans la seconde décennie contre trois dans la première :
        # l'attente doit suivre, sinon la décennie courte paraîtrait toujours pauvre.
        serie = self._serie(dict.fromkeys(self.ANCIENNES + self.RECENTES, 10.0))
        parts = {p.decennie: p for p in indicateurs.parts_par_decennie(serie, [])}
        assert parts[2000].attendus == pytest.approx(365 * 3 / 5)
        assert parts[2010].attendus == pytest.approx(365 * 2 / 5)


# --- Sécheresse : le bilan hydrique estival et son échelle standardisée.


def _saison_pleine(annee, valeur):
    """Toute la saison mai-septembre d'une année, à valeur constante."""
    jour, valeurs = date(annee, 5, 1), {}
    while jour <= date(annee, 9, 30):
        valeurs[jour] = valeur
        jour += timedelta(days=1)
    return valeurs


class TestBilans:
    def test_le_cumul_ne_porte_que_sur_la_saison(self):
        pluie = _saison_pleine(2001, 2.0) | {date(2001, 1, 15): 100.0}
        etp = _saison_pleine(2001, 3.0)
        (bilan,) = secheresse.bilans(pluie, etp)
        # 153 jours de saison à 2 mm : le déluge de janvier n'y entre pas.
        assert bilan.apport_mm == pytest.approx(153 * 2.0)
        assert bilan.demande_mm == pytest.approx(153 * 3.0)
        assert bilan.bilan_mm == pytest.approx(-153.0)

    def test_une_saison_trouee_d_un_seul_cote_est_ecartee(self):
        # Un bilan calculé sur une pluie complète et une demande trouée paraîtrait
        # excédentaire alors qu'il ne serait qu'incomplet.
        pluie = _saison_pleine(2001, 2.0)
        etp = {j: 3.0 for j in _saison_pleine(2001, 3.0) if j.month != 7}
        assert secheresse.bilans(pluie, etp) == []

    def test_une_annee_sans_l_autre_serie_est_ignoree(self):
        pluie = _saison_pleine(2001, 2.0) | _saison_pleine(2002, 2.0)
        etp = _saison_pleine(2001, 3.0)
        assert [b.annee for b in secheresse.bilans(pluie, etp)] == [2001]


class TestEchelleStandardisee:
    def _saisons(self, valeurs):
        return [
            secheresse.BilanSaison(annee=a, apport_mm=v, demande_mm=0.0, jours=153)
            for a, v in valeurs.items()
        ]

    def test_refus_sous_trente_annees(self):
        courtes = self._saisons({a: float(a) for a in range(1990, 2010)})
        assert secheresse.standardiser(courtes) == []

    def test_la_plus_seche_recoit_l_indice_le_plus_bas(self):
        saisons = self._saisons({a: float(a % 37) for a in range(1950, 2010)})
        etats = {e.annee: e for e in secheresse.standardiser(saisons)}
        plus_sec = min(saisons, key=lambda b: b.bilan_mm).annee
        assert etats[plus_sec].indice == min(e.indice for e in etats.values())
        assert etats[plus_sec].sec

    def test_l_indice_ne_sort_pas_de_l_echantillon(self):
        # Conséquence assumée de la standardisation par les rangs : sur n années, la
        # plus sèche vaut au mieux Phi-1(0,44/(n+0,12)).
        saisons = self._saisons({a: float(a) for a in range(1950, 2000)})
        indices = [e.indice for e in secheresse.standardiser(saisons)]
        assert min(indices) > -2.6
        assert max(indices) < 2.6

    def test_la_moitie_des_annees_est_sous_zero(self):
        saisons = self._saisons({a: float(a % 41) for a in range(1930, 2030)})
        etats = secheresse.standardiser(saisons)
        negatifs = sum(1 for e in etats if e.indice < 0)
        assert 45 <= negatifs <= 55, "la standardisation doit centrer la série"


class TestClasses:
    def test_les_bornes_usuelles(self):
        assert secheresse.classe_de(-2.5)[0] == "extremement_sec"
        assert secheresse.classe_de(-2.0)[0] == "extremement_sec"
        assert secheresse.classe_de(-1.6)[0] == "severement_sec"
        assert secheresse.classe_de(-1.0)[0] == "moderement_sec"
        assert secheresse.classe_de(0.0)[0] == "normal"
        assert secheresse.classe_de(1.0)[0] == "normal"
        assert secheresse.classe_de(1.2)[0] == "moderement_humide"
        assert secheresse.classe_de(2.5)[0] == "extremement_humide"


class TestFrequences:
    def test_rapportees_aux_annees_apportees(self):
        # Une décennie tronquée ne doit pas paraître épargnée parce qu'elle est brève.
        etats = [
            secheresse.EtatSec(annee=a, bilan_mm=0.0, indice=-1.5 if a >= 2010 else 0.0,
                               classe="x", libelle="x")
            for a in list(range(2000, 2010)) + [2010, 2011]
        ]
        par_decennie = {f.decennie: f for f in secheresse.frequences(etats)}
        assert par_decennie[2000].seches == 0
        assert par_decennie[2010].annees == 2
        assert par_decennie[2010].part == pytest.approx(1.0)


# --- Neige : l'enneigement, saison après saison.


class TestSaisonNeige:
    def test_la_saison_va_d_aout_a_juillet(self):
        # L'hiver 1962-1963 est « la saison 1962 » : la caler sur l'année civile
        # couperait chaque hiver en son milieu.
        assert neige.saison_de(date(1962, 8, 1)) == 1962
        assert neige.saison_de(date(1962, 12, 31)) == 1962
        assert neige.saison_de(date(1963, 1, 15)) == 1962
        assert neige.saison_de(date(1963, 7, 31)) == 1962
        assert neige.saison_de(date(1963, 8, 1)) == 1963

    def test_le_rang_se_compte_depuis_le_1er_aout(self):
        assert neige.rang_dans_saison(date(1962, 8, 1), 1962) == 0
        assert neige.rang_dans_saison(date(1963, 1, 1), 1962) == 153


def _saison_mesuree(millesime, hauteurs_par_jour=None):
    """Une saison complète mesurée, à zéro sauf aux jours indiqués."""
    jour, valeurs = date(millesime, 8, 1), {}
    while jour < date(millesime + 1, 8, 1):
        valeurs[jour] = 0.0
        jour += timedelta(days=1)
    valeurs.update(hauteurs_par_jour or {})
    return valeurs


class TestSaisonsNeige:
    def test_compte_les_jours_au_sol_et_le_maximum(self):
        hauteurs = _saison_mesuree(1962, {
            date(1962, 12, 20): 15.0,
            date(1962, 12, 21): 40.0,
            date(1963, 3, 10): 5.0,
        })
        (s,) = neige.saisons(hauteurs)
        assert s.saison == 1962
        assert s.libelle == "1962-1963"
        assert s.jours_au_sol == 3
        assert s.epaisseur_max_cm == 40.0
        assert s.premiere == date(1962, 12, 20)
        assert s.derniere == date(1963, 3, 10)

    def test_une_saison_sans_neige_est_conservee_a_zero(self):
        # L'omettre gonflerait la moyenne des saisons restantes.
        (s,) = neige.saisons(_saison_mesuree(1962))
        assert s.jours_au_sol == 0
        assert not s.enneigee
        assert s.premiere is None

    def test_une_saison_trop_lacunaire_est_ecartee(self):
        # Un hiver relevé à moitié compterait mécaniquement moins de jours et
        # dessinerait un recul là où il n'y a qu'un trou dans le relevé.
        partielle = {j: v for j, v in _saison_mesuree(1962).items() if j.month in (12, 1, 2)}
        assert neige.saisons(partielle) == []

    def test_le_cumul_de_neige_fraiche_suit_la_saison(self):
        hauteurs = _saison_mesuree(1962, {date(1963, 1, 5): 20.0})
        fraiches = {date(1962, 12, 30): 12.0, date(1963, 1, 5): 20.0, date(1963, 9, 1): 99.0}
        (s,) = neige.saisons(hauteurs, fraiches)
        assert s.fraiche_cm == pytest.approx(32.0), "septembre suivant appartient à 1963"
