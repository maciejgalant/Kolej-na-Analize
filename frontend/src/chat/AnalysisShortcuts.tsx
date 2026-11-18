import { useState } from "react";
import type { CrossingFeature } from "../api";

export function AnalysisShortcuts({
  crossings,
  disabled,
  onSend,
}: {
  crossings: CrossingFeature[];
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const options = crossings.filter(
    (c) =>
      c.properties.name &&
      !c.properties.verification_status.startsWith("rejected"),
  );
  return (
    <div className="analysis-shortcuts">
      <div className="analysis-shortcut-buttons">
        <button
          type="button"
          aria-expanded={comparing}
          onClick={() => setComparing((v) => !v)}
        >
          Porównaj przejazdy
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            onSend(
              "Które przejazdy mają niepełne lub modelowane dane? Sprawdź jakość danych.",
            )
          }
        >
          Sprawdź jakość danych
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSend("Co potrafisz?")}
        >
          Co potrafisz?
        </button>
      </div>
      {comparing && (
        <form
          className="comparison-picker"
          onSubmit={(e) => {
            e.preventDefault();
            const first = options.find((c) => String(c.id) === a);
            const second = options.find((c) => String(c.id) === b);
            if (!disabled && first && second && a !== b) {
              onSend(
                `Porównaj przejazdy o numerach „${first.properties.name}” i „${second.properties.name}”. Wyjaśnij różnice WPO, wkłady składników i jakość danych.`,
              );
              setComparing(false);
            }
          }}
        >
          <p>
            Wybierz dwa przejazdy. Porównanie pokaże wyniki, składniki i braki
            danych.
          </p>
          <div>
            {[a, b].map((v, i) => (
              <label key={i}>
                Przejazd {i === 0 ? "A" : "B"}
                <select
                  aria-label={`Przejazd ${i === 0 ? "A" : "B"}`}
                  value={v}
                  onChange={(e) => (i === 0 ? setA : setB)(e.target.value)}
                >
                  <option value="">Wybierz przejazd</option>
                  {options.map((c) => (
                    <option
                      key={c.id}
                      value={c.id}
                      disabled={String(c.id) === (i === 0 ? b : a)}
                    >
                      {[
                        c.properties.street,
                        c.properties.name,
                        c.properties.district_name,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          {!options.length && (
            <small>
              Lista przejazdów jest niedostępna. Możesz podać dwa numery w
              wiadomości.
            </small>
          )}
          <div className="comparison-picker-actions">
            <button type="button" onClick={() => setComparing(false)}>
              Anuluj
            </button>
            <button
              className="primary"
              disabled={disabled || !a || !b || a === b}
            >
              Porównaj wybrane
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
