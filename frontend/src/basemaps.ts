import L from "leaflet";

export type BasemapId = "gray" | "color" | "ortho";

export interface Basemap {
  id: BasemapId;
  label: string;
  /** Miniatura przycisku (SVG 40×40). */
  thumbnail: string;
  create: () => L.TileLayer;
}

const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
// Ortofotomapa PZGiK: usługa bezpłatna, bez ograniczeń poza masowym pobieraniem obrazów.
const ORTHO_URL =
  "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution";

const THUMB = (body: string) =>
  `<svg viewBox="0 0 40 40" width="40" height="40" aria-hidden="true" focusable="false">${body}</svg>`;

export const BASEMAPS: Basemap[] = [
  {
    id: "gray",
    label: "Szara",
    thumbnail: THUMB(
      `<rect width="40" height="40" fill="#eceef0"/>
       <path d="M0 28 C12 24 22 30 40 22" stroke="#fff" stroke-width="5" fill="none"/>
       <path d="M14 0 L20 40" stroke="#fff" stroke-width="4"/>
       <path d="M0 10 H40" stroke="#d3d7db" stroke-width="2"/>
       <rect x="24" y="4" width="10" height="8" fill="#dcdfe2"/>
       <rect x="3" y="31" width="8" height="7" fill="#dcdfe2"/>`,
    ),
    // OSM w odcieniach szarości (filtr CSS): neutralne tło dla piktogramów, bez klucza API.
    create: () =>
      L.tileLayer(OSM_URL, {
        maxZoom: 19,
        attribution: OSM_ATTRIBUTION,
        className: "tiles-gray",
      }),
  },
  {
    id: "color",
    label: "Kolorowa",
    thumbnail: THUMB(
      `<rect width="40" height="40" fill="#f2efe9"/>
       <rect x="22" y="2" width="16" height="12" fill="#cde6c3"/>
       <path d="M0 28 C12 24 22 30 40 22" stroke="#f7d38a" stroke-width="5" fill="none"/>
       <path d="M14 0 L20 40" stroke="#fff" stroke-width="4"/>
       <path d="M0 36 Q20 32 40 38" stroke="#aad3df" stroke-width="4" fill="none"/>`,
    ),
    create: () =>
      L.tileLayer(OSM_URL, { maxZoom: 19, attribution: OSM_ATTRIBUTION }),
  },
  {
    id: "ortho",
    label: "Ortofoto",
    thumbnail: THUMB(
      `<rect width="40" height="40" fill="#5f6b4a"/>
       <rect x="2" y="3" width="15" height="13" fill="#7d8460"/>
       <rect x="22" y="22" width="16" height="15" fill="#4c5a3a"/>
       <rect x="24" y="4" width="9" height="7" fill="#b9b2a4"/>
       <rect x="5" y="25" width="8" height="6" fill="#c9c2b5"/>
       <path d="M0 19 L40 17" stroke="#9a968c" stroke-width="3"/>
       <path d="M18 0 L21 40" stroke="#8e8a80" stroke-width="2.5"/>`,
    ),
    create: () =>
      L.tileLayer.wms(ORTHO_URL, {
        layers: "Raster",
        format: "image/jpeg",
        version: "1.3.0",
        maxZoom: 20,
        attribution: "Ortofotomapa: GUGiK (geoportal.gov.pl)",
      }),
  },
];

const STORAGE_KEY = "railsafe.basemap";

/** Zapamiętany wybór podkładu; w razie braku dostępu do pamięci przeglądarki — szara. */
export function storedBasemap(): BasemapId {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (BASEMAPS.some((b) => b.id === value)) return value as BasemapId;
  } catch {
    /* pamięć przeglądarki niedostępna */
  }
  return "gray";
}

export function storeBasemap(id: BasemapId): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* bez zapamiętywania */
  }
}
