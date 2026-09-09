import { Suspense, lazy, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import {
  ApiError,
  builderApi,
  clearSessionAuth,
  configureBuilderApi,
  configureSessionAuth,
  getStoredSessionToken,
} from "./api/builderApi";
import "./App.css";
import { BotList } from "./components/BotList";
import { LoginScreen } from "./components/LoginScreen";
import { useTelegramWebApp } from "./hooks/useTelegramWebApp";

/** The builder drags in React Flow — by far the heaviest dependency here,
 * and one nobody needs until they actually open a bot. Split out, so the
 * landing and the bot list load without it. */
const BotBuilder = lazy(() => import("./components/BotBuilder").then((m) => ({ default: m.BotBuilder })));

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

  const screenKey = screen.name === "builder" ? `builder-${screen.botId}` : "list";

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={screenKey}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
      >
        {screen.name === "builder" ? (
          <Suspense
            fallback={
              <div className="screen screen--center">
                <div className="state-icon">🛠</div>
                <p>Открываем холст…</p>
              </div>
            }
          >
            <BotBuilder
              botId={screen.botId}
              isMiniApp={isMiniApp}
              onBack={() => setScreen({ name: "list" })}
              onDeleted={() => setScreen({ name: "list" })}
            />
          </Suspense>
        ) : (
          <BotList
            greetingName={clientName}
            isMiniApp={isMiniApp}
            onOpen={(botId) => setScreen({ name: "builder", botId })}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
