"""Schéma de la base.

Trois tables portent la donnée brute (Stations, Observations, Prévisions) et une
quatrième les Verdicts matérialisés, seule lue par l'API.
"""

from datetime import date, datetime

from sqlalchemy import (
    REAL,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Station(Base):
    """Un point de mesure du réseau StatIC."""

    __tablename__ = "station"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    nom: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float]
    longitude: Mapped[float]
    altitude: Mapped[float]
    derniere_activite: Mapped[date | None] = mapped_column(Date)
    suivie: Mapped[bool] = mapped_column(Boolean, default=False)
    """Vrai si la Station fait partie du périmètre backfillé."""


class Observation(Base):
    """Une mesure réelle. `valide` porte le verdict des garde-fous qualité."""

    __tablename__ = "observation"

    station_code: Mapped[str] = mapped_column(
        ForeignKey("station.code", ondelete="CASCADE"), primary_key=True
    )
    instant: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    temperature_c: Mapped[float | None] = mapped_column(REAL)
    precipitation_mm: Mapped[float | None] = mapped_column(REAL)
    valide: Mapped[bool] = mapped_column(Boolean, default=True)


class Prevision(Base):
    """Ce qu'un Modèle annonçait pour un instant, vu depuis une Anticipation.

    Les valeurs sont déjà ramenées à l'altitude de la Station (cf. ADR 0002).
    """

    __tablename__ = "prevision"

    station_code: Mapped[str] = mapped_column(
        ForeignKey("station.code", ondelete="CASCADE"), primary_key=True
    )
    modele: Mapped[str] = mapped_column(String(48), primary_key=True)
    anticipation: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    instant: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    temperature_c: Mapped[float | None] = mapped_column(REAL)
    precipitation_mm: Mapped[float | None] = mapped_column(REAL)


Index("ix_prevision_station_instant", Prevision.station_code, Prevision.instant)


class Verdict(Base):
    """Une ligne de Verdict : le score d'un Modèle sur une case.

    Une case est le quadruplet (Station, variable, Anticipation, saison). Une case
    entière est absente de la table lorsque la Couverture est insuffisante — c'est
    ainsi que se matérialise le refus de conclure.
    """

    __tablename__ = "verdict"

    station_code: Mapped[str] = mapped_column(
        ForeignKey("station.code", ondelete="CASCADE"), primary_key=True
    )
    variable: Mapped[str] = mapped_column(String(16), primary_key=True)
    """« temperature » ou « pluie »."""

    anticipation: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    saison: Mapped[str] = mapped_column(String(12), primary_key=True)
    modele: Mapped[str] = mapped_column(String(48), primary_key=True)

    rang: Mapped[int] = mapped_column(SmallInteger)
    ecart_moyen: Mapped[float] = mapped_column(REAL)
    biais: Mapped[float | None] = mapped_column(REAL)
    fausses_alertes: Mapped[float | None] = mapped_column(REAL)
    pluies_manquees: Mapped[float | None] = mapped_column(REAL)
    ex_aequo: Mapped[bool] = mapped_column(Boolean)

    nb_heures: Mapped[int] = mapped_column(Integer)
    nb_jours: Mapped[int] = mapped_column(Integer)
    couverture: Mapped[float] = mapped_column(REAL)
    calcule_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))
