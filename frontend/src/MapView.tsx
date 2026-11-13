import L from "leaflet";
import { useEffect, useRef, useState } from "react";

import type { CrossingFeature, DistrictFeature } from "./api";
import { crossingTitle } from "./labels";

const WARSAW_CENTER: L.LatLngTuple = [52.2297, 21.0122];

interface Props {
  districts: DistrictFeature[];
  crossings: CrossingFeature[];
  selectedDistrictId: number | null;
  selectedCrossingId: number | null;
  onSelectCrossing: (id: number) => void;
  loading: boolean;
  /** Zestaw demonstracyjny: podpis źródeł nie może wskazywać rzeczywistych rejestrów. */
  demo: boolean;
  /** Zmiana wartości wymusza przeliczenie rozmiaru mapy (np. po otwarciu panelu). */
  layoutKey: string;
}

function markerIcon(feature: CrossingFeature, selected: boolean): L.DivIcon {
  const p = feature.properties;
  const classes = [
    "marker",
    p.is_pedestrian ? "marker-ped" : "marker-road",
    p.verification_status === "verified" ? "" : "marker-unverified",
    selected ? "marker-selected" : "",
  ];
  const warning =
    p.warnings > 0
      ? '<span class="marker-warn" aria-hidden="true">!</span>'
      : "";
  return L.divIcon({
    className: "",
    html: `<span class="${classes.join(" ").trim()}">${p.category ?? "?"}${warning}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

export function MapView({
  districts,
  crossings,
  selectedDistrictId,
  selectedCrossingId,
  onSelectCrossing,
  loading,
  demo,
  layoutKey,
}: Props) {
  const [legendOpen, setLegendOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const districtLayer = useRef<L.GeoJSON | null>(null);
  const markerLayer = useRef<L.LayerGroup | null>(null);
  const onSelect = useRef(onSelectCrossing);
  onSelect.current = onSelectCrossing;

  useEffect(() => {
    if (!container.current) return;
    const instance = L.map(container.current, {
      center: WARSAW_CENTER,
      zoom: 11,
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instance);
    markerLayer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const control = map.current?.attributionControl;
    if (!control) return;
    const real = "przejazdy: UTK/GUGiK | granice, tory, drogi: GUGiK";
    const fake = "obiekty na mapie: dane demonstracyjne (fikcyjne)";
    control.removeAttribution(real).removeAttribution(fake);
    control.addAttribution(demo ? fake : real);
  }, [demo]);

  // Granice dzielnic; wybrana dzielnica jest wyróżniona i mapa się do niej dopasowuje.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    districtLayer.current?.remove();
    if (districts.length === 0) return;
    const layer = L.geoJSON(districts as unknown as GeoJSON.Feature[], {
      interactive: false,
      style: (feature) => {
        const active = feature?.id === selectedDistrictId;
        return {
          color: active ? "#174A7E" : "#526476",
          weight: active ? 3 : 1,
          fillColor: "#287BC1",
          fillOpacity: active ? 0.08 : 0,
        };
      },
    }).addTo(instance);
    districtLayer.current = layer;
    const target =
      selectedDistrictId === null
        ? layer.getBounds()
        : L.geoJSON(
            districts.filter(
              (d) => d.id === selectedDistrictId,
            ) as unknown as GeoJSON.Feature[],
          ).getBounds();
    if (target.isValid()) instance.fitBounds(target, { padding: [16, 16] });
  }, [districts, selectedDistrictId]);

  useEffect(() => {
    const layer = markerLayer.current;
    if (!layer) return;
    layer.clearLayers();
    for (const feature of crossings) {
      const [lon, lat] = feature.geometry.coordinates;
      const selected = feature.id === selectedCrossingId;
      L.marker([lat, lon], {
        icon: markerIcon(feature, selected),
        title: `${crossingTitle(feature.properties)}, kategoria ${feature.properties.category ?? "nieznana"}`,
        keyboard: true,
        zIndexOffset: selected ? 1000 : 0,
      })
        .on("click", () => onSelect.current(feature.id))
        .addTo(layer);
    }
  }, [crossings, selectedCrossingId]);

  useEffect(() => {
    const instance = map.current;
    const feature = crossings.find((c) => c.id === selectedCrossingId);
    if (!instance || !feature) return;
    const [lon, lat] = feature.geometry.coordinates;
    instance.setView([lat, lon], Math.max(instance.getZoom(), 15));
    // Tylko przy zmianie wyboru, nie przy każdej zmianie listy.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCrossingId]);

  // Po zmianie układu kolumn Leaflet musi poznać nowy rozmiar kontenera.
  useEffect(() => {
    const timer = window.setTimeout(() => map.current?.invalidateSize(), 260);
    return () => window.clearTimeout(timer);
  }, [layoutKey]);

  return (
    <div className="map-holder">
      <div
        ref={container}
        className="map"
        role="application"
        aria-label="Mapa przejazdów"
      />
      {loading && (
        <div className="map-loading" role="status">
          <span className="spinner" aria-hidden="true" />
          Wczytywanie mapy przejazdów…
        </div>
      )}
      <div className="legend-wrap">
        <button
          type="button"
          className="map-button"
          aria-expanded={legendOpen}
          onClick={() => setLegendOpen((value) => !value)}
        >
          {legendOpen ? "Ukryj legendę" : "Legenda"}
        </button>
        {legendOpen && (
          <div className="legend" aria-label="Legenda">
            <div>
              <span className="marker marker-road">B</span> przejazd drogowy
              (litera = kategoria)
            </div>
            <div>
              <span className="marker marker-ped">E</span> przejście dla
              pieszych
            </div>
            <div>
              <span className="marker marker-road marker-unverified">D</span>{" "}
              niezweryfikowany
            </div>
            <div>
              <span className="marker marker-road">
                C<span className="marker-warn">!</span>
              </span>{" "}
              ostrzeżenie o danych
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
