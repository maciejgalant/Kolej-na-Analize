"""Exact conversational intents; mixed factual questions always continue to data tools."""

import re
import unicodedata


def conversational_reply(message: str, attached: bool = False) -> str | None:
    text = unicodedata.normalize("NFKD", message.casefold().replace("ł", "l"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())
    if text in {"czesc", "hej", "hejka", "witaj", "dzien dobry", "dobry wieczor", "hello", "hi"}:
        return (
            "Cześć! Mogę wyjaśnić wynik wybranego przejazdu lub sprawdzić jakość jego danych. "
            "O co chcesz zapytać?"
            if attached
            else "Cześć! Chcesz porównać dwa przejazdy, sprawdzić jakość danych "
            "czy zobaczyć ranking dzielnicy?"
        )
    if text in {"dzieki", "dziekuje", "dziekuje bardzo", "super dzieki", "dzieki za pomoc"}:
        return "Proszę bardzo! Jeśli zechcesz, możemy przyjrzeć się kolejnemu przejazdowi."
    if text in {"do widzenia", "pa", "na razie", "dobranoc"}:
        return "Do zobaczenia! Wróć, gdy zechcesz przyjrzeć się kolejnym przejazdom."
    if text in {"co potrafisz", "co umiesz", "jak mozesz pomoc", "pomoc", "pomoz mi"}:
        return (
            "Mogę pokazać ranking przejazdów w Warszawie, porównać dwa przejazdy, wyjaśnić RPS "
            "i wskazać braki oraz modelowane dane. Wybierz przejazd na mapie albo użyj przycisku "
            "Porównaj przejazdy. Możesz też zapytać: Które przejazdy w Wawrze mają niepełne dane? "
            "RPS oznacza priorytet do dalszej oceny, a nie prawdopodobieństwo wypadku."
        )
    if text in {"jak sie masz", "co slychac"}:
        return "Jestem gotowy do pomocy przy analizie przejazdów. Od czego zaczynamy?"
    return None
