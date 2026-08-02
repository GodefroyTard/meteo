import io
from datetime import date

import pytest

from meteo.collecte.climatologie import FormatInattendu, lire_csv

ENTETE = "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJ;RR;QRR;TN;QTN;TX;QTX"


def _fichier(*lignes: str) -> io.StringIO:
    return io.StringIO("\n".join((ENTETE, *lignes)) + "\n")


class TestLectureClimatologie:
    def test_une_journee_validee(self):
        flux = _fichier("38020001;AUTRANS;45.17;5.54;1069;19700802;0.0;1;8.4;1;24.6;1")
        (journee,) = list(lire_csv(flux))
        assert journee.poste_numero == "38020001"
        assert journee.nom == "AUTRANS"
        assert journee.jour == date(1970, 8, 2)
        assert journee.tn_c == 8.4
        assert journee.tx_c == 24.6
        assert journee.altitude == 1069.0

    def test_une_valeur_douteuse_est_ecartee_sans_perdre_la_journee(self):
        # QTX=2 : valeur douteuse. Le maximum tombe, le minimum reste.
        flux = _fichier("38020001;AUTRANS;45.17;5.54;1069;19700802;0.0;1;8.4;1;24.6;2")
        (journee,) = list(lire_csv(flux))
        assert journee.tn_c == 8.4
        assert journee.tx_c is None

    def test_la_qualite_9_est_retenue(self):
        # Les écarter amputerait les années 1950, dont elles font près de 60 %
        # des maxima : ce sont des valeurs filtrées, pas des valeurs suspectes.
        flux = _fichier("38020001;AUTRANS;45.17;5.54;1069;19550802;0.0;1;7.1;9;23.0;9")
        (journee,) = list(lire_csv(flux))
        assert journee.tn_c == 7.1
        assert journee.tx_c == 23.0

    def test_une_ligne_sans_aucune_temperature_est_omise(self):
        # Les postes purement pluviométriques représentent plus de la moitié des
        # lignes d'un département : les charger gonflerait la base pour rien.
        flux = _fichier(
            "38020001;AUTRANS;45.17;5.54;1069;19700802;12.4;1;;;;",
            "38020001;AUTRANS;45.17;5.54;1069;19700803;0.0;1;8.0;1;25.0;1",
        )
        journees = list(lire_csv(flux))
        assert [j.jour for j in journees] == [date(1970, 8, 3)]

    def test_une_journee_dont_les_deux_valeurs_sont_douteuses_disparait(self):
        flux = _fichier("38020001;AUTRANS;45.17;5.54;1069;19700802;0.0;1;8.4;0;24.6;2")
        assert list(lire_csv(flux)) == []

    def test_une_date_malformee_est_ignoree(self):
        flux = _fichier(
            "38020001;AUTRANS;45.17;5.54;1069;1970080;0.0;1;8.4;1;24.6;1",
            "38020001;AUTRANS;45.17;5.54;1069;19700803;0.0;1;8.0;1;25.0;1",
        )
        journees = list(lire_csv(flux))
        assert [j.jour for j in journees] == [date(1970, 8, 3)]

    def test_un_fichier_sans_les_colonnes_attendues_est_refuse(self):
        # Météo-France sert aussi un fichier « autres-parametres », sans TN ni TX.
        # Mieux vaut une erreur nette qu'un chargement silencieusement vide.
        flux = io.StringIO("NUM_POSTE;NOM_USUEL;AAAAMMJJ;PMERM\n38020001;AUTRANS;19700802;1015\n")
        with pytest.raises(FormatInattendu, match="Colonnes absentes"):
            list(lire_csv(flux))
