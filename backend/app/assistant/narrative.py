"""Concise narratives from verified tool rows; conversation scope is explicit."""

import re


def plain(text: str) -> str:
    return text.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


def detail_request(text: str) -> bool:
    text = plain(text)
    return bool(
        re.search(r"szczeg|wiecej inform|rozwin|omow|wyjasnij|dlaczego|skad", text)
        or re.fullmatch(r"\s*(tak|tak prosze|poprosze|wiecej|prosze)[.! ]*", text)
    )


def recommendation_request(text: str) -> bool:
    return bool(
        re.search(r"rekomend|zalec|popraw.*bezpieczen|zrobic.*bezpiecz|wdrozyc", plain(text))
    )


def number(value) -> str:
    return "brak danych" if value is None else f"{value:g}".replace(".", ",")


def ranking_text(rows: list[dict]) -> str:
    lines = ["Przejazdy z najwyższym priorytetem (WPO) według rankingu:"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. **Numer:** {row['numer']}, "
            f"**Dzielnica:** {row.get('dzielnica') or 'brak danych'}, "
            f"**Kategoria:** {row.get('kategoria') or 'brak danych'}, "
            f"**WPO:** {number(row.get('rps'))}"
        )
    lines += [
        "Wszystkie dane dotyczą przejazdów z kursami pasażerskimi w rozkładzie. "
        "WPO to priorytet do dalszej oceny, nie oznacza niebezpieczności.",
        f"Czy chcesz więcej szczegółów o tych {len(rows)} przejazdach?",
    ]
    return "\n\n".join(lines)


COMPONENT_NAMES = {
    "T": "ekspozycja",
    "P": "zabezpieczenia",
    "G": "geometria",
    "H": "historia zdarzeń",
}


def detail_text(rows: list[dict]) -> str:
    lines = [
        "Szczegóły wybranego przejazdu:"
        if len(rows) == 1
        else f"Szczegóły tych samych {len(rows)} przejazdów z poprzedniej analizy:"
    ]
    for i, row in enumerate(rows, 1):
        parts = row.get("skladniki", {})
        t = parts.get("T", {}).get("szczegoly", {})
        g = parts.get("G", {}).get("szczegoly", {})
        measured = t.get("vehicles_source") == "measured"
        vehicles = t.get("vehicles_per_day_measured" if measured else "vehicles_per_day_model")
        scores = "; ".join(
            f"{COMPONENT_NAMES[key]}: {number(parts.get(key, {}).get('wartosc'))}"
            for key in COMPONENT_NAMES
        )
        available = {
            k: c for k, c in parts.items() if c.get("wartosc") is not None and c.get("waga", 0) > 0
        }
        total_weight = sum(c["waga"] for c in available.values())
        explanation = ""
        if total_weight and row.get("rps") is not None:
            key = max(available, key=lambda k: available[k]["wartosc"] * available[k]["waga"])
            contribution = available[key]["wartosc"] * available[key]["waga"] / total_weight
            explanation = (
                f" Największy wkład do wyniku ma {COMPONENT_NAMES.get(key, key)} "
                f"— około {number(round(contribution, 1))} pkt WPO "
                "po uwzględnieniu wag dostępnych składników."
            )
        traffic_source = (
            "brak danych" if vehicles is None else "pomiar" if measured else "model z klasy drogi"
        )
        angle = "brak danych" if g.get("angle_deg") is None else number(g["angle_deg"]) + "°"
        lines.append(
            f"{i}. **{row['numer']} — {row.get('dzielnica') or 'brak dzielnicy'}**\n"
            f"WPO {number(row.get('rps'))}; kategoria {row.get('kategoria') or 'brak danych'}. "
            f"Pociągi pasażerskie / dzień roboczy (plan): "
            f"{number(row.get('pociagi_pasazerskie_dzien_roboczy_plan'))}. "
            f"Pojazdy / dobę: {number(vehicles)} ({traffic_source}). "
            f"Tory: {number(g.get('tracks'))}; kąt: {angle}.\n"
            f"Składniki (0–100): {scores}. "
            f"Kompletność składników: {number(row.get('kompletnosc_proc'))}%." + explanation
        )
    lines.append("Rozwiń wykresy i dane poniżej lub otwórz te same przejazdy na mapie.")
    return "\n\n".join(lines)


def recommendation_text(rows: list[dict]) -> str:
    lines = [
        "Propozycje działań do rozważenia podczas audytu — "
        "wymagają oceny w terenie i uzgodnienia z zarządcą:"
    ]
    for row in rows:
        parts = row.get("skladniki", {})
        t = parts.get("T", {}).get("szczegoly", {})
        g = parts.get("G", {}).get("szczegoly", {})
        actions = [
            "sprawdzić widoczność z dojazdów, oznakowanie "
            "i możliwość bezpiecznego opuszczenia torowiska"
        ]
        if row.get("kategoria") in ("D", "F"):
            actions.append(
                "przeanalizować adekwatność organizacji ruchu i zabezpieczeń "
                "dla tej kategorii przejazdu"
            )
        else:
            actions.append(
                "zweryfikować działanie istniejących zabezpieczeń i zachowania użytkowników"
            )
        if t.get("vehicles_source") == "model":
            actions.append(
                "wykonać pomiar ruchu drogowego, ponieważ obecna ekspozycja opiera się na modelu"
            )
        if g.get("tracks", 0) and g["tracks"] > 1:
            actions.append(
                "uwzględnić dłuższe przekraczanie wielotorowego przejazdu "
                "oraz ruch na kolejnych torach"
            )
        lines.append(f"**{row['numer']}**: " + "; ".join(actions) + ".")
    lines.append(
        "Te propozycje nie potwierdzają usterki ani nie przesądzają o przebudowie. "
        "Najpierw należy zweryfikować dane i warunki lokalne; "
        "sama zmiana WPO nie dowodzi poprawy bezpieczeństwa."
    )
    return "\n\n".join(lines)
