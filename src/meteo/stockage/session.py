"""Accès à la base."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from meteo.config import config
from meteo.stockage.tables import Base


@lru_cache
def moteur() -> Engine:
    return create_engine(config().dsn, pool_pre_ping=True)


@lru_cache
def _fabrique() -> sessionmaker[Session]:
    return sessionmaker(bind=moteur(), expire_on_commit=False)


@contextmanager
def session() -> Iterator[Session]:
    with _fabrique()() as s:
        yield s


def creer_schema() -> None:
    Base.metadata.create_all(moteur())
