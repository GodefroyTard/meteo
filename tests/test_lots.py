from datetime import date

from meteo.domaine.saison import Saison, heures_attendues


class TestHeuresAttendues:
    """Le dénominateur de la Couverture : ce qu'on aurait dû mesurer."""

    def test_un_mois_d_ete_complet(self):
        assert heures_attendues(date(2025, 6, 1), date(2025, 6, 30), Saison.ETE) == 720

    def test_un_mois_d_ete_ne_compte_pas_pour_l_hiver(self):
        assert heures_attendues(date(2025, 6, 1), date(2025, 6, 30), Saison.HIVER) == 0

    def test_une_periode_a_cheval_ne_compte_que_la_part_saisonniere(self):
        # Février (28 j, hiver) puis mars (31 j, printemps).
        assert heures_attendues(date(2025, 2, 1), date(2025, 3, 31), Saison.HIVER) == 28 * 24
        assert heures_attendues(date(2025, 2, 1), date(2025, 3, 31), Saison.PRINTEMPS) == 31 * 24

    def test_l_annee_se_repartit_entierement(self):
        debut, fin = date(2025, 1, 1), date(2025, 12, 31)
        total = sum(heures_attendues(debut, fin, s) for s in Saison)
        assert total == 365 * 24
