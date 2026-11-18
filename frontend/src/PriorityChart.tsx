import type { CrossingDetail } from "./api";
import { COMPONENT_LABEL } from "./labels";

type Components = NonNullable<CrossingDetail["priority"]>["components"];
export function PriorityChart({ components }: { components: Components }) {
  const description = components.map(c =>
    `${COMPONENT_LABEL[c.component]}, waga ${Math.round(c.weight * 100)}%: ${c.value === null ? "brak punktacji" : `${c.value} na 100`}`
  ).join("; ");
  return <figure className="priority-chart">
    <figcaption>Jak obliczono WPO <small>składniki · skala 0–100</small></figcaption>
    <svg viewBox={`0 0 320 ${components.length * 48 + 4}`} role="img" aria-label={description}>
      {components.map((c, i) => <g key={c.component} transform={`translate(0 ${i * 48})`}>
        <text x="0" y="15" className="priority-chart-label">{COMPONENT_LABEL[c.component]} · {Math.round(c.weight * 100)}%</text>
        <text x="320" y="15" textAnchor="end" className="priority-chart-value">{c.value === null ? "—" : Math.round(c.value)}</text>
        <rect x="0" y="24" width="320" height="8" rx="4"
          className={c.value === null ? "priority-chart-unknown" : "priority-chart-track"} />
        {c.value !== null && <rect x="0" y="24"
          width={3.2 * Math.max(0, Math.min(100, c.value))} height="8" rx="4"
          className={c.status === "modelled" ? "priority-chart-model" : "priority-chart-source"} />}
        <title>{COMPONENT_LABEL[c.component]}: {c.value === null ? "punktacja nieustalona" : c.status === "modelled" ? "składnik modelowany" : "dane źródłowe"}</title>
      </g>)}
    </svg>
    <p className="muted small">Wartości składników, nie udział procentowy w wyniku. Historia H wymaga weryfikacji.</p>
  </figure>;
}
