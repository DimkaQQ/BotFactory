import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The web app is the primary product now, served at the domain root (see
// nginx/default.conf). It also runs inside the Telegram Mini App (opened by
// the meta-bot) — same build, same URL, the app just detects at runtime
// whether real Telegram initData is present and switches to a lighter
// "dashboard" mode there (see App.tsx / BotBuilder's isMiniApp prop).
export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
