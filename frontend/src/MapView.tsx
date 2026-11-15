import L from "leaflet";
import { useEffect, useRef, useState } from "react";

import type { MapState } from "./chat/model";
import type { Category, CrossingFeature, DistrictFeature } from "./api";
import {
  BASEMAPS,
  type BasemapId,
  storeBasemap,
  storedBasemap,
} from "./basemaps";
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
  /** Margines dopasowania widoku, gdy okna zasłaniają boki mapy (px). */
  fitPadding?: { left: number; right: number } | null;
  savedState?: MapState;
  onStateChange?: (patch: Partial<MapState>) => void;
  fitCrossingIds?: number[];
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
  fitPadding = null,
  savedState,
  onStateChange,
  fitCrossingIds,
}: Props) {
  const [legendOpen, setLegendOpen] = useState(false);
  const [basemap, setBasemap] = useState<BasemapId>(
    () => savedState?.basemap ?? storedBasemap(),
  );
  const initialState = useRef(savedState);
  const stateChange = useRef(onStateChange);
  stateChange.current = onStateChange;
  const previousDistrict = useRef(selectedDistrictId);
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
      center: initialState.current?.center ?? WARSAW_CENTER,
      zoom: initialState.current?.zoom ?? 11,
      // własne przyciski powiększenia są na pasku narzędzi mapy (nie pod oknami)
      zoomControl: false,
      // Modal maps can close during zoom; Leaflet's CSS transition timer outlives remove().
      zoomAnimation: false,
    });
    markerLayer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    instance.on("moveend", () => {
      const center = instance.getCenter();
      stateChange.current?.({
        center: [center.lat, center.lng],
        zoom: instance.getZoom(),
      });
    });
    const observer = new ResizeObserver(() => {
      if (map.current === instance) instance.invalidateSize();
    });
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.stop();
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
    stateChange.current?.({ basemap });
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
    const shouldFit =
      !initialState.current || previousDistrict.current !== selectedDistrictId;
    previousDistrict.current = selectedDistrictId;
    if (shouldFit && target.isValid())
      instance.fitBounds(
        target,
        fitPadding
          ? {
              paddingTopLeft: [fitPadding.left, 24],
              paddingBottomRight: [fitPadding.right, 90],
            }
          : { padding: [16, 16] },
      );
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
      const tooltip = document.createElement("span");
      tooltip.textContent = label;
      const marker = L.marker([lat, lon], {
        icon: markerIcon(feature, selected),
        alt: label,
        keyboard: true,
        zIndexOffset: selected ? 1000 : 0,
        riseOnHover: true,
      })
        .bindTooltip(tooltip, { direction: "top", offset: [0, -16] })
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

  useEffect(() => {
    const instance = map.current;
    if (!instance || !fitCrossingIds?.length) return;
    const points = crossings
      .filter((c) => fitCrossingIds.includes(c.id))
      .map((c) => {
        const [lon, lat] = c.geometry.coordinates;
        return L.latLng(lat, lon);
      });
    // Child effects run before dialog.showModal(): defer until its container is visible.
    const frame = requestAnimationFrame(() => {
      if (map.current !== instance || !points.length) return;
      instance.invalidateSize();
      instance.fitBounds(L.latLngBounds(points), {
        padding: [48, 48],
        maxZoom: 16,
        animate: false,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [fitCrossingIds, crossings]);

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
      {legendOpen && (
        <div className="legend" id="map-legend" aria-label="Legenda">
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
            Wszystkie znaki mają ten sam kolor; kategorię rozpoznaje się po
            rysunku. Znak nie mówi nic o pozycji w rankingu.
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
      <div className="map-toolbar" role="toolbar" aria-label="Narzędzia mapy">
        <div className="toolbar-group" role="group" aria-label="Powiększenie">
          <button
            type="button"
            className="tool-button"
            aria-label="Pomniejsz mapę"
            title="Pomniejsz"
            onClick={() => map.current?.zoomOut()}
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <path
                d="M3 8h10"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <button
            type="button"
            className="tool-button"
            aria-label="Powiększ mapę"
            title="Powiększ"
            onClick={() => map.current?.zoomIn()}
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <path
                d="M3 8h10M8 3v10"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
        <span className="toolbar-sep" aria-hidden="true" />
        <div className="toolbar-group" role="group" aria-label="Podkład mapy">
          {BASEMAPS.map((b) => (
            <button
              key={b.id}
              type="button"
              className={
                b.id === basemap ? "basemap basemap-active" : "basemap"
              }
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
        <span className="toolbar-sep" aria-hidden="true" />
        <button
          type="button"
          className={
            legendOpen
              ? "tool-button tool-text tool-active"
              : "tool-button tool-text"
          }
          aria-expanded={legendOpen}
          aria-controls="map-legend"
          onClick={() => setLegendOpen((value) => !value)}
        >
          Legenda
        </button>
      </div>
    </div>
  );
}
