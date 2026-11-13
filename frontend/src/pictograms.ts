import type { Category } from "./api";

/**
 * Piktogramy przejazdów (SVG 24×24, biały rysunek na kolorowym tle).
 *
 * Kolor drogowych kategorii to odcienie czerwieni: im mniej urządzeń zabezpieczenia,
 * tym ciemniejsza czerwień (A najjaśniejsza, D najciemniejsza). Przejście dla pieszych
 * (E) ma kolor granatowy, bo nie należy do rankingu. Kategoria nigdy nie jest
 * przekazywana samym kolorem: każda ma własny rysunek i opis w legendzie.
 */

export const CATEGORY_COLOR: Record<Category | "unknown", string> = {
  A: "#cf6e76", // pracownik kolei kieruje ruchem
  B: "#bf3e48", // rogatki i sygnalizacja
  C: "#a3242e", // sygnalizacja bez rogatek
  D: "#7a121b", // bez urządzeń
  F: "#9e4a2c", // droga wewnętrzna
  E: "#174a7e", // przejście dla pieszych
  unknown: "#526476",
};

export const CATEGORY_SHORT: Record<Category, string> = {
  A: "pracownik kolei kieruje ruchem",
  B: "rogatki i sygnalizacja",
  C: "sygnalizacja bez rogatek",
  D: "bez urządzeń zabezpieczenia",
  E: "przejście dla pieszych",
  F: "droga wewnętrzna",
};

const STROKE =
  'fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"';

const DRAWINGS: Record<Category | "unknown", string> = {
  // pracownik kolei z tarczą sygnałową („lizakiem”)
  A: `
  <circle cx="8.5" cy="5" r="2.3" fill="#fff"/>
  <path ${STROKE} d="M8.5 8.5V15M8.5 15l-2.6 5.5M8.5 15l2.6 5.5M8.5 10.5l5.2-3"/>
  <circle cx="17" cy="6" r="3.4" fill="#fff"/>
  <circle cx="17" cy="6" r="1.3" fill="currentColor"/>`,
  // rogatka: słupek z lampą i ramię w pasy
  B: `
  <path ${STROKE} d="M4.5 21V7.5"/>
  <circle cx="4.5" cy="4.8" r="2" fill="#fff"/>
  <rect x="4.5" y="10" width="16" height="4" rx="1" fill="none" stroke="#fff" stroke-width="1.6"/>
  <rect x="7.5" y="10" width="3" height="4" fill="#fff"/>
  <rect x="13.5" y="10" width="3" height="4" fill="#fff"/>`,
  // sygnalizator przejazdowy: dwie lampy obok siebie, bez rogatki
  C: `
  <rect x="2.5" y="5" width="19" height="10" rx="5" fill="#fff"/>
  <circle cx="7.6" cy="10" r="2.8" fill="currentColor"/>
  <circle cx="16.4" cy="10" r="2.8" fill="currentColor"/>
  <path ${STROKE} d="M12 15v6M8.5 21h7"/>`,
  // krzyż św. Andrzeja
  D: `
  <path fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" d="M5 5l14 14M19 5L5 19"/>`,
  // pieszy w ruchu
  E: `
  <circle cx="13" cy="4.2" r="2.3" fill="#fff"/>
  <path ${STROKE} stroke-width="2.5" d="M12.5 8l-2 6 3 2.5 1 4.5M10.5 14l-2.5 6.5M12.4 8.4l3.6 2.6 2.5-.5M12.3 8.6L9 10.5 7.5 13"/>`,
  // znak „droga wewnętrzna” (D-46): prostokąt z literą W
  F: `
  <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" fill="none" stroke="#fff" stroke-width="2"/>
  <path ${STROKE} d="M6.3 8.3l2.1 7.4L12 10.6l3.6 5.1 2.1-7.4"/>`,
  unknown: `
  <path ${STROKE} d="M9.2 9a2.9 2.9 0 1 1 3.8 2.8c-.7.3-1 .8-1 1.5v1"/>
  <circle cx="12" cy="17.6" r="1.3" fill="#fff"/>`,
};

export function categoryKey(category: Category | null): Category | "unknown" {
  return category ?? "unknown";
}

/** Sam rysunek (bez tła) jako znacznik SVG 24×24. */
export function pictogramSvg(category: Category | null, size = 18): string {
  const key = categoryKey(category);
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false" style="color:${CATEGORY_COLOR[key]}">${DRAWINGS[key]}</svg>`;
}

export function categoryLabel(category: Category | null): string {
  return category ? `kategoria ${category}: ${CATEGORY_SHORT[category]}` : "kategoria nieznana";
}

export interface PinOptions {
  category: Category | null;
  verified?: boolean;
  warning?: boolean;
  selected?: boolean;
  /** Średnica znaku w pikselach. */
  size?: number;
}

/** Znak przejazdu: kolorowe kółko z piktogramem, opcjonalnie z ostrzeżeniem. */
export function pinHtml({
  category,
  verified = true,
  warning = false,
  selected = false,
  size = 32,
}: PinOptions): string {
  const key = categoryKey(category);
  const classes = [
    "pin",
    key === "E" ? "pin-ped" : "pin-road",
    verified ? "" : "pin-unverified",
    selected ? "pin-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const badge = warning ? '<span class="pin-warn" aria-hidden="true">!</span>' : "";
  return `<span class="${classes}" style="--pin:${CATEGORY_COLOR[key]};width:${size}px;height:${size}px">${pictogramSvg(category, Math.round(size * 0.74))}${badge}</span>`;
}
