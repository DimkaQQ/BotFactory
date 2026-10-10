import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
// Шрифты лежат в сборке (без внешних запросов): Onest с родной кириллицей
// для текста, JetBrains Mono для цифр и кода.
import "@fontsource-variable/onest";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
