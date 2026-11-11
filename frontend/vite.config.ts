import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// W trybie dev zapytania /api trafiają do backendu wystawionego na loopbacku.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
