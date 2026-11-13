import pytest

from app.analysis.rps import (
    CATEGORY_SCORE,
    EXPOSURE_REFERENCE,
    WEIGHTS,
    CrossingInputs,
    exposure_component,
    geometry_component,
    perturbed_weights,
    protection_component,
    score_crossings,
)

MAIN = "droga główna"
LOCAL = "droga lokalna"


def crossing(cid, category="B", trains=100.0, road=LOCAL, tracks=2, angle=90.0):
    return CrossingInputs(cid, category, trains, road, tracks, angle)


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert all(abs(sum(w.values()) - 1) < 1e-9 for w in perturbed_weights(0.2))
    assert len(perturbed_weights(0.2)) == 8


def test_exposure_is_log_scaled_and_capped():
    reference = exposure_component(400, "droga główna ruchu przyśpieszonego")
    assert reference.value == pytest.approx(100.0, abs=0.01)
    assert reference.status == "modelled"  # ruch drogowy z modelu klasy drogi
    assert reference.detail["exposure_product"] == EXPOSURE_REFERENCE
    assert exposure_component(4000, "droga główna ruchu przyśpieszonego").value == 100.0
    low = exposure_component(30, LOCAL)
    high = exposure_component(300, LOCAL)
    assert 0 < low.value < high.value < 100
    assert high.value - low.value == pytest.approx(100 / 7.079, abs=0.2)  # dekada ≈ 14 pkt


@pytest.mark.parametrize(
    ("trains", "road", "reason"),
    [
        (None, LOCAL, "rozkładowych"),
        (0, LOCAL, "towarowy"),  # zero kursów pasażerskich to nie zero ekspozycji
        (120, None, "jezdni"),
        (120, "nieznana klasa", "jezdni"),
    ],
)
def test_exposure_unknown_is_null_not_zero(trains, road, reason):
    component = exposure_component(trains, road)
    assert component.value is None
    assert component.status == "unknown"
    assert reason in component.detail["reason"]


def test_protection_follows_category_order():
    values = [protection_component(c).value for c in "ABCD"]
    assert values == sorted(values) and values[-1] == 100.0
    assert protection_component("F").status == "ok"
    for category in (None, "E", "X"):  # przejścia piesze nie mają oceny w tej metodzie
        assert protection_component(category).value is None
    assert set(CATEGORY_SCORE) == set("ABCDF")


def test_geometry_from_tracks_and_angle():
    assert geometry_component(1, 90).value == 0.0
    assert geometry_component(4, 20).value == 100.0
    assert geometry_component(2, 90).value == pytest.approx(24.0)  # 0,6·40
    assert geometry_component(1, 52.5).value == pytest.approx(20.0)  # 0,4·50
    assert geometry_component(2, None).value == 40.0
    assert geometry_component(2, 90).status == "modelled"
    assert geometry_component(None, 90).value is None
    assert geometry_component(0, 90).status == "unknown"


def test_score_is_weighted_mean_of_available_components():
    [score] = score_crossings([crossing(1, "D", 400, "droga główna ruchu przyśpieszonego", 4, 20)])
    assert score.rps == 100.0  # T, P, G = 100; H nieznane i pominięte
    assert score.completeness_pct == 90.0
    assert score.is_partial
    assert score.components["H"].status == "unknown"
    assert (score.rank, score.rank_best, score.rank_worst) == (1, 1, 1)


def test_missing_key_component_gives_no_score_and_no_rank():
    scores = {s.crossing_id: s for s in score_crossings(
        [crossing(1), crossing(2, trains=0), crossing(3, category="E"), crossing(4, road=None)]
    )}  # fmt: skip
    assert scores[1].rank == 1
    for cid in (2, 3, 4):
        assert scores[cid].rps is None
        assert (scores[cid].rank, scores[cid].rank_best, scores[cid].rank_worst) == (None,) * 3
    assert scores[2].components["P"].value == 30.0  # pozostałe składniki są zachowane
    assert scores[2].completeness_pct == 50.0


def test_missing_geometry_keeps_rank_with_lower_completeness():
    [score] = score_crossings([crossing(1, tracks=None)])
    assert score.rank == 1
    assert score.completeness_pct == 70.0
    expected = (0.4 * score.components["T"].value + 0.3 * 30.0) / 0.7
    assert score.rps == pytest.approx(expected, abs=0.01)


def test_ranking_order_ties_and_sensitivity_span():
    inputs = [
        crossing(10, "D", 200, MAIN, 2, 60),  # wysoki priorytet
        crossing(11, "A", 200, MAIN, 2, 60),  # ten sam ruch, lepsze zabezpieczenia
        crossing(12, "A", 200, MAIN, 2, 60),  # remis z 11: wygrywa niższy identyfikator
        crossing(13, "C", 30, LOCAL, 1, 90),
    ]
    scores = {s.crossing_id: s for s in score_crossings(inputs)}
    assert [scores[c].rank for c in (10, 11, 12, 13)] == [1, 2, 3, 4]
    assert scores[11].rps == scores[12].rps
    for score in scores.values():
        assert score.rank_best <= score.rank <= score.rank_worst
    assert (scores[10].rank_best, scores[10].rank_worst) == (1, 1)  # stabilny lider


def test_sensitivity_detects_unstable_neighbours():
    # 1: silna ekspozycja, słaby priorytet zabezpieczeń; 2: odwrotnie — wyniki zbliżone.
    a = crossing(1, "B", 380, "droga główna ruchu przyśpieszonego", 1, 90)
    b = crossing(2, "D", 12, "droga dojazdowa", 1, 90)
    scores = {s.crossing_id: s for s in score_crossings([a, b], sensitivity_step=0.2)}
    assert abs(scores[1].rps - scores[2].rps) < 6
    assert {scores[1].rank_best, scores[1].rank_worst} == {1, 2}
    stable = {s.crossing_id: s for s in score_crossings([a, b], sensitivity_step=0.0)}
    assert stable[1].rank_best == stable[1].rank_worst


def test_category_f_without_road_uses_internal_road_class():
    component = exposure_component(392, None, None, "F")
    assert component.detail["road_class"] == "droga wewnętrzna"
    assert component.detail["vehicles_per_day_model"] == 300
    assert "kategorii F" in component.detail["note"]
    assert exposure_component(392, None, None, "A").value is None
