import io
from datetime import date

import pytest

from meteo.collecte.climatologie import (
    MESURES_AUTRES,
    MESURES_TEMPERATURES,
    FormatInattendu,
    lire_csv,
)

ENTETE_T = "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJ;RR;QRR;TN;QTN;TX;QTX"
ENTETE_A = "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJ;ETPMON;QETPMON;ETPGRILLE;QETPGRILLE"


def _fichier(entete: str, *lignes: str) -> io.StringIO:
    return io.StringIO("\n".join((entete, *lignes)) + "\n")


def _temperatures(*lignes: str):
    return list(lire_csv(_fichier(ENTETE_T, *lignes), MESURES_TEMPERATURES))


def _autres(*lignes: str):
    return list(lire_csv(_fichier(ENTETE_A, *lignes), MESURES_AUTRES))


class TestTemperaturesEtPluie:
    def test_une_journee_validee(self):
        (j,) = _temperatures("38020001;AUTRANS;45.17;5.54;1069;19700802;3.4;1;8.4;1;24.6;1")
        assert j.poste_numero == "38020001"
        assert j.nom == "AUTRANS"
        assert j.jour == date(1970, 8, 2)
        assert (j.tn_c, j.tx_c, j.rr_mm) == (8.4, 24.6, 3.4)
        assert j.altitude == 1069.0
        assert j.etp_monteith_mm is None, "cette famille de fichiers ne porte pas l'ETP"

    def test_une_valeur_douteuse_est_ecartee_sans_perdre_la_journee(self):
        # QTX=2 : valeur douteuse. Le maximum tombe, le reste demeure.
        (j,) = _temperatures("38020001;AUTRANS;45.17;5.54;1069;19700802;3.4;1;8.4;1;24.6;2")
        assert (j.tn_c, j.rr_mm) == (8.4, 3.4)
        assert j.tx_c is None

    def test_la_qualite_9_est_retenue(self):
        # Les écarter amputerait les années 1950, dont elles font près de 60 %
        # des maxima : ce sont des valeurs filtrées, pas des valeurs suspectes.
        (j,) = _temperatures("38020001;AUTRANS;45.17;5.54;1069;19550802;0.0;9;7.1;9;23.0;9")
        assert (j.tn_c, j.tx_c, j.rr_mm) == (7.1, 23.0, 0.0)

    def test_un_poste_pluviometrique_seul_est_conserve(self):
        # Plus de la moitié des lignes d'un département n'ont que la pluie. Les
        # écarter fermerait la porte à tout indicateur de sécheresse.
        (j,) = _temperatures("38020001;AUTRANS;45.17;5.54;1069;19700802;12.4;1;;;;")
        assert j.rr_mm == 12.4
        assert j.tn_c is None and j.tx_c is None

    def test_une_ligne_sans_aucune_mesure_est_omise(self):
        journees = _temperatures(
            "38020001;AUTRANS;45.17;5.54;1069;19700802;;;;;;",
            "38020001;AUTRANS;45.17;5.54;1069;19700803;0.0;1;8.0;1;25.0;1",
        )
        assert [j.jour for j in journees] == [date(1970, 8, 3)]

    def test_une_journee_entierement_douteuse_disparait(self):
        assert _temperatures("38020001;AUTRANS;45.17;5.54;1069;19700802;3.4;0;8.4;0;24.6;2") == []

    def test_une_date_malformee_est_ignoree(self):
        journees = _temperatures(
            "38020001;AUTRANS;45.17;5.54;1069;1970080;0.0;1;8.4;1;24.6;1",
            "38020001;AUTRANS;45.17;5.54;1069;19700803;0.0;1;8.0;1;25.0;1",
        )
        assert [j.jour for j in journees] == [date(1970, 8, 3)]


class TestEvapotranspiration:
    def test_les_deux_sources_cohabitent(self):
        # Elles ne valent pas la même chose : Monteith vient des mesures du poste,
        # la grille d'une analyse. On les stocke séparément (ADR 0009).
        (j,) = _autres("38384001;GRENOBLE-ST GEOIRS;45.36;5.33;376;20030802;6.8;1;5.9;9")
        assert j.etp_monteith_mm == 6.8
        assert j.etp_grille_mm == 5.9
        assert j.tn_c is None and j.rr_mm is None

    def test_la_grille_seule_suffit_a_retenir_la_journee(self):
        (j,) = _autres("38548001;VILLARD-DE-LANS;45.07;5.55;1027;20030802;;;4.7;9")
        assert j.etp_monteith_mm is None
        assert j.etp_grille_mm == 4.7


class TestFormat:
    def test_un_fichier_sans_les_colonnes_attendues_est_refuse(self):
        # Mieux vaut une erreur nette qu'un chargement silencieusement vide : c'est
        # exactement ce qui arriverait si l'on lisait le mauvais fichier.
        flux = _fichier(ENTETE_T, "38020001;AUTRANS;45.17;5.54;1069;19700802;0.0;1;8.4;1;24.6;1")
        with pytest.raises(FormatInattendu, match="Colonnes absentes"):
            list(lire_csv(flux, MESURES_AUTRES))

    def test_l_identite_manquante_est_signalee(self):
        flux = io.StringIO("AAAAMMJJ;TN;QTN\n19700802;8.4;1\n")
        with pytest.raises(FormatInattendu, match="NUM_POSTE"):
            list(lire_csv(flux, ("TN",)))
