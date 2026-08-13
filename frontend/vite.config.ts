import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Mini App is served under /builder in production (see nginx/default.conf),
// so both dev and build need to know that base path.
export default defineConfig({
  base: "/builder/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
