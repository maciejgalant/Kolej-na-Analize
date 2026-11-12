"""Bezpieczne funkcje asystenta AI (RSA-013): tylko odczyt, tylko z tej listy.

Model językowy nie pisze zapytań SQL i nie ma dostępu do bazy. Może jedynie wybrać
jedną z poniższych funkcji i podać jej argumenty; argumenty są walidowane, a wynik
to mały słownik z danymi z ostatniego zakończonego przebiegu analizy.
"""

from collections.abc import Callable
from typing import Any

import psycopg

from app.analysis import rps
from app.api.crossings import DISCLAIMER, LATEST_RUN_SQL

MAX_LIMIT = 15


class ToolError(ValueError):
    """Błąd argumentów; treść trafia do modelu, żeby mógł poprawić wywołanie."""


def _district_id(conn: psycopg.Connection, name: str | None) -> tuple[int | None, str | None]:
    if name is None or not str(name).strip():
        return None, None
    wanted = str(name).strip().lower()
    rows = conn.execute("SELECT district_id, name FROM spatial.districts").fetchall()
    for row in rows:
        if row["name"].lower() == wanted:
            return row["district_id"], row["name"]
    close = [row for row in rows if wanted in row["name"].lower()]
    if len(close) == 1:
        return close[0]["district_id"], close[0]["name"]
    raise ToolError(
        f"Nie ma dzielnicy '{name}'. Dostępne: " + ", ".join(sorted(r["name"] for r in rows))
    )


def _find_crossing(conn: psycopg.Connection, number: Any) -> dict:
    wanted = "".join(str(number or "").split()).upper()
    if not wanted:
        raise ToolError("Podaj numer przejazdu, np. '021 003 504'.")
    rows = conn.execute(
        "SELECT crossing_id, name FROM spatial.crossings "
        "WHERE district_id IS NOT NULL AND upper(replace(name, ' ', '')) = %s",
        (wanted,),
    ).fetchall()
    if not rows:
        raise ToolError(f"Nie ma w ewidencji przejazdu o numerze '{number}'.")
    return rows[0]


def _crossing_summary(conn: psycopg.Connection, crossing_id: int) -> dict:
    row = conn.execute(
        f"""
        SELECT c.name AS numer, c.category AS kategoria, d.name AS dzielnica,
               c.verification_status AS status_weryfikacji,
               (SELECT round(avg(f.train_count))::int FROM rail.crossing_flow f
                 WHERE f.crossing_id = c.crossing_id AND f.evidence_type = 'planned'
                   AND extract(isodow FROM f.period_start AT TIME ZONE 'Europe/Warsaw') < 6
               ) AS pociagi_pasazerskie_dzien_roboczy_plan,
               s.rank AS pozycja, s.rps::float AS rps, s.rank_best AS pozycja_najlepsza,
               s.rank_worst AS pozycja_najgorsza,
               s.completeness_pct::float AS kompletnosc_proc, s.run_id
        FROM spatial.crossings c
        JOIN spatial.districts d USING (district_id)
        LEFT JOIN analysis.risk_scores s
               ON s.crossing_id = c.crossing_id AND s.run_id = ({LATEST_RUN_SQL})
        WHERE c.crossing_id = %s
        """,
        (crossing_id,),
    ).fetchone()
    run_id = row.pop("run_id")
    row["przejscie_dla_pieszych_poza_rankingiem"] = row["kategoria"] == "E"
    row["ulice"] = [
        r["road_name"]
        for r in conn.execute(
            "SELECT DISTINCT r.road_name FROM spatial.crossing_road_segments l "
            "JOIN spatial.road_segments r USING (segment_id) "
            "WHERE l.crossing_id = %s AND r.road_name IS NOT NULL ORDER BY 1",
            (crossing_id,),
        )
    ]
    if run_id is not None:
        row["skladniki"] = {
            c["component"]: {
                "wartosc": None if c["value"] is None else float(c["value"]),
                "status": c["status"],
                "szczegoly": c["detail"],
            }
            for c in conn.execute(
                "SELECT component, value, status, detail FROM analysis.components "
                "WHERE run_id = %s AND crossing_id = %s",
                (run_id, crossing_id),
            )
        }
    row["ostrzezenia"] = [
        f["message"] or f["code"]
        for f in conn.execute(
            "SELECT code, message FROM system.quality_flags WHERE entity_schema = 'spatial' "
            "AND entity_table = 'crossings' AND entity_id = %s AND resolved_at IS NULL "
            "AND severity <> 'info'",
            (str(crossing_id),),
        )
    ]
    return row


