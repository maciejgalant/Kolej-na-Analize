import L from "leaflet";
import { useEffect, useRef, useState } from "react";

import type { Category, CrossingFeature, DistrictFeature } from "./api";
import { BASEMAPS, type BasemapId, storeBasemap, storedBasemap } from "./basemaps";
import { CategoryPin } from "./CategoryPin";
import { CATEGORY_DESCRIPTION, crossingTitle } from "./labels";
import { categoryLabel, pinHtml } from "./pictograms";

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
  const size = selected ? 40 : 32;
  return L.divIcon({
    className: "",
    html: pinHtml({
      category: p.category,
      verified: p.verification_status === "verified",
      warning: p.warnings > 0,
      selected,
      size,
    }),
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function markerLabel(feature: CrossingFeature): string {
  const p = feature.properties;
  const parts = [p.street, crossingTitle(p), categoryLabel(p.category)];
  if (p.rank !== null) parts.push(`pozycja ${p.rank} w rankingu`);
  return parts.filter(Boolean).join(", ");
}

const LEGEND_ORDER: Category[] = ["A", "B", "C", "D", "F", "E"];

function districtStyle(active: boolean, basemap: BasemapId): L.PathOptions {
  if (basemap === "ortho")
    // na zdjęciu lotniczym ciemne linie giną: jasna granica, wybrana dzielnica żółta
    return {
      color: active ? "#ffd84d" : "#ffffff",
      weight: active ? 3 : 1.5,
      opacity: 0.9,
      fillOpacity: 0,
    };
  return {
    color: active ? "#174A7E" : "#526476",
    weight: active ? 3 : 1,
    fillColor: "#287BC1",
    fillOpacity: active ? 0.08 : 0,
  };
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
  const [basemap, setBasemap] = useState<BasemapId>(storedBasemap);
  const tileLayer = useRef<L.TileLayer | null>(null);
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
    markerLayer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  // Podkład: wymiana warstwy kafli bez przebudowy mapy; wybór zapamiętany w przeglądarce.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    tileLayer.current?.remove();
    const definition = BASEMAPS.find((b) => b.id === basemap) ?? BASEMAPS[0];
    tileLayer.current = definition.create().addTo(instance);
    tileLayer.current.bringToBack();
    storeBasemap(basemap);
  }, [basemap]);

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
      style: (feature) =>
        districtStyle(feature?.id === selectedDistrictId, basemap),
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
    // Zmiana podkładu zmienia tylko styl granic; dopasowanie widoku zostaje bez zmian.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [districts, selectedDistrictId]);

  useEffect(() => {
    districtLayer.current?.setStyle((feature) =>
      districtStyle(feature?.id === selectedDistrictId, basemap),
    );
  }, [basemap, selectedDistrictId]);

  useEffect(() => {
    const layer = markerLayer.current;
    if (!layer) return;
    layer.clearLayers();
    for (const feature of crossings) {
      const [lon, lat] = feature.geometry.coordinates;
      const selected = feature.id === selectedCrossingId;
      const label = markerLabel(feature);
      const marker = L.marker([lat, lon], {
        icon: markerIcon(feature, selected),
        alt: label,
        keyboard: true,
        zIndexOffset: selected ? 1000 : 0,
        riseOnHover: true,
      })
        .bindTooltip(label, { direction: "top", offset: [0, -16] })
        .on("click", () => onSelect.current(feature.id))
        .addTo(layer);
      // Znak to element HTML (divIcon), więc opis dla czytników ekranu nadajemy sami.
      const element = marker.getElement();
      element?.setAttribute("role", "button");
      element?.setAttribute("aria-label", label);
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
      <div className="basemap-switch" role="group" aria-label="Podkład mapy">
        {BASEMAPS.map((b) => (
          <button
            key={b.id}
            type="button"
            className={b.id === basemap ? "basemap basemap-active" : "basemap"}
            aria-pressed={b.id === basemap}
            title={`Podkład: ${b.label.toLowerCase()}`}
            onClick={() => setBasemap(b.id)}
          >
            <span
              className="basemap-thumb"
              dangerouslySetInnerHTML={{ __html: b.thumbnail }}
            />
            <span className="basemap-label">{b.label}</span>
          </button>
        ))}
      </div>
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
            <p className="legend-title">Kategoria przejazdu</p>
            {LEGEND_ORDER.map((category) => (
              <div key={category} className="legend-row">
                <CategoryPin category={category} size={24} />
                <span>
                  <strong>{category}</strong> — {CATEGORY_DESCRIPTION[category]}
                </span>
              </div>
            ))}
            <p className="legend-note">
              Ciemniejsza czerwień = mniej urządzeń zabezpieczenia. To nie jest
              wynik rankingu.
            </p>
            <div className="legend-row">
              <CategoryPin category="B" verified={false} size={24} />
              <span>niezweryfikowany (przerywana obwódka)</span>
            </div>
            <div className="legend-row">
              <CategoryPin category="C" warning size={24} />
              <span>ostrzeżenie o jakości danych</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
