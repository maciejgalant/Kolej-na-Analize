import { useMemo, useState } from "react";
import type { Category, CrossingFeature, DistrictFeature } from "./api";
import type { Attachment, MapState } from "./chat/model";
import { CrossingCard } from "./CrossingCard";
import { Dialog } from "./Dialog";
import { MapView } from "./MapView";
import { crossingTitle, CATEGORY_DESCRIPTION } from "./labels";
interface Props {
  crossings: CrossingFeature[];
  districts: DistrictFeature[];
  demo: boolean;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  saved: MapState;
  onSave: (patch: Partial<MapState>) => void;
  ids?: number[];
  initialSelected?: number;
  onClose: () => void;
  onAsk: (a: Attachment) => void;
}
export function MapExplorer({
  crossings,
  districts,
  demo,
  loading,
  error,
  onRetry,
  saved,
  onSave,
  ids,
  initialSelected,
  onClose,
  onAsk,
}: Props) {
  const [selected, setSelected] = useState<number | null>(
    initialSelected ?? null,
  );
  const [scope, setScope] = useState(ids);
  const visible = useMemo(
    () =>
      crossings.filter(
        (c) =>
          !c.properties.verification_status.startsWith("rejected") &&
          (!scope || scope.includes(c.id)) &&
          (saved.districtId === null ||
            c.properties.district_id === saved.districtId) &&
          (!saved.category || c.properties.category === saved.category),
      ),
    [crossings, saved.districtId, saved.category, scope],
  );
  const feature = crossings.find((c) => c.id === selected);
  const missing =
    scope?.filter((id) => !crossings.some((c) => c.id === id)).length ?? 0;
  return (
    <Dialog
      title="Mapa przejazdów"
      open
      onClose={onClose}
      className="map-dialog"
    >
      {demo && (
        <div className="demo-bar demo-bar-strong">
          DANE DEMONSTRACYJNE — fikcyjne obiekty i wartości.
        </div>
      )}
      <div className="map-filters">
        <label>
          Dzielnica
          <select
            aria-label="Dzielnica"
            value={saved.districtId ?? ""}
            onChange={(e) => {
              onSave({
                districtId: e.target.value ? Number(e.target.value) : null,
              });
              setSelected(null);
            }}
          >
            <option value="">
              {demo ? "Wszystkie dzielnice" : "Cała Warszawa"}
            </option>
            {districts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.properties.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Kategoria
          <select
            aria-label="Kategoria przejazdu"
            value={saved.category}
            onChange={(e) => {
              onSave({ category: e.target.value });
              setSelected(null);
            }}
          >
            <option value="">Wszystkie kategorie</option>
            {(["A", "B", "C", "D", "E", "F"] as Category[]).map((c) => (
              <option key={c} value={c}>
                {c} — {CATEGORY_DESCRIPTION[c]}
              </option>
            ))}
          </select>
        </label>
        <span className="map-count" aria-live="polite">
          {visible.length} obiektów
        </span>
        {scope && (
          <button onClick={() => setScope(undefined)}>
            Pokaż wszystkie przejazdy
          </button>
        )}
      </div>
      {error && (
        <div className="alert" role="alert">
          Nie udało się pobrać przejazdów.{" "}
          <button onClick={onRetry}>Spróbuj ponownie</button>
        </div>
      )}
      {!!missing && !loading && (
        <div className="map-empty" role="status">
          Część przejazdów z tej odpowiedzi nie jest już dostępna w bieżącej
          ewidencji ({missing}).
        </div>
      )}
      {!loading && !error && !visible.length && (
        <div className="map-empty" role="status">
          Brak przejazdów w tym zakresie. Zmień filtry lub pokaż wszystkie
          przejazdy.
        </div>
      )}
      <div
        className={`map-explorer-body ${selected !== null ? "has-detail" : ""}`}
      >
        <div className="explorer-map">
          <MapView
            districts={districts}
            crossings={visible}
            selectedDistrictId={saved.districtId}
            selectedCrossingId={selected}
            onSelectCrossing={setSelected}
            loading={loading}
            demo={demo}
            layoutKey={String(selected !== null)}
            savedState={saved}
            onStateChange={onSave}
            fitCrossingIds={scope}
          />
        </div>
        {selected !== null && (
          <aside className="explorer-detail" aria-label="Szczegóły przejazdu">
            <div className="detail-actions">
              <button onClick={() => setSelected(null)}>← Wróć do mapy</button>
              <button
                className="primary"
                onClick={() =>
                  onAsk({
                    id: selected,
                    label: feature
                      ? [
                          feature.properties.street,
                          crossingTitle(feature.properties),
                        ]
                          .filter(Boolean)
                          .join(" · ")
                      : `#${selected}`,
                  })
                }
              >
                Zapytaj o ten przejazd
              </button>
            </div>
            <CrossingCard
              crossingId={selected}
              street={feature?.properties.street}
            />
          </aside>
        )}
      </div>
    </Dialog>
  );
}
