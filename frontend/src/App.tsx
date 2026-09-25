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

  // Browser Back used to leave the product. The builder and the list shared
  // one URL, so the only entry in history was whatever page came before —
  // and on Android, where Back is the primary gesture, that meant the app
  // closed mid-edit. Opening a bot now pushes a state; Back pops it and
  // returns to the list, and the URL says which bot you are looking at, so a
  // reload or a shared link lands in the right place.
  useEffect(() => {
    const onPop = (event: PopStateEvent) => {
      const botId = (event.state as { botId?: string } | null)?.botId;
      setScreen(botId ? { name: "builder", botId } : { name: "list" });
    };
    window.addEventListener("popstate", onPop);

    // A reload on /bot/<id> should reopen that bot rather than the list.
    const match = window.location.pathname.match(/^\/bot\/([0-9a-f-]{36})$/i);
    if (match) setScreen({ name: "builder", botId: match[1] });

    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const openBot = (botId: string) => {
    window.history.pushState({ botId }, "", `/bot/${botId}`);
    setScreen({ name: "builder", botId });
  };

  const showList = () => {
    // `back()` when we got here by pushState, so the history stack does not
    // grow a dead entry for every open/close round trip.
    if ((window.history.state as { botId?: string } | null)?.botId) window.history.back();
    else {
      window.history.replaceState(null, "", "/");
      setScreen({ name: "list" });
    }
  };

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
        // Только отказ в доступе означает «сессия протухла». Раньше сюда
        // попадала ЛЮБАЯ ошибка, включая обрыв связи, — и человека
        // выбрасывало на лендинг посреди правки, со стёртым токеном и
        // единственным путём назад через виджет Telegram. В метро с
        // телефона это происходило бы постоянно.
        const expired = err instanceof ApiError && (err.status === 401 || err.status === 403);
        if (!initData && expired) {
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
              onBack={showList}
              onDeleted={() => {
              window.history.replaceState(null, "", "/");
              setScreen({ name: "list" });
            }}
            />
          </Suspense>
        ) : (
          <BotList
            greetingName={clientName}
            isMiniApp={isMiniApp}
            onOpen={openBot}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
