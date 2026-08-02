from datetime import date

import numpy as np
import pytest

from meteo.domaine import qualite
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
from meteo.domaine.modeles import CATALOGUE, modeles_couvrant
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
        assert {m.nom for m in modeles_couvrant(7)} == {"ECMWF", "GFS"}

    def test_arome_ne_court_pas_au_dela_d_un_jour(self):
        arome = next(m for m in CATALOGUE if m.nom == "AROME")
        assert arome.couvre(1)
        assert not arome.couvre(2)


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
