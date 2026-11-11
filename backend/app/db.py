"""Połączenie z PostGIS dla endpointów API (jedno połączenie na żądanie)."""

from collections.abc import Iterator

import psycopg
from fastapi import Depends, HTTPException
from psycopg.rows import dict_row

from app.config import Settings, get_settings


def get_connection(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Iterator[psycopg.Connection]:
    try:
        connection = psycopg.connect(**settings.database_connect_kwargs, row_factory=dict_row)
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="Baza danych jest niedostępna.") from error
    try:
        yield connection
    finally:
        connection.close()