def get_ranking(conn: psycopg.Connection, district: str | None = None, limit: Any = 5) -> dict:
    try:
        limit = int(limit)
    except (TypeError, ValueError) as error:
        raise ToolError("limit musi być liczbą całkowitą.") from error
    if not 1 <= limit <= MAX_LIMIT:
        raise ToolError(f"limit musi być w zakresie 1–{MAX_LIMIT}.")
    district_id, district_name = _district_id(conn, district)
    rows = conn.execute(
        f"""
        SELECT s.rank AS pozycja, c.name AS numer, c.category AS kategoria,
               d.name AS dzielnica, s.rps::float AS rps,
               s.rank_best AS pozycja_najlepsza, s.rank_worst AS pozycja_najgorsza,
               (SELECT round(avg(f.train_count))::int FROM rail.crossing_flow f
                 WHERE f.crossing_id = c.crossing_id AND f.evidence_type = 'planned'
                   AND extract(isodow FROM f.period_start AT TIME ZONE 'Europe/Warsaw') < 6
               ) AS pociagi_dzien_roboczy_plan
        FROM analysis.risk_scores s
        JOIN spatial.crossings c USING (crossing_id)
        JOIN spatial.districts d USING (district_id)
        WHERE s.run_id = ({LATEST_RUN_SQL}) AND s.rank IS NOT NULL
          AND (%(district)s::int IS NULL OR c.district_id = %(district)s)
        ORDER BY s.rank LIMIT %(limit)s
        """,
        {"district": district_id, "limit": limit},
    ).fetchall()
    unranked = conn.execute(
        f"""
        SELECT count(*) AS n FROM analysis.risk_scores s
        JOIN spatial.crossings c USING (crossing_id)
        WHERE s.run_id = ({LATEST_RUN_SQL}) AND s.rank IS NULL
          AND (%(district)s::int IS NULL OR c.district_id = %(district)s)
        """,
        {"district": district_id},
    ).fetchone()["n"]
    return {
        "zakres": district_name or "cała Warszawa",
        "pozycje_dotycza_calej_warszawy": True,
        "ranking": rows,
        "przejazdy_bez_pozycji_brak_danych_o_ruchu": unranked,
        "uwaga": "Ranking obejmuje tylko przejazdy drogowe z kursami pasażerskimi w rozkładzie.",
    }


def get_crossing(conn: psycopg.Connection, number: Any = None) -> dict:
    return _crossing_summary(conn, _find_crossing(conn, number)["crossing_id"])


def compare_crossings(conn: psycopg.Connection, number_a: Any = None, number_b: Any = None) -> dict:
    return {"a": get_crossing(conn, number_a), "b": get_crossing(conn, number_b)}


def list_districts(conn: psycopg.Connection) -> dict:
    rows = conn.execute(
        f"""
        SELECT d.name AS dzielnica,
               count(c.*) FILTER (WHERE c.category IS DISTINCT FROM 'E') AS przejazdy_drogowe,
               count(c.*) FILTER (WHERE c.category = 'E') AS przejscia_dla_pieszych,
               count(s.*) FILTER (WHERE s.rank IS NOT NULL) AS przejazdy_w_rankingu,
               min(s.rank) AS najwyzsza_pozycja
        FROM spatial.districts d
        LEFT JOIN spatial.crossings c
               ON c.district_id = d.district_id AND c.verification_status = 'verified'
        LEFT JOIN analysis.risk_scores s
               ON s.crossing_id = c.crossing_id AND s.run_id = ({LATEST_RUN_SQL})
        GROUP BY d.name HAVING count(c.*) > 0 ORDER BY d.name
        """
    ).fetchall()
    return {"dzielnice_z_przejazdami": rows}


