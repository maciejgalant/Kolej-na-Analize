import "leaflet/dist/leaflet.css";
import "./styles.css";
import "./chat.css";
import "./presentation.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

