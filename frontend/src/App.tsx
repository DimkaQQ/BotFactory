import { useEffect, useState } from "react";

import {
  ApiError,
  builderApi,
  clearSessionAuth,
  configureBuilderApi,
  configureSessionAuth,
  getStoredSessionToken,
} from "./api/builderApi";
import "./App.css";
import { BotBuilder } from "./components/BotBuilder";
import { BotList } from "./components/BotList";
import { LoginScreen } from "./components/LoginScreen";
import { useTelegramWebApp } from "./hooks/useTelegramWebApp";

type BootState = "loading" | "need-login" | "ready" | "error";
type Screen = { name: "list" } | { name: "builder"; botId: string };

export default function App() {
  const { ready, initData } = useTelegramWebApp();
  // Real Telegram initData only ever exists inside the Mini App — that's
  // the one reliable signal to tell "opened from the bot" apart from "opened
  // as a regular website" (including a plain browser tab with a restored
  // web session, which has no initData either).
  const isMiniApp = !!initData;

  const [bootState, setBootState] = useState<BootState>("loading");
  const [bootError, setBootError] = useState<string | null>(null);
  const [clientName, setClientName] = useState<string | undefined>();
  const [screen, setScreen] = useState<Screen>({ name: "list" });

  // Bootstrap: inside Telegram, trust initData outright. Outside it (plain
  // browser), restore a saved web session or fall back to the login screen.
  useEffect(() => {
    if (!ready) return;

    (async () => {
      if (initData) {
        configureBuilderApi(() => initData);
      } else {
        const stored = getStoredSessionToken();
        if (!stored) {
          setBootState("need-login");
          return;
        }
        configureSessionAuth(stored);
      }

      try {
        const me = await builderApi.getMe();
        setClientName(me.full_name ?? undefined);
        setBootState("ready");
      } catch (err) {
        if (!initData) {
          // Stored web session is stale/expired — send back to login rather
          // than a dead-end error screen.
          clearSessionAuth();
          setBootState("need-login");
          return;
        }
        setBootError(err instanceof ApiError ? err.message : "Не удалось загрузить конструктор");
        setBootState("error");
      }
    })();
  }, [ready, initData]);

  function handleLoggedIn() {
    setBootState("loading");
    builderApi
      .getMe()
      .then((me) => {
        setClientName(me.full_name ?? undefined);
        setBootState("ready");
      })
      .catch(() => {
        clearSessionAuth();
        setBootState("need-login");
      });
  }

  if (bootState === "loading") {
    return (
      <div className="screen screen--center">
        <div className="state-icon">🏭</div>
        <p>Загружаем Bot Factory…</p>
      </div>
    );
  }

  if (bootState === "need-login") {
    return <LoginScreen onLoggedIn={handleLoggedIn} />;
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
        isMiniApp={isMiniApp}
        onBack={() => setScreen({ name: "list" })}
        onDeleted={() => setScreen({ name: "list" })}
      />
    );
  }

  return (
    <BotList
      greetingName={clientName}
      isMiniApp={isMiniApp}
      onOpen={(botId) => setScreen({ name: "builder", botId })}
    />
  );
}
