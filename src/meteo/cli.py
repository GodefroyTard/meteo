"""Commandes d'exploitation."""

from datetime import date

import typer

from meteo.config import config
from meteo.lots import backfill, climatologie, rafraichissement, referentiel, verdicts
from meteo.stockage.session import creer_schema

app = typer.Typer(help="Fiabilité des modèles météo, station par station.", no_args_is_help=True)


@app.command("init-base")
def init_base() -> None:
    """Crée les tables si elles n'existent pas."""
    creer_schema()
    typer.echo("Schéma en place.")


@app.command("stations")
def stations() -> None:
    """Importe le référentiel StatIC et fixe le périmètre suivi."""
    cfg = config()
    retenues = referentiel.importer()
    typer.echo(
        f"{len(retenues)} stations actives à moins de {cfg.rayon_km:g} km "
        f"de ({cfg.centre_lat}, {cfg.centre_lon}) :"
    )
    for s in retenues:
        typer.echo(f"  {s.distance_km:5.1f} km  {s.altitude:>5.0f} m  {s.code:12} {s.nom}")


@app.command("climatologie")
def charger_climatologie(
    departements: str = typer.Option(
        "",
        help="Départements séparés par des virgules. Par défaut, METEO_DEPARTEMENTS_CLIMAT.",
    ),
) -> None:
    """Charge les séries longues Météo-France (températures quotidiennes depuis 1950)."""
    demandes = [d.strip() for d in departements.split(",") if d.strip()]
    resultat = climatologie.charger(demandes or None)
    typer.echo(
        f"{resultat['journees']} journées chargées pour les départements "
        f"{', '.join(resultat['departements'])}, "
        f"{resultat['postes']} postes référencés."
    )


@app.command("previsions")
def previsions(
    debut: str = typer.Option(None, help="Date de début, AAAA-MM-JJ."),
    fin: str = typer.Option(None, help="Date de fin, AAAA-MM-JJ."),
) -> None:
    """Backfille les prévisions passées depuis Open-Meteo."""
    n = backfill.previsions(
        date.fromisoformat(debut) if debut else None,
        date.fromisoformat(fin) if fin else None,
    )
    typer.echo(f"{n} prévisions enregistrées.")


@app.command("observations")
def observations(
    debut: str = typer.Option(None, help="Date de début, AAAA-MM-JJ."),
    fin: str = typer.Option(None, help="Date de fin, AAAA-MM-JJ."),
) -> None:
    """Backfille les observations depuis Infoclimat.

    Le jeton étant lié à une adresse IP déclarée, cette commande ne fonctionne que
    depuis la machine déclarée.
    """
    n = backfill.observations(
        date.fromisoformat(debut) if debut else None,
        date.fromisoformat(fin) if fin else None,
    )
    typer.echo(f"{n} observations enregistrées.")


@app.command("verdicts")
def calculer_verdicts(
    debut: str = typer.Option(None, help="Date de début, AAAA-MM-JJ."),
    fin: str = typer.Option(None, help="Date de fin, AAAA-MM-JJ."),
) -> None:
    """Recalcule tous les verdicts et remplace la table."""
    n = verdicts.calculer(
        date.fromisoformat(debut) if debut else None,
        date.fromisoformat(fin) if fin else None,
    )
    typer.echo(f"{n} lignes de verdict écrites.")


@app.command("rafraichir")
def rafraichir() -> None:
    """Met à jour les derniers jours puis recalcule les verdicts.

    C'est la commande du lot planifié. Contrairement à `previsions` et `observations`
    sans bornes, elle ne recollecte qu'une fenêtre récente : elle peut donc tourner
    toutes les heures sans matraquer Open-Meteo ni Infoclimat.
    """
    compte = rafraichissement.executer()
    typer.echo(
        f"{compte['previsions']} prévisions et {compte['observations']} observations "
        f"collectées, {compte['verdicts']} lignes de verdict écrites."
    )


@app.command("servir")
def servir(hote: str = "127.0.0.1", port: int = 8000) -> None:
    """Démarre l'API et le front."""
    import uvicorn

    uvicorn.run("meteo.api.app:app", host=hote, port=port)


if __name__ == "__main__":
    app()
