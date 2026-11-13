"""RailSafe Priority Score (RPS) — wersja eksperymentalna `rps-0.5-exp`.

RPS to autorski *priorytet do dalszej oceny*, a nie prawdopodobieństwo wypadku ani
urzędowa klasyfikacja przejazdu. Wagi i tabele poniżej są założeniami roboczymi,
niezwalidowanymi; każda zmiana wymaga nowej wersji metody.

    RPS = 0,40·T + 0,30·P + 0,20·G + 0,10·H      (składniki w skali 0–100)

T — ekspozycja: planowe pociągi pasażerskie na dobę × pojazdy na dobę, w skali
    logarytmicznej względem stałego poziomu odniesienia. Pojazdy: pomiar ZDM (APR), gdy
    punkt pomiarowy leży na ulicy przejazdu blisko niego, w pozostałych przypadkach
    szacunek z klasy drogi.
P — zabezpieczenia: wynika z kategorii przejazdu (mniej urządzeń = wyższy priorytet).
G — geometria: liczba torów i kąt skrzyżowania (przybliżenie; brak danych o widoczności).
H — historia zdarzeń: brak danych, status `unknown`.

Moduł zawiera wyłącznie czyste funkcje, bez dostępu do bazy.
"""

import math
from dataclasses import dataclass, field

METHOD_VERSION = "rps-0.5-exp"
WEIGHTS: dict[str, float] = {"T": 0.40, "P": 0.30, "G": 0.20, "H": 0.10}
# Bez tych składników obiekt nie dostaje pozycji w rankingu.
KEY_COMPONENTS = ("T", "P")

# Szacowane natężenie ruchu drogowego [pojazdy/dobę] według klasy drogi z BDOT10k.
# ZAŁOŻENIE robocze dla przejazdów bez pomiaru ZDM (APR) na ulicy przejazdu.
# Wartości wymagają kalibracji (porównanie z pomiarami: reports/DATA_AUDIT_road.md).
INTERNAL_ROAD = "droga wewnętrzna"
ROAD_CLASS_VEHICLES: dict[str, int] = {
    "droga wewnętrzna": 300,
    "droga dojazdowa": 800,
    "droga lokalna": 2500,
    "droga zbiorcza": 8000,
    "droga główna": 18000,
    "droga główna ruchu przyśpieszonego": 30000,
}
# Poziom odniesienia ekspozycji: 400 pociągów/dobę × 30 000 pojazdów/dobę = T 100.
EXPOSURE_REFERENCE = 400 * 30000

# Priorytet wynikający z kategorii (0–100). ZAŁOŻENIE robocze.
CATEGORY_SCORE: dict[str, int] = {
    "A": 15,  # ruch kierowany przez pracowników kolei
    "B": 30,  # samoczynna sygnalizacja świetlna z rogatkami
    "C": 55,  # samoczynna sygnalizacja świetlna bez rogatek
    "D": 100,  # bez urządzeń zabezpieczenia ruchu
    "F": 60,  # droga wewnętrzna; wyposażenie zależne od umowy z zarządcą
}
TRACKS_SCORE = {1: 0.0, 2: 40.0, 3: 70.0}  # 4 i więcej torów: 100
ANGLE_FULL_SCORE_DEG = 30.0
ANGLE_ZERO_SCORE_DEG = 75.0
G_TRACKS_SHARE = 0.6


@dataclass(frozen=True)
class CrossingInputs:
    crossing_id: int
    category: str | None
    # None = brak danych rozkładowych; 0 = brak kursów pasażerskich (ruch łączny nieznany)
    trains_weekday: float | None
    road_class: str | None
    tracks: int | None
    angle_deg: float | None  # kąt ostry między osią drogi i toru, 0–90
    road_distance_m: float | None = None  # odległość punktu od przyjętej jezdni
    vehicles_measured: int | None = None  # średnia dobowa z pomiaru ZDM (typ 'direct')
    measurement: dict | None = None  # pochodzenie pomiaru: punkt, ulica, odległość, okres


@dataclass(frozen=True)
class Component:
    value: float | None
    status: str  # ok | modelled | unknown
    detail: dict = field(default_factory=dict)


@dataclass
class Score:
    crossing_id: int
    components: dict[str, Component]
    rps: float | None = None
    completeness_pct: float = 0.0
    rank: int | None = None
    rank_best: int | None = None
    rank_worst: int | None = None

    @property
    def is_partial(self) -> bool:
        return self.completeness_pct < 100.0


