"""Deterministic comparisons and data diagnostics; no model-generated metrics."""

from app.analysis.rps import WEIGHTS

COMPONENT_NAMES = {"T": "Ekspozycja", "P": "Zabezpieczenia", "G": "Geometria", "H": "Historia"}


def quality_summary(row: dict) -> dict:
    components = row.get("skladniki", {})
    missing = [k for k in WEIGHTS if components.get(k, {}).get("wartosc") is None]
    modelled = [k for k, c in components.items() if c.get("status") == "modelled"]
    traffic = components.get("T", {}).get("szczegoly", {})
    measured = traffic.get("vehicles_source") == "measured"
    vehicles = traffic.get("vehicles_per_day_measured" if measured else "vehicles_per_day_model")
    traffic_source = "brak danych" if vehicles is None else "pomiar" if measured else "model"
    return {
        "kompletnosc_proc": row.get("kompletnosc_proc"),
        "brakujace_skladniki": missing,
        "modelowane_skladniki": modelled,
        "ruch_drogowy": traffic_source,
        "okres_pomiaru": traffic.get("measurement") if measured and vehicles is not None else None,
        "brak_analizy": not bool(components),
        "poza_rankingiem": row.get("pozycja") is None,
        "uwaga": "Kompletność to dostępność składników WPO, nie pewność ani ocena bezpieczeństwa. "
        "Brak danych nie oznacza braku zagrożeń. Ruch kolejowy obejmuje plan pasażerski.",
    }


def comparison(a: dict, b: dict) -> dict:
    """A minus B. Contributions use the same available-weight normalization as WPO."""

    def total_weight(row):
        return sum(
            c.get("waga", WEIGHTS[k])
            for k, c in row.get("skladniki", {}).items()
            if k in WEIGHTS and c.get("wartosc") is not None
        )

    wa, wb = total_weight(a), total_weight(b)
    rows = []
    for key, label in COMPONENT_NAMES.items():
        ca, cb = a.get("skladniki", {}).get(key, {}), b.get("skladniki", {}).get(key, {})
        va, vb = ca.get("wartosc"), cb.get("wartosc")
        rows.append(
            {
                "skladnik": label,
                "a": va,
                "b": vb,
                "status_a": ca.get("status", "unknown"),
                "status_b": cb.get("status", "unknown"),
                "roznica_a_minus_b": round(va - vb, 2)
                if va is not None and vb is not None
                else None,
                "wklad_do_rps_a": round(va * ca.get("waga", WEIGHTS[key]) / wa, 2)
                if va is not None and wa
                else None,
                "wklad_do_rps_b": round(vb * cb.get("waga", WEIGHTS[key]) / wb, 2)
                if vb is not None and wb
                else None,
            }
        )
    comparable = all(a.get(k) is not None and b.get(k) is not None for k in ("rps", "pozycja"))
    return {
        "a": a,
        "b": b,
        "skladniki_porownania": rows,
        "roznica_rps_a_minus_b": round(a["rps"] - b["rps"], 2) if comparable else None,
        "oba_w_rankingu": comparable,
        "jakosc_a": quality_summary(a),
        "jakosc_b": quality_summary(b),
        "uwaga": "Różnica to A minus B. Wkłady uwzględniają dostępne wagi osobno dla każdego "
        "przejazdu. Różne braki danych ograniczają porównywalność; nie są zerowymi wynikami. "
        "Wyższy WPO to priorytet do dalszej oceny, nie prawdopodobieństwo wypadku.",
    }
