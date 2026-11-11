import math

import httpx
import pytest

from app.etl.crossing_scan import Bbox, coarse_windows, scan_crossings
from app.etl.overpass import parse_overpass
from app.etl.symbols import find_blobs
from app.etl.utk_wms import UtkWmsClient, Window, WmsFeature, WmsRenderError, parse_feature_info
from tests.fake_wms import FakeWms

BBOX = Bbox(630000, 480000, 638000, 488000)

# Skrócona prawdziwa odpowiedź usługi (GetFeatureInfo, text/xml).
SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<FeatureCollection xmlns="http://www.intergraph.com/geomedia/gml"
    xmlns:gml="http://www.opengis.net/gml"><gml:featureMember>
<Layer Name="PKP_Polskie_Linie_Kolejowe"><Attribute Name="OGR_FID">3708</Attribute>
<Attribute Name="NAZWA">021 008 716</Attribute><Attribute Name="KATEGORIA">B</Attribute>
<Attribute Name="TEL_ST">+48 25 746 35 01</Attribute>
<Attribute Name="STAC_SZLAK">szlakowy</Attribute>
<Attribute Name="IDDE">PKP PLK WARSZAWA</Attribute></Layer></gml:featureMember>
<gml:featureMember><Layer Name="Warszawska_Kolej_Dojazdowa">
<Attribute Name="NAZWA">WK 0479615</Attribute><Attribute Name="KATEGORIA">c</Attribute>
<Attribute Name="STAC_SZLAK"></Attribute>
<Attribute Name="IDDE">Warszawska Kolej Dojazdowa sp. z o.o.</Attribute></Layer>
</gml:featureMember></FeatureCollection>"""


def feature(name: str, category: str = "D", layer: str = "PKP_Polskie_Linie_Kolejowe"):
    return WmsFeature(layer, name, category, "szlakowy", "PKP PLK WARSZAWA")


def test_parse_feature_info_reads_real_response_shape():
    parsed = parse_feature_info(SAMPLE_XML)
    assert [f.name for f in parsed] == ["021 008 716", "WK 0479615"]
    assert parsed[0].category_raw == "B"
    assert parsed[0].location_type == "szlakowy"
    assert parsed[1].category_raw == "c"
    assert parsed[1].key == "Warszawska_Kolej_Dojazdowa:WK 0479615"


def test_parse_feature_info_empty_collection():
    assert parse_feature_info('<FeatureCollection xmlns="x"/>') == []


def test_window_pixel_round_trip_and_axis_order():
    window = Window(630000, 480000, 512, 512)
    assert window.wms_bbox == "480000,630000,480512,630512"  # północ, wschód
    east, north = window.to_map(100, 200)
    assert window.to_pixel(east, north) == (100, 200)
    assert north == pytest.approx(480000 + 512 - 200.5)


def test_find_blobs_separates_symbols_and_marks_edge():
    fake = FakeWms([(feature("a"), 630100, 480100), (feature("b"), 630300, 480400)])
    blobs, width, _ = find_blobs(fake.get_map(Window(630000, 480000, 512, 512)))
    assert width == 512
    assert sorted((b.width, b.height) for b in blobs) == [(46, 25), (46, 25)]
    assert not any(b.touches_edge for b in blobs)
    edge = FakeWms([(feature("c"), 630005, 480100)])
    assert find_blobs(edge.get_map(Window(630000, 480000, 512, 512)))[0][0].touches_edge


def test_coarse_windows_cover_bbox_with_overlap():
    windows = list(coarse_windows(BBOX))
    assert len(windows) == 9
    assert max(w.e_min + w.size_m for w in windows) >= BBOX.e_max
    assert max(w.n_min + w.size_m for w in windows) >= BBOX.n_max


def test_scan_locates_crossings_within_two_metres():
    truth = {
        "001 000 100": (631234.0, 481777.0),
        "001 005 200": (634100.5, 486020.5),
        "002 000 300": (637800.0, 480300.0),
    }
    fake = FakeWms([(feature(name), e, n) for name, (e, n) in truth.items()])
    result = scan_crossings(fake, BBOX)
    assert {c.feature.name for c in result.crossings} == set(truth)
    for crossing in result.crossings:
        east, north = truth[crossing.feature.name]
        assert math.hypot(crossing.east - east, crossing.north - north) < 2.0
        assert not crossing.approximate
    assert result.unidentified == []


def test_scan_retries_when_centre_query_is_empty():
    fake = FakeWms([(feature("001 000 100"), 631234.0, 481777.0)], dead_centre=True)
    result = scan_crossings(fake, BBOX)
    assert [c.feature.name for c in result.crossings] == ["001 000 100"]


def test_scan_splits_merged_symbols_with_grid():
    # 30 m od siebie: symbole (46 px przy 1 m/px) zlewają się w jeden zlepek.
    fake = FakeWms(
        [(feature("001 000 100", "A"), 633000.0, 484000.0),
         (feature("001 000 130", "E"), 633030.0, 484000.0)]
    )  # fmt: skip
    result = scan_crossings(fake, BBOX)
    by_name = {c.feature.name: c for c in result.crossings}
    assert set(by_name) == {"001 000 100", "001 000 130"}
    assert all(c.approximate for c in by_name.values())
    assert abs(by_name["001 000 100"].east - 633000) < 12
    assert abs(by_name["001 000 130"].east - 633030) < 12


def test_scan_deduplicates_symbol_seen_in_overlapping_tiles_and_drops_outside():
    inside = (633900.0, 483900.0)  # w pasie nakładania się kafli
    outside = (638100.0, 484000.0)  # widoczny na kaflu, ale poza obszarem
    fake = FakeWms([(feature("in"), *inside), (feature("out"), *outside)])
    result = scan_crossings(fake, BBOX)
    assert [c.feature.name for c in result.crossings] == ["in"]
    assert fake.info_requests <= 4


def test_scan_reports_symbol_without_feature_info():
    class Mute(FakeWms):
        def get_feature_info(self, window, px, py):
            return []

    result = scan_crossings(Mute([(feature("x"), 633000.0, 484000.0)]), BBOX)
    assert result.crossings == []
    assert len(result.unidentified) == 1
    assert abs(result.unidentified[0][0] - 633000) < 2


def test_parse_overpass_keeps_only_relevant_tags():
    payload = {
        "elements": [
            {"type": "node", "id": 5, "lat": 52.2, "lon": 21.0,
             "tags": {"railway": "level_crossing", "crossing:barrier": "half", "name": "x"}},
            {"type": "way", "id": 9},
        ]
    }  # fmt: skip
    parsed = parse_overpass(payload)
    assert len(parsed) == 1
    assert parsed[0].tags == {"railway": "level_crossing", "crossing:barrier": "half"}


def test_scan_shifts_window_when_server_fails_for_exact_bbox():
    fake = FakeWms([(feature("001 000 100"), 631234.0, 481777.0)])
    first = scan_crossings(fake, BBOX)
    assert len(first.crossings) == 1
    # Zepsuj dokładnie te okna 1 m/px, których użył pierwszy przebieg.
    seed = first.crossings[0]

    class Recording(FakeWms):
        def get_map(self, window):
            if window.m_per_px <= 1 and not self.broken_windows:
                self.broken_windows.add((window.e_min, window.n_min, window.size_m))
            return super().get_map(window)

    flaky = Recording([(feature("001 000 100"), 631234.0, 481777.0)])
    result = scan_crossings(flaky, BBOX)
    assert len(flaky.broken_windows) == 1
    assert [c.feature.name for c in result.crossings] == ["001 000 100"]
    assert abs(result.crossings[0].east - seed.east) < 2


def test_scan_records_seed_when_fine_window_never_renders():
    fake = FakeWms([(feature("001 000 100"), 631234.0, 481777.0)])
    fake.fail_all_fine = True
    result = scan_crossings(fake, BBOX)
    assert result.crossings == []
    assert len(result.unidentified) == 1


def test_scan_aborts_when_coarse_tile_never_renders():
    class Broken(FakeWms):
        def get_map(self, window):
            from app.etl.utk_wms import WmsRenderError

            raise WmsRenderError("E_FAIL")

    with pytest.raises(RuntimeError, match="kafla przeglądu"):
        scan_crossings(Broken([]), BBOX)


def test_client_builds_wms_requests_and_detects_service_exception():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        if request.url.params["REQUEST"] == "GetFeatureInfo":
            return httpx.Response(200, text=SAMPLE_XML, headers={"content-type": "text/xml"})
        return httpx.Response(
            200, text="<ServiceExceptionReport/>", headers={"content-type": "text/xml"}
        )

    client = UtkWmsClient(delay_s=0, transport=httpx.MockTransport(handler))
    window = Window(630000, 480000, 512, 512)
    assert [f.name for f in client.get_feature_info(window, 10, 20)] == [
        "021 008 716",
        "WK 0479615",
    ]
    info = seen[0]
    assert info["BBOX"] == "480000,630000,480512,630512"
    assert (info["CRS"], info["I"], info["J"]) == ("EPSG:2180", "10", "20")
    assert "PKP_Polskie_Linie_Kolejowe" in info["QUERY_LAYERS"]
    with pytest.raises(WmsRenderError):
        client.get_map(window)
    assert client.requests_made == 2
    client.close()


def test_client_retries_on_http_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, text=SAMPLE_XML)

    client = UtkWmsClient(delay_s=0, transport=httpx.MockTransport(handler))
    assert len(client.get_feature_info(Window(630000, 480000, 512, 512), 1, 1)) == 2
    assert len(calls) == 3
