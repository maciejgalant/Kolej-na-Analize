import type { Category, VerificationStatus } from "./api";

export const CATEGORY_DESCRIPTION: Record<Category, string> = {
  A: "ruch kierowany przez pracowników kolei",
  B: "samoczynna sygnalizacja świetlna i rogatki",
  C: "samoczynna sygnalizacja świetlna, bez rogatek",
  D: "bez urządzeń zabezpieczenia ruchu",
  E: "przejście dla pieszych",
  F: "przejazd lub przejście na drodze wewnętrznej",
};

export const STATUS_LABEL: Record<VerificationStatus, string> = {
  verified: "zweryfikowany",
  unverified: "niezweryfikowany",
  rejected_grade_separated: "odrzucony — skrzyżowanie bezkolizyjne",
  rejected_other: "odrzucony",
};

export const FLAG_LABEL: Record<string, string> = {
  train_count_sensitive: "Liczba pociągów niepewna",
  train_count_extended: "Liczba pociągów z rozszerzonego progu",
  outside_warsaw: "Poza granicami Warszawy",
  no_road_nearby: "Brak jezdni w pobliżu",
  no_track_nearby: "Brak toru w pobliżu",
  grade_separation_suspected: "Możliwe skrzyżowanie bezkolizyjne",
  track_inactive: "Tor oznaczony jako nieczynny",
  near_district_boundary: "Blisko granicy dzielnicy",
  position_approximate: "Położenie przybliżone",
  no_osm_confirmation: "Brak potwierdzenia w OpenStreetMap",
  osm_type_mismatch: "Inny typ obiektu w OpenStreetMap",
  category_unrecognised: "Nierozpoznana kategoria w źródle",
  duplicate_official_id: "Numer występuje u kilku zarządców",
};

const ATTRIBUTE_LABEL: Record<string, string> = {
  manager: "Zarządca",
  location_type: "Położenie na sieci",
  "osm:crossing:barrier": "Rogatki (OSM)",
  "osm:crossing:light": "Sygnalizacja świetlna (OSM)",
  "osm:crossing:bell": "Sygnał dźwiękowy (OSM)",
  "osm:crossing:saltire": "Krzyż św. Andrzeja (OSM)",
  "osm:ref": "Numer w OSM",
  "osm:railway:position": "Kilometr linii (OSM)",
};

/** Cechy techniczne (identyfikatory OSM, odległości) nie są pokazywane w karcie. */
export function attributeLabel(code: string): string | null {
  return ATTRIBUTE_LABEL[code] ?? null;
}

export function crossingTitle(c: {
  name: string | null;
  crossing_id: number;
}): string {
  return c.name ?? `Przejazd nr ${c.crossing_id}`;
}

export function objectsLabel(count: number): string {
  const lastTwo = count % 100;
  const last = count % 10;
  if (count === 1) return "obiekt";
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14))
    return "obiekty";
  return "obiektów";
}

export const COMPONENT_LABEL: Record<"T" | "P" | "G" | "H", string> = {
  T: "Ekspozycja na ruch",
  P: "Zabezpieczenia",
  G: "Geometria",
  H: "Historia zdarzeń",
};

export const COMPONENT_STATUS: Record<string, string> = {
  ok: "dane źródłowe",
  modelled: "szacunek",
  unknown: "brak danych",
};
