import type { Category } from "./api";
import { pinHtml } from "./pictograms";

/** Ten sam znak co na mapie, do listy i legendy (statyczny SVG z własnego kodu). */
export function CategoryPin(props: {
  category: Category | null;
  verified?: boolean;
  warning?: boolean;
  size?: number;
}) {
  return (
    <span
      className="pin-holder"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: pinHtml(props) }}
    />
  );
}
