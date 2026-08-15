import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
// Self-hosted variable font (bundled, no external request) — strong native
// Cyrillic design, not just Latin-with-Cyrillic-bolted-on, since every
// word on this site is Russian.
import "@fontsource-variable/manrope";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
