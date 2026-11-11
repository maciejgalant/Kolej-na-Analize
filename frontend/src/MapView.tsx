import L from "leaflet";
import { useEffect, useRef } from "react";

const WARSAW_CENTER: L.LatLngTuple = [52.2297, 21.0122];

export function MapView() {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const map = L.map(container.current, { center: WARSAW_CENTER, zoom: 11 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    return () => {
      map.remove();
    };
  }, []);

  return <div ref={container} className="map" role="application" aria-label="Mapa Warszawy" />;
}
