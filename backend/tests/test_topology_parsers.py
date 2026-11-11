import io
import zipfile

import httpx
import pytest

from app.etl.bdot10k import find_member, iter_segments, near_any_point
from app.etl.prg import fetch_districts, parse_districts
from app.etl.remote_zip import open_remote_zip

# Skrócone prawdziwe odpowiedzi usług (struktura i kolejność osi jak w oryginale).
PRG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:ms="http://mapserver.gis.umn.edu/mapserver"
  xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:wfs="http://www.opengis.net/wfs/2.0">
<wfs:member><ms:A05_Granice_jednostek_ewidencyjnych gml:id="a.1">
  <gml:boundedBy><gml:Envelope><gml:lowerCorner>480000 630000</gml:lowerCorner>
  <gml:upperCorner>481000 631000</gml:upperCorner></gml:Envelope></gml:boundedBy>
  <ms:msGeometry><gml:Polygon gml:id="p1" srsName="urn:ogc:def:crs:EPSG::2180">
    <gml:exterior><gml:LinearRing><gml:posList srsDimension="2">480000 630000 480000 631000
      481000 631000 481000 630000 480000 630000</gml:posList></gml:LinearRing></gml:exterior>
    <gml:interior><gml:LinearRing><gml:posList srsDimension="2">480400 630400 480400 630600
      480600 630600 480600 630400 480400 630400</gml:posList></gml:LinearRing></gml:interior>
  </gml:Polygon></ms:msGeometry>
  <ms:JPT_KOD_JE>146511_8</ms:JPT_KOD_JE><ms:JPT_NAZWA_>Targówek - dzielnica</ms:JPT_NAZWA_>
</ms:A05_Granice_jednostek_ewidencyjnych></wfs:member>
<wfs:member><ms:A05_Granice_jednostek_ewidencyjnych gml:id="a.2">
  <ms:msGeometry><gml:Polygon gml:id="p2"><gml:exterior><gml:LinearRing>
    <gml:posList>490000 650000 490000 651000 491000 651000 490000 650000</gml:posList>
  </gml:LinearRing></gml:exterior></gml:Polygon></ms:msGeometry>
  <ms:JPT_KOD_JE>143403_1</ms:JPT_KOD_JE><ms:JPT_NAZWA_>Ząbki - gmina miejska</ms:JPT_NAZWA_>
