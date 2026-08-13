import { useEffect, useState } from "react";

import { ApiError, builderApi, configureBuilderApi } from "./api/builderApi";
import "./App.css";
import { BotBuilder } from "./components/BotBuilder";
import { BotList } from "./components/BotList";
import { useTelegramWebApp } from "./hooks/useTelegramWebApp";

type BootState = "loading" | "ready" | "error";
type Screen = { name: "list" } | { name: "builder"; botId: string };

export default function App() {
  const { ready, initData, user } = useTelegramWebApp();

  const [bootState, setBootState] = useState<BootState>("loading");
  const [bootError, setBootError] = useState<string | null>(null);
  const [screen, setScreen] = useState<Screen>({ name: "list" });

  // Bootstrap: validate initData with the backend once, then show the bot list.
  useEffect(() => {
    if (!ready) return;

    configureBuilderApi(() => initData);

    (async () => {
      try {
        await builderApi.getMe();
        setBootState("ready");
      } catch (err) {
        setBootError(err instanceof ApiError ? err.message : "Не удалось загрузить конструктор");
        setBootState("error");
      }
    })();
  }, [ready, initData]);

  if (bootState === "loading") {
    return (
      <div className="screen screen--center">
        <div className="state-icon">🏭</div>
        <p>Загружаем Bot Factory…</p>
      </div>
    );
  }

  if (bootState === "error") {
    return (
      <div className="screen screen--center">
        <div className="state-icon">😕</div>
        <p>{bootError}</p>
      </div>
    );
  }

  if (screen.name === "builder") {
    return (
      <BotBuilder
        botId={screen.botId}
        onBack={() => setScreen({ name: "list" })}
        onDeleted={() => setScreen({ name: "list" })}
      />
    );
  }

  return (
    <BotList
      greetingName={user?.first_name}
      onOpen={(botId) => setScreen({ name: "builder", botId })}
    />
  );
}
