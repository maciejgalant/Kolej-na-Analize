"""Bezpieczne funkcje asystenta AI (RSA-013): tylko odczyt, tylko z tej listy.

Model językowy nie pisze zapytań SQL i nie ma dostępu do bazy. Może jedynie wybrać
jedną z poniższych funkcji i podać jej argumenty; argumenty są walidowane, a wynik
to mały słownik z danymi z ostatniego zakończonego przebiegu analizy.
"""

import difflib
from collections.abc import Callable
from typing import Any

import psycopg

from app.analysis import rps
from app.api.crossings import DISCLAIMER, LATEST_RUN_SQL
from app.assistant.insights import comparison, quality_summary

MAX_LIMIT = 15


class ToolError(ValueError):
    """Błąd argumentów; treść trafia do modelu, żeby mógł poprawić wywołanie."""


# Odmiana nazw dzielnic, której nie złapie samo podobieństwo napisów.
DISTRICT_FORMS = {
    "wawra": "Wawer", "wawrze": "Wawer",
    "woli": "Wola", "wole": "Wola",
    "włoch": "Włochy", "włochach": "Włochy",
    "bielan": "Bielany", "bielanach": "Bielany",
    "pragi-południe": "Praga-Południe", "pradze-południe": "Praga-Południe",
    "pragi-północ": "Praga-Północ", "pradze-północ": "Praga-Północ",
    "pragi południe": "Praga-Południe", "pragi północ": "Praga-Północ",
    "praga południe": "Praga-Południe", "praga północ": "Praga-Północ",
    "śródmieścia": "Śródmieście", "śródmieściu": "Śródmieście",
    "ochoty": "Ochota", "ochocie": "Ochota",
    "wesołej": "Wesoła",
}  # fmt: skip


def _plain(text: str) -> str:
    table = str.maketrans("ąćęłńóśźż", "acelnoszz")
    return " ".join(text.lower().replace("dzielnica", "").split()).translate(table)


def _district_id(conn: psycopg.Connection, name: str | None) -> tuple[int | None, str | None]:
    """Rozpoznaje dzielnicę także w odmianie („Targówka”, „na Woli”) i bez polskich znaków."""
    if name is None or not str(name).strip():
        return None, None
    rows = conn.execute("SELECT district_id, name FROM spatial.districts").fetchall()
    by_plain = {_plain(row["name"]): row for row in rows}
    wanted = " ".join(str(name).lower().replace("dzielnica", "").split())
    for prefix in ("na ", "w ", "we ", "dla ", "z ", "ze "):
        wanted = wanted.removeprefix(prefix)
    if wanted in DISTRICT_FORMS:
        wanted = DISTRICT_FORMS[wanted]
    key = _plain(wanted)
    if key in by_plain:
        return by_plain[key]["district_id"], by_plain[key]["name"]
    prefixed = [plain for plain in by_plain if plain.startswith(key)]
    close = difflib.get_close_matches(key, list(by_plain), n=2, cutoff=0.72)
    # Skrót pasujący do kilku dzielnic („Urs”, „Praga”) jest niejednoznaczny: nie zgadujemy.
    if len(prefixed) <= 1 and (
        len(close) == 1 or (len(close) == 2 and close[0][:4] != close[1][:4])
    ):
        return by_plain[close[0]]["district_id"], by_plain[close[0]]["name"]
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
    if len(rows) > 1:
        raise ToolError("Numer przejazdu jest niejednoznaczny w ewidencji. Wymaga weryfikacji.")
    return rows[0]