def get_method(conn: psycopg.Connection) -> dict:
    run = conn.execute(
        f"""
        SELECT run_id, method_version,
               to_char(period_start AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD') AS okres_od,
               to_char(period_end AT TIME ZONE 'Europe/Warsaw' - interval '1 day', 'YYYY-MM-DD')
                   AS okres_do
        FROM analysis.runs WHERE run_id = ({LATEST_RUN_SQL})
        """
    ).fetchone()
    return {
        "przebieg": run,
        "wzor": "RPS = 0,40*T + 0,30*P + 0,20*G + 0,10*H (średnia po dostępnych składnikach)",
        "skladniki": {
            "T": "ekspozycja: planowe pociągi pasażerskie x szacowane pojazdy (z klasy drogi)",
            "P": "zabezpieczenia: wynika z kategorii przejazdu, D (bez urządzeń) = 100, A = 15",
            "G": "geometria: liczba torów i kąt skrzyżowania; bez oceny widoczności",
            "H": "historia zdarzeń: brak danych dla wszystkich przejazdów",
        },
        "wagi": rps.WEIGHTS,
        "ograniczenia": [
            "Tylko pociągi pasażerskie z rozkładu; ruch towarowy nie jest ujęty.",
            "Ruch drogowy to szacunek z klasy drogi, nie pomiar.",
            "Przejścia dla pieszych (kategoria E) są poza rankingiem.",
            "Wagi i tabele punktowe są eksperymentalne i niezwalidowane.",
        ],
        "zastrzezenie": DISCLAIMER,
    }


def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


NUMBER = {"type": "string", "description": "Numer przejazdu z ewidencji, np. '021 003 504'."}
REGISTRY: dict[str, tuple[Callable[..., dict], str, dict]] = {
    "get_ranking": (
        get_ranking,
        "Ranking przejazdów drogowych według priorytetu RPS. Opcjonalnie tylko jedna dzielnica.",
        _schema(
            {
                "district": {"type": "string", "description": "Nazwa dzielnicy, np. 'Wola'."},
                "limit": {"type": "integer", "description": f"Liczba pozycji, 1–{MAX_LIMIT}."},
            },
            [],
        ),
    ),
    "get_crossing": (
        get_crossing,
        "Szczegóły jednego przejazdu: kategoria, dzielnica, pociągi, RPS, składniki, ostrzeżenia.",
        _schema({"number": NUMBER}, ["number"]),
    ),
    "compare_crossings": (
        compare_crossings,
        "Porównanie dwóch przejazdów po numerach.",
        _schema({"number_a": NUMBER, "number_b": NUMBER}, ["number_a", "number_b"]),
    ),
    "list_districts": (
        list_districts,
        "Dzielnice z liczbą przejazdów, przejść i najwyższą pozycją w rankingu.",
        _schema({}, []),
    ),
    "get_method": (
        get_method,
        "Opis metody RPS: wzór, składniki, wagi, okres danych i ograniczenia.",
        _schema({}, []),
    ),
}

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": name, "description": text, "parameters": schema}}
    for name, (_function, text, schema) in REGISTRY.items()
]


def call_tool(conn: psycopg.Connection, name: str, arguments: Any) -> dict:
    """Wykonuje funkcję z listy; nieznana nazwa lub złe argumenty dają ToolError."""
    if name not in REGISTRY:
        raise ToolError(f"Nieznana funkcja '{name}'. Dostępne: {', '.join(REGISTRY)}.")
    function, _text, schema = REGISTRY[name]
    if not isinstance(arguments, dict):
        raise ToolError("Argumenty muszą być obiektem JSON.")
    unknown = set(arguments) - set(schema["properties"])
    if unknown:
        raise ToolError(f"Nieznane argumenty: {sorted(unknown)}.")
    missing = [key for key in schema["required"] if arguments.get(key) in (None, "")]
    if missing:
        raise ToolError(f"Brakuje argumentów: {missing}.")
    return function(conn, **arguments)