</ms:A05_Granice_jednostek_ewidencyjnych></wfs:member>
</wfs:FeatureCollection>"""

BDOT_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<gml:FeatureCollection '
    'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:ot="urn:gugik:specyfikacje:gmlas:'
    'bazaDanychObiektowTopograficznych10k:2.0" gml:id="GUGiK_OT_SKTR_L">\n'
)


def bdot_feature(tag, local_id, pos_list, **attrs):
    fields = "".join(f"<ot:{k}>{v}</ot:{k}>" for k, v in attrs.items())
    return (
        f'<gml:featureMember><ot:{tag} gml:id="x_{local_id}"><ot:lokalnyId>{local_id}'
        f'</ot:lokalnyId>{fields}<ot:geometria><gml:Curve srsName="EPSG:2180"><gml:segments>'
        f"<gml:LineStringSegment><gml:posList>{pos_list}</gml:posList></gml:LineStringSegment>"
        f"</gml:segments></gml:Curve></ot:geometria></ot:{tag}></gml:featureMember>\n"
    )


def bdot_xml(*features):
    return (BDOT_HEAD + "".join(features) + "</gml:FeatureCollection>").encode()


def test_parse_districts_keeps_warsaw_and_swaps_axis_order():
    districts = parse_districts(PRG_XML)
    assert [(d.teryt, d.name) for d in districts] == [("146511_8", "Targówek")]
    wkt = districts[0].wkt
    assert wkt.startswith("MULTIPOLYGON(((630000 480000,631000 480000,")
    assert ",(630400 480400," in wkt  # otwór w poligonie


def test_fetch_districts_sends_bbox_in_north_east_order():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, text=PRG_XML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert len(fetch_districts(625500, 470500, 656500, 503500, client)) == 1
    assert seen["BBOX"] == "470500,625500,503500,656500,urn:ogc:def:crs:EPSG::2180"
    assert seen["TYPENAMES"] == "ms:A05_Granice_jednostek_ewidencyjnych"


def test_iter_segments_reads_attributes_and_east_north_coordinates():
    xml = bdot_xml(
        bdot_feature("OT_SKTR_L", "A1", "643091.89 489628.27 643121.75 489608.81",
                     polozenie="na powierzchni gruntu", rodzajPojazduSzynowego="kolej",
                     liczbaTorow="1", numerLinii="9"),
        bdot_feature("OT_SKTR_L", "A2", "1 1 1 1"),  # zdegenerowany: pomijany
        bdot_feature("OT_SKJZ_L", "B1", "0 0 5 5"),  # inna klasa obiektów
    )  # fmt: skip
    segments = list(iter_segments(io.BytesIO(xml), "OT_SKTR_L"))
    assert [s.local_id for s in segments] == ["A1"]
    assert segments[0].points == ((643091.89, 489628.27), (643121.75, 489608.81))
    assert segments[0].attributes["numerLinii"] == "9"
    assert segments[0].wkt == "LINESTRING(643091.89 489628.27,643121.75 489608.81)"


def test_near_any_point_uses_margin_around_segment_bbox():
    segment = next(
        iter_segments(io.BytesIO(bdot_xml(bdot_feature("OT_SKJZ_L", "B1", "0 0 100 0"))),
                      "OT_SKJZ_L")
    )  # fmt: skip
    assert near_any_point([(50.0, 80.0)], 100.0)(segment)
    assert not near_any_point([(50.0, 180.0)], 100.0)(segment)
    assert not near_any_point([], 100.0)(segment)


def test_find_member_requires_exactly_one_match():
    names = ["x/BDOT10k/PL__OT_SKTR_L.xml", "x/BDOT10k/PL__OT_SKJZ_L.xml"]
    assert find_member(names, "OT_SKTR_L.xml") == names[0]
    with pytest.raises(RuntimeError):
        find_member(names, "OT_BRAK.xml")


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pkg/BDOT10k/pkg__OT_BUBD_A.xml", b"x" * 300_000)
        archive.writestr(
            "pkg/BDOT10k/pkg__OT_SKTR_L.xml",
            bdot_xml(*[bdot_feature("OT_SKTR_L", f"T{i}", f"{i} 0 {i} 10") for i in range(500)]),
        )
    return buffer.getvalue()


def test_remote_zip_reads_one_member_with_range_requests():
    payload = _zip_bytes()
    fetched = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200, headers={"accept-ranges": "bytes", "content-length": str(len(payload)),
                              "last-modified": "Sat, 31 Oct 2026 13:29:03 GMT"}
            )  # fmt: skip
        start, end = (int(v) for v in request.headers["range"].removeprefix("bytes=").split("-"))
        fetched.append(end - start + 1)
        return httpx.Response(206, content=payload[start : end + 1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    archive, raw = open_remote_zip(client, "https://example.test/p.zip", buffer_size=4096)
    with archive.open(find_member(archive.namelist(), "OT_SKTR_L.xml")) as stream:
        assert len(list(iter_segments(stream, "OT_SKTR_L"))) == 500
    assert raw.last_modified.startswith("Sat, 31 Oct 2026")
    assert sum(fetched) < len(payload)  # nie pobrano całego archiwum


def test_remote_zip_rejects_server_without_range_support():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "10"})

    with pytest.raises(RuntimeError, match="zakres"):
        open_remote_zip(httpx.Client(transport=httpx.MockTransport(handler)), "https://e.test/z")