def _crossing_summary(conn: psycopg.Connection, crossing_id: int) -> dict:
    row = conn.execute(
        f"""
        SELECT c.crossing_id, c.name AS numer, c.category AS kategoria, d.name AS dzielnica,
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
    if row is None:
        raise ToolError("Nie ma przejazdu o takim identyfikatorze w obszarze analizy.")
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
                "waga": float(c["weight"]),
                "szczegoly": c["detail"],
            }
            for c in conn.execute(
                "SELECT component, value, status, weight, detail FROM analysis.components "
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
        SELECT c.crossing_id, s.rank AS pozycja, c.name AS numer, c.category AS kategoria,
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
    a, b = get_crossing(conn, number_a), get_crossing(conn, number_b)
    if a["crossing_id"] == b["crossing_id"]:
        raise ToolError("Wybierz dwa różne przejazdy do porównania.")
    return comparison(a, b)


def get_data_quality(
    conn: psycopg.Connection, district: str | None = None, number: Any = None, limit: Any = 5
) -> dict:
    if number is not None and district:
        raise ToolError("Podaj numer przejazdu albo dzielnicę, nie oba naraz.")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ToolError(f"limit musi być liczbą całkowitą w zakresie 1-{MAX_LIMIT}.")
    district_id, district_name = _district_id(conn, district)
    if number is not None:
        rows = [get_crossing(conn, number)]
    else:
        ids = conn.execute(
            f"""
            SELECT c.crossing_id FROM spatial.crossings c
            LEFT JOIN analysis.risk_scores s
                ON s.crossing_id = c.crossing_id AND s.run_id = ({LATEST_RUN_SQL})
            WHERE c.district_id IS NOT NULL AND c.verification_status = 'verified'
              AND c.category IS DISTINCT FROM 'E'
              AND (%(district)s::int IS NULL OR c.district_id = %(district)s)
            ORDER BY s.completeness_pct ASC NULLS FIRST,
              (SELECT count(*) FROM analysis.components p
               WHERE p.crossing_id = c.crossing_id AND p.run_id = s.run_id
                 AND p.status = 'modelled') DESC, c.crossing_id
            LIMIT %(limit)s
            """,
            {"district": district_id, "limit": limit},
        ).fetchall()
        rows = [_crossing_summary(conn, r["crossing_id"]) for r in ids]
    for row in rows:
        row["jakosc_danych"] = quality_summary(row)
        row.pop(
            "skladniki", None
        )  # diagnostics retain statuses without large raw geometry payloads
    return {
        "zakres": str(number) if number is not None else district_name or "cała Warszawa",
        "przejazdy": rows,
        "uwaga": "Lista do przeglądu danych: najpierw brak analizy lub najniższa kompletność, "
        "następnie więcej składników modelowanych. To nie ranking bezpieczeństwa ani pomiar "
        "wiarygodności. Przejścia kategorii E są poza rankingiem RPS z założenia. "
        "Kompletność opisuje dostępność składników, nie ich aktualność. "
        "Do potwierdzenia aktualności sprawdź okresy w źródłach.",
    }


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
            "T": "ekspozycja: planowe pociągi pasażerskie x pojazdy na dobę (pomiar ZDM, gdy "
            "punkt pomiarowy jest na ulicy przejazdu do 300 m; inaczej szacunek z klasy drogi)",
            "P": "zabezpieczenia: wynika z kategorii przejazdu, D (bez urządzeń) = 100, A = 15",
            "G": "geometria: liczba torów i kąt skrzyżowania; bez oceny widoczności",
            "H": "historia zdarzeń: brak danych dla wszystkich przejazdów",
        },
        "wagi": rps.WEIGHTS,
        "ograniczenia": [
            "Tylko pociągi pasażerskie z rozkładu; ruch towarowy nie jest ujęty.",
            "Ruch drogowy z pomiaru ZDM ma tylko kilka przejazdów; pozostałe mają szacunek "
            "z klasy drogi.",
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
    "get_data_quality": (
        get_data_quality,
        "Braki i jakość danych: kompletność RPS, modelowane składniki, źródło ruchu. "
        "Dla jednego numeru albo dzielnicy; bez argumentów dla Warszawy. "
        "Użyj przy pytaniach o niepełne dane, niepewność lub co należy zweryfikować.",
        _schema(
            {
                "district": {"type": "string"},
                "number": NUMBER,
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
            },
            [],
        ),
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


def get_attached_crossing(conn: psycopg.Connection, crossing_id: int) -> dict:
    """Resolve an explicit UI attachment using its database ID, not a model-supplied name."""
    return _crossing_summary(conn, crossing_id)