def exposure_component(
    trains_weekday: float | None,
    road_class: str | None,
    road_distance_m: float | None = None,
    category: str | None = None,
    vehicles_measured: int | None = None,
    measurement: dict | None = None,
) -> Component:
    from_category = road_class is None and category == "F"
    if from_category:
        road_class = INTERNAL_ROAD  # kategoria F z definicji leży na drodze wewnętrznej
    model = ROAD_CLASS_VEHICLES.get(road_class or "")
    detail = {"trains_per_day": trains_weekday, "road_class": road_class,
              "vehicles_per_day_model": model}  # fmt: skip
    vehicles = model
    if vehicles_measured:
        vehicles = vehicles_measured
        detail["vehicles_per_day_measured"] = vehicles_measured
        detail["vehicles_source"] = "measured"
        if measurement:
            detail["measurement"] = measurement
    else:
        detail["vehicles_source"] = "model"
    if road_distance_m is not None:
        detail["road_distance_m"] = road_distance_m
        if road_distance_m > 15:
            detail["note"] = "jezdnia przecinająca tor, z rozszerzonego promienia (15–30 m)"
    if from_category:
        detail["note"] = "brak jezdni w danych; klasa drogi przyjęta z kategorii F"
    if trains_weekday is None:
        return Component(None, "unknown", detail | {"reason": "brak danych rozkładowych"})
    if trains_weekday <= 0:
        return Component(
            None, "unknown",
            detail | {"reason": "brak kursów pasażerskich; ruch towarowy i manewrowy nieznany"},
        )  # fmt: skip
    if vehicles is None:
        return Component(None, "unknown", detail | {"reason": "brak jezdni lub klasy drogi"})
    product = trains_weekday * vehicles
    value = 100.0 * math.log10(1 + product) / math.log10(1 + EXPOSURE_REFERENCE)
    # Planowe pociągi to dane źródłowe; z pomiarem ruchu drogowego cały składnik nie jest
    # już szacunkiem.
    return Component(
        round(min(100.0, value), 2), "ok" if vehicles_measured else "modelled",
        detail | {"exposure_product": round(product), "reference": EXPOSURE_REFERENCE},
    )  # fmt: skip


def protection_component(category: str | None) -> Component:
    if category not in CATEGORY_SCORE:
        return Component(None, "unknown", {"category": category})
    return Component(float(CATEGORY_SCORE[category]), "ok", {"category": category})


def geometry_component(tracks: int | None, angle_deg: float | None) -> Component:
    detail = {"tracks": tracks, "angle_deg": None if angle_deg is None else round(angle_deg, 1)}
    if not tracks or tracks < 1:
        return Component(None, "unknown", detail | {"reason": "brak torów w danych"})
    tracks_score = TRACKS_SCORE.get(tracks, 100.0)
    if angle_deg is None:
        return Component(round(tracks_score, 2), "modelled",
                         detail | {"note": "bez kąta skrzyżowania"})  # fmt: skip
    span = ANGLE_ZERO_SCORE_DEG - ANGLE_FULL_SCORE_DEG
    angle_score = 100.0 * min(1.0, max(0.0, (ANGLE_ZERO_SCORE_DEG - angle_deg) / span))
    value = G_TRACKS_SHARE * tracks_score + (1 - G_TRACKS_SHARE) * angle_score
    return Component(round(value, 2), "modelled", detail)


def history_component() -> Component:
    return Component(None, "unknown", {"reason": "brak danych o zdarzeniach"})


def _weighted(components: dict[str, Component], weights: dict[str, float]) -> float | None:
    """Średnia ważona po dostępnych składnikach; None, gdy brakuje kluczowego."""
    if any(components[key].value is None for key in KEY_COMPONENTS):
        return None
    available = {k: c.value for k, c in components.items() if c.value is not None}
    total = sum(weights[k] for k in available)
    return sum(weights[k] * v for k, v in available.items()) / total


def _ranks(values: dict[int, float]) -> dict[int, int]:
    """Pozycje od 1; remisy rozstrzyga identyfikator, żeby wynik był powtarzalny."""
    ordered = sorted(values, key=lambda cid: (-values[cid], cid))
    return {cid: position for position, cid in enumerate(ordered, start=1)}


def perturbed_weights(step: float) -> list[dict[str, float]]:
    """Każda waga osobno zmieniona o ±step (względnie), po czym wagi są normalizowane."""
    variants = []
    for key in WEIGHTS:
        for factor in (1 - step, 1 + step):
            changed = dict(WEIGHTS) | {key: WEIGHTS[key] * factor}
            total = sum(changed.values())
            variants.append({k: v / total for k, v in changed.items()})
    return variants


def score_crossings(inputs: list[CrossingInputs], sensitivity_step: float = 0.2) -> list[Score]:
    scores = []
    for item in inputs:
        components = {
            "T": exposure_component(
                item.trains_weekday,
                item.road_class,
                item.road_distance_m,
                item.category,
                item.vehicles_measured,
                item.measurement,
            ),
            "P": protection_component(item.category),
            "G": geometry_component(item.tracks, item.angle_deg),
            "H": history_component(),
        }
        rps = _weighted(components, WEIGHTS)
        completeness = 100.0 * sum(WEIGHTS[k] for k, c in components.items() if c.value is not None)
        scores.append(
            Score(item.crossing_id, components, None if rps is None else round(rps, 2),
                  round(completeness, 1))
        )  # fmt: skip

    ranked = {s.crossing_id: s.rps for s in scores if s.rps is not None}
    base = _ranks(ranked)
    spans: dict[int, list[int]] = {cid: [position] for cid, position in base.items()}
    by_id = {s.crossing_id: s for s in scores}
    for weights in perturbed_weights(sensitivity_step):
        variant = {cid: _weighted(by_id[cid].components, weights) for cid in ranked}
        for cid, position in _ranks(variant).items():
            spans[cid].append(position)
    for score in scores:
        if score.crossing_id in base:
            score.rank = base[score.crossing_id]
            score.rank_best = min(spans[score.crossing_id])
            score.rank_worst = max(spans[score.crossing_id])
    return scores
