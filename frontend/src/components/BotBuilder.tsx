import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  type BillingState,
  type BlockType,
  type BotBlock,
  type BotWithBlocks,
  type OrdersReport,
  type PaymentProviderInfo,
  type PaymentSettings,
  type PublicationInfo,
  ApiError,
  builderApi,
} from "../api/builderApi";
import { confirmDialog } from "../confirm";
import { openExternal } from "../hooks/useTelegramWebApp";
import { BLOCK_TYPE_BY_ID } from "../blockTypes";
import { plural } from "../plural";
import { loopedBlocks, orphanBlocks } from "../reachability";
import { BillingBanner, paidUntilLabel } from "./BillingBanner";
import { FlowCanvas } from "./flow/FlowCanvas";
import { LivePreview } from "./LivePreview";
import { BotProfilePanel } from "./BotProfilePanel";
import { PaymentSettingsPanel } from "./PaymentSettingsPanel";
import { SitePanel } from "./SitePanel";
import { SalesPanel } from "./SalesPanel";
import { PublishPaywall } from "./PublishPaywall";
import { PublishButton } from "./PublishButton";
import { ThemeToggle } from "./ThemeToggle";

const AUTOSAVE_DEBOUNCE_MS = 500;

type LoadState = "loading" | "ready" | "error";
// "failed" exists so the indicator can say a save did not happen —
// showing "Сохранено" for a request that errored is how work gets lost.
type SaveStatus = "idle" | "saving" | "saved" | "failed";

interface Props {
  botId: string;
  isMiniApp?: boolean;
  onBack: () => void;
  onDeleted: () => void;
}

export function BotBuilder({ botId, isMiniApp, onBack, onDeleted }: Props) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bot, setBot] = useState<BotWithBlocks | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [paymentPanelOpen, setPaymentPanelOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [siteOpen, setSiteOpen] = useState(false);
  const [salesPanelOpen, setSalesPanelOpen] = useState(false);
  const [paymentSettings, setPaymentSettings] = useState<PaymentSettings | null>(null);
  const [paymentProviders, setPaymentProviders] = useState<PaymentProviderInfo[]>([]);
  // Server-side switch: subscriptions are built but off while the one-off
  // sale is being shaken out.
  const [subscriptionsEnabled, setSubscriptionsEnabled] = useState(false);
  const [publication, setPublication] = useState<PublicationInfo | null>(null);
  const [billing, setBilling] = useState<BillingState | null>(null);
  const [sales, setSales] = useState<OrdersReport | null>(null);

  // The fixed footer's height decides how much room the canvas gets and how
  // much the page must reserve below it. Guessing it with a constant was
  // wrong every time it changed shape — a publish button, a paywall with one
  // method, a paywall with three — so it is measured instead.
  const footerRef = useRef<HTMLDivElement | null>(null);
  const screenRef = useRef<HTMLDivElement | null>(null);

  // Measured, never guessed — and re-measured on *every* render, because the
  // things being measured change without resizing anything: the footer swaps
  // between a publish button, an expanded token form and a paywall. Two
  // different `.app-footer` elements share this ref, so a ResizeObserver
  // attached once at mount ended up watching a detached node and `--footer-h`
  // sat at a stale 110px while the real footer was 52px — which is how the
  // publish confirm button ended up below the fold on every laptop.
  const measure = useCallback(() => {
    const footer = footerRef.current;
    const screen = screenRef.current;
    if (!footer || !screen) return;
    screen.style.setProperty("--footer-h", `${Math.ceil(footer.getBoundingClientRect().height)}px`);
    const canvas = screen.querySelector<HTMLElement>(".flow-canvas");
    if (canvas) {
      const above = canvas.getBoundingClientRect().top - screen.getBoundingClientRect().top;
      screen.style.setProperty("--above-h", `${Math.ceil(Math.max(above, 0))}px`);
    }
  }, []);

  useLayoutEffect(measure);

  // And once more for the changes React never hears about — a web font
  // landing, the browser chrome collapsing on scroll.
  useEffect(() => {
    const footer = footerRef.current;
    if (!footer) return;
    const observer = new ResizeObserver(measure);
    observer.observe(footer);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Правка, набранная в последние полсекунды, жила только в таймере
  // автосохранения — закрыл вкладку и потерял. Окно узкое, но индикатор в
  // этот момент показывает «Сохраняем…», то есть человек уверен в обратном.
  useEffect(() => {
    const warnIfUnsaved = (event: BeforeUnloadEvent) => {
      if (Object.keys(saveTimers.current).length === 0 && pendingSaves.current.size === 0) return;
      event.preventDefault();
      // Браузеры показывают свой текст, но требуют, чтобы значение было.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnIfUnsaved);
    return () => window.removeEventListener("beforeunload", warnIfUnsaved);
  }, []);
  const nameTimer = useRef<ReturnType<typeof setTimeout>>();

  // Tracks which fields (block ids, "name", "reorder") currently have an
  // autosave in flight, so the "Сохраняем… / Сохранено" indicator in the
  // header reflects reality even with several fields mid-edit at once —
  // repeated keystrokes on the same field are a no-op (Set), and the
  // status only flips back to "saved" once every field has settled.
  const pendingSaves = useRef<Set<string>>(new Set());
  const markPending = useCallback((key: string) => {
    pendingSaves.current.add(key);
    setSaveStatus("saving");
  }, []);
  const markSettled = useCallback((key: string) => {
    pendingSaves.current.delete(key);
    failedSaves.current.delete(key);
    if (pendingSaves.current.size === 0) {
      setSaveStatus(failedSaves.current.size > 0 ? "failed" : "saved");
    }
  }, []);

  // A save that did not happen must never show as "Сохранено". The whole
  // point of an autosave indicator is that the user trusts it and closes the
  // tab; an expired session or a restarted API would otherwise quietly eat
  // everything typed since.
  const failedSaves = useRef<Set<string>>(new Set());
  const markFailed = useCallback((key: string) => {
    failedSaves.current.add(key);
    pendingSaves.current.delete(key);
    if (pendingSaves.current.size === 0) setSaveStatus("failed");
  }, []);

  const retryFailedSaves = useCallback(async () => {
    if (!bot) return;
    setSaveStatus("saving");
    try {
      // Re-send the whole bot as it stands locally: what failed is whatever
      // the server has not got, and the client's copy is the truth here.
      // Positions and the start block are included — leaving them out meant
      // the indicator said "Сохранено" for changes still only in the browser.
      await Promise.all(
        bot.blocks.map((block) =>
          builderApi.updateBlock(bot.id, block.id, {
            content: block.content,
            next_block_id: block.next_block_id,
            position_x: block.position_x,
            position_y: block.position_y,
          }),
        ),
      );
      await builderApi.setStartBlock(bot.id, bot.start_block_id);
      if (bot.name) await builderApi.renameBot(bot.id, bot.name);
      failedSaves.current.clear();
      setSaveStatus("saved");
    } catch {
      setSaveStatus("failed");
    }
  }, [bot]);

  useEffect(() => {
    setLoadState("loading");
    (async () => {
      try {
        const full = await builderApi.getBot(botId);
        setBot(full);
        setLoadState("ready");
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : "Не удалось загрузить бота");
        setLoadState("error");
      }
    })();

    // Payment setup and the publication paywall are secondary — a failure
    // here leaves the constructor perfectly usable, so it never touches
    // loadState.
    (async () => {
      try {
        const [providers, settings, publicationInfo, billingState] = await Promise.all([
          builderApi.listPaymentProviders(),
          builderApi.getPaymentSettings(botId),
          builderApi.getPublicationInfo(botId),
          builderApi.getBilling(botId),
        ]);
        setPaymentProviders(providers.providers);
        setSubscriptionsEnabled(Boolean(providers.subscriptions_enabled));
        setPaymentSettings(settings);
        setPublication(publicationInfo);
        setBilling(billingState);
        builderApi
          .listOrders(botId)
          .then(setSales)
          // Не показать выручку — не повод ломать конструктор.
          .catch(() => undefined);
      } catch {
        // leaves payments unconfigured in the UI; nothing else breaks
      }
    })();
  }, [botId]);


  // Что человек узнавал только после того, как заплатил 99 $: касса без
  // ключей, кнопка в никуда, цена не указана. Считается прямо здесь, потому
  // что все три факта уже загружены — отдельный запрос не нужен.
  const publishProblems = (() => {
    if (!bot) return [];
    const found: string[] = [];
    const payBlocks = bot.blocks.filter((b) => b.block_type === "payment");

    if (payBlocks.length > 0 && !paymentSettings?.provider) {
      found.push("Касса не подключена — бот не сможет принять оплату.");
    } else if (payBlocks.length > 0 && paymentSettings && !paymentSettings.ready) {
      found.push(`В кассе не заполнено: ${paymentSettings.missing_fields.join(", ")} — оплата не откроется.`);
    } else if (payBlocks.length > 0 && paymentSettings && !paymentSettings.live) {
      // Галочка «тестовый режим» стоит по умолчанию — то есть по умолчанию
      // бот выходит в эфир, не принимая настоящих денег.
      found.push("Касса в тестовом режиме — платежи будут ненастоящими. Выключи его в настройках кассы.");
    }

    // Поля, которые заполняются в самом блоке, а не в кассе: ссылка на
    // оплату у «Оплаты по ссылке», номер оферты у LavaTop. У этих
    // провайдеров ключей в кассе нет вовсе, поэтому она объявлялась готовой
    // всегда — зелёное «Касса подключена» в шапке, пустой чек-лист, и
    // «не получилось открыть оплату» у первого же покупателя.
    const blockFields = paymentProviders.find((p) => p.slug === paymentSettings?.provider)?.block_fields ?? [];
    const unfilled = new Set<string>();
    for (const block of payBlocks) {
      for (const field of blockFields) {
        const value = (block.content as Record<string, unknown>)[field.key];
        if (!String(value ?? "").trim()) unfilled.add(field.label.toLowerCase());
      }
    }
    if (unfilled.size > 0) {
      found.push(`В блоке оплаты не заполнено: ${[...unfilled].join(", ")} — оплата не откроется.`);
    }

    // Заглушки шаблонов вроде «[цена]» и «[название продукта]»: покупатель
    // увидел бы их буквально, в квадратных скобках.
    const placeholder = /\[[^\]\n]*[а-яё][^\]\n]*\]/i;
    const withPlaceholder = bot.blocks.filter((b) =>
      Object.values(b.content as Record<string, unknown>).some((v) => typeof v === "string" && placeholder.test(v)),
    );
    if (withPlaceholder.length > 0) {
      found.push(
        'В текстах остались заглушки в квадратных скобках, например «[цена]» — замени их своими словами, иначе покупатель увидит скобки.',
      );
    }

    // Картинка или видео без файла: бот отправил бы голую подпись.
    const emptyMedia = bot.blocks.filter(
      (b) => (b.block_type === "image" || b.block_type === "video") && !String(b.content.media_file_id ?? "").trim(),
    );
    if (emptyMedia.length > 0) {
      found.push("Есть блок «Изображение» или «Видео» без файла — загрузи файл или вставь ссылку, иначе уйдёт только подпись.");
    }

    // Валюта блока, которую касса не принимает: покупатель получит ошибку.
    const allowed = paymentProviders.find((p) => p.slug === paymentSettings?.provider)?.currencies ?? [];
    if (allowed.length > 0) {
      const wrong = payBlocks.filter((b) => b.content.currency && !allowed.includes(String(b.content.currency).toUpperCase()));
      if (wrong.length > 0) {
        found.push(`Валюта в блоке оплаты не подходит этой кассе (она принимает: ${allowed.join(", ")}).`);
      }
    }

    // Быстрые кнопки: подписи должны быть уникальны и короче 64 символов.
    const replyLabels = bot.blocks
      .filter((b) => b.block_type === "buttons" && b.content.keyboard === "reply")
      .flatMap((b) => (b.content.buttons ?? []).map((btn) => (btn.label || "").trim()).filter(Boolean));
    if (new Set(replyLabels).size !== replyLabels.length) {
      found.push("У быстрых кнопок есть одинаковые подписи — бот не поймёт, какую нажали. Сделай их разными.");
    }
    if (replyLabels.some((l) => l.length > 64)) {
      found.push("Подпись быстрой кнопки длиннее 64 символов — Telegram её обрежет.");
    }

    const priceless = payBlocks.filter((b) => {
      const raw = String(b.content.price ?? "").replace(",", ".").trim();
      return !raw || Number(raw) <= 0;
    });
    if (priceless.length > 0) {
      found.push(
        priceless.length === 1
          ? "В блоке оплаты не указана цена — покупатель получит ошибку."
          : `Блоков оплаты без цены: ${priceless.length} — покупатели получат ошибку.`,
      );
    }

    // Блок «Выдача», которому нечего выдать. Шаблон «Платная подписка»
    // приходит с пустым полем чата и текстом «вот твоя персональная ссылка
    // на вход» — покупатель платил и получал обещание ссылки без ссылки.
    // Ссылка, вписанная прямо в текст, — тоже выдача, поэтому проверяется
    // и она.
    const emptyDelivery = bot.blocks.filter((b) => {
      if (b.block_type !== "delivery") return false;
      const hasLink = /https?:\/\/\S|t\.me\/\S/i.test(String(b.content.text ?? ""));
      return (
        !String(b.content.group_chat_id ?? "").trim() &&
        !String(b.content.media_file_id ?? "").trim() &&
        !hasLink
      );
    });
    if (emptyDelivery.length > 0) {
      found.push(
        "Блок «Выдача» ничего не выдаёт: ни файла, ни ссылки, ни доступа в чат — покупатель получит только текст.",
      );
    }

    const looped = loopedBlocks(bot.blocks, bot.start_block_id);
    if (looped.length > 0) {
      found.push(
        // Раньше здесь было «дойдёт и остановится молча» — и это описывало
        // не то, что происходит. Блоки кольца бот успевает отправить по
        // разу, замолкает он уже после них, на втором заходе.
        `Стрелки «дальше» замкнуты в кольцо (${looped.length} бл.) — эти сообщения придут по одному разу, ` +
          `и дальше сценарий остановится.`,
      );
    }

    const orphans = orphanBlocks(bot.blocks, bot.start_block_id);
    if (orphans.length > 0) {
      found.push(
        orphans.length === 1
          ? "Один блок ни с чем не соединён — бот его не покажет."
          : `Блоков ни с чем не соединено: ${orphans.length} — бот их не покажет.`,
      );
    }

    const deadButtons = bot.blocks
      .filter((b) => b.block_type === "buttons")
      .flatMap((b) => b.content.buttons ?? [])
      // Кнопка-ссылка ведёт наружу и продолжения не требует; молчит только
      // та, у которой нет ни ссылки, ни стрелки на холсте.
      .filter((button) => button.action_type !== "url" && !button.target_block_id);
    if (deadButtons.length > 0) {
      found.push(
        `Кнопка без продолжения: ${deadButtons
          .map((b) => `«${b.label || "без названия"}»`)
          .slice(0, 3)
          .join(", ")} — нажатие ничего не сделает.`,
      );
    }

    // Кнопка-ссылка на адрес без домена. Telegram отвергает такую кнопку, и
    // вместе с ней не уходит всё сообщение целиком — то есть пропадает не
    // кнопка, а весь блок.
    const brokenLinks = bot.blocks
      .filter((b) => b.block_type === "buttons")
      .flatMap((b) => b.content.buttons ?? [])
      .filter((button) => button.action_type === "url" && !/^(https?|tg):\/\/\S+\.\S|^tg:\/\//i.test(
        String(button.action_value ?? "").trim(),
      ));
    if (brokenLinks.length > 0) {
      found.push(
        `У кнопки ${brokenLinks
          .map((b) => `«${b.label || "без названия"}»`)
          .slice(0, 3)
          .join(", ")} не указан адрес — Telegram не покажет всё сообщение целиком.`,
      );
    }

    // Блок кнопок без текста. Telegram не отправляет кнопки без сообщения,
    // поэтому бот подставляет «…» — покупатель получает пустой пузырь.
    const speechless = bot.blocks.filter(
      (b) =>
        b.block_type === "buttons" &&
        !String(b.content.text ?? "").trim() &&
        (b.content.buttons ?? []).length > 0,
    );
    if (speechless.length > 0) {
      found.push("В блоке кнопок нет сообщения — покупатель увидит пузырь с «…» над кнопками.");
    }

    return found;
  })();

  // A renewal can put a stopped bot back on the air, so this re-reads the
  // bot itself and not just the clock — the status drives the whole header.
  const handleRenewed = useCallback(async () => {
    try {
      const [full, state] = await Promise.all([builderApi.getBot(botId), builderApi.getBilling(botId)]);
      setBot(full);
      setBilling(state);
    } catch {
      // The payment landed either way; a stale banner until the next load
      // is a far smaller problem than an error over a successful payment.
    }
  }, [botId]);

  const handleChangeContent = useCallback(
    (blockId: string, content: BotBlock["content"]) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, content } : b)) } : prev,
      );

      markPending(blockId);
      clearTimeout(saveTimers.current[blockId]);
      saveTimers.current[blockId] = setTimeout(async () => {
        delete saveTimers.current[blockId];
        try {
          await builderApi.updateBlock(bot.id, blockId, { content });
          markSettled(blockId);
        } catch {
          markFailed(blockId);
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleDelete = useCallback(
    async (blockId: string) => {
      if (!bot) return;
      // Removing a node can orphan two kinds of arrow pointing *at* it: the
      // backend already nulls next_block_id/start_block_id on delete (real
      // FKs, ON DELETE SET NULL) but a button's target_block_id lives inside
      // JSONB content, so it's on us to clear it here — otherwise the arrow
      // just silently stops resolving to anything on the canvas.
      const affected = bot.blocks.filter(
        (b) => b.block_type === "buttons" && (b.content.buttons ?? []).some((btn) => btn.target_block_id === blockId),
      );
      // Kept so a failed delete can be undone on the canvas instead of the
      // block reappearing out of nowhere on the next reload.
      const before = bot.blocks;
      const startBefore = bot.start_block_id;

      setBot((prev) =>
        prev
          ? {
              ...prev,
              start_block_id: prev.start_block_id === blockId ? null : prev.start_block_id,
              blocks: prev.blocks
                .filter((b) => b.id !== blockId)
                .map((b) =>
                  b.block_type === "buttons" && (b.content.buttons ?? []).some((btn) => btn.target_block_id === blockId)
                    ? {
                        ...b,
                        content: {
                          ...b.content,
                          buttons: (b.content.buttons ?? []).map((btn) =>
                            btn.target_block_id === blockId ? { ...btn, target_block_id: null } : btn,
                          ),
                        },
                      }
                    : b,
                ),
            }
          : prev,
      );
      try {
        await builderApi.deleteBlock(bot.id, blockId);
        await Promise.all(
          affected.map((b) =>
            builderApi.updateBlock(bot.id, b.id, {
              content: {
                ...b.content,
                buttons: (b.content.buttons ?? []).map((btn) =>
                  btn.target_block_id === blockId ? { ...btn, target_block_id: null } : btn,
                ),
              },
            }),
          ),
        );
      } catch {
        // The block is already gone from the canvas, so failing quietly here
        // meant it silently came back on the next reload. Put it back now and
        // say so, rather than letting the canvas and the database disagree.
        setBot((current) =>
          current ? { ...current, blocks: before, start_block_id: startBefore } : current,
        );
        markFailed(blockId);
      }
    },
    [bot, markFailed],
  );

  const handleAdd = useCallback(
    async (blockType: BlockType, position: { x: number; y: number }): Promise<string> => {
      if (!bot) throw new Error("Bot not loaded");
      const defaultContent = BLOCK_TYPE_BY_ID[blockType].defaultContent();
      if (blockType === "payment") {
        // The shop's own currency, not a constant. Falls back to RUB only
        // when no cash desk is connected yet — and the block picks the real
        // one up as soon as one is, because PaymentEditor writes back
        // whatever the provider actually supports.
        const connected = paymentProviders.find((p) => p.slug === paymentSettings?.provider);
        defaultContent.currency = connected?.currencies[0] ?? "RUB";
      }
      const created = await builderApi.createBlock(bot.id, blockType, defaultContent, position);
      setBot((prev) =>
        prev
          ? {
              ...prev,
              blocks: [...prev.blocks, created],
              start_block_id: prev.start_block_id ?? created.id,
            }
          : prev,
      );
      return created.id;
    },
    [bot, paymentProviders, paymentSettings],
  );

  // Graph edges — a plain arrow (next_block_id), a per-button branch (lives
  // in content, so it rides the same debounced content autosave), and the
  // "▶ Старт" pseudo-edge (bot.start_block_id). All three are optimistic:
  // the canvas already shows the new arrow before the PATCH lands.
  const handleSetNext = useCallback(
    (blockId: string, nextBlockId: string | null) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, next_block_id: nextBlockId } : b)) } : prev,
      );
      markPending(`${blockId}:next`);
      builderApi
        .updateBlock(bot.id, blockId, { next_block_id: nextBlockId })
        .then(() => markSettled(`${blockId}:next`))
        .catch(() => markFailed(`${blockId}:next`));
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleSetStart = useCallback(
    (blockId: string | null) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, start_block_id: blockId } : prev));
      markPending("start");
      builderApi
        .setStartBlock(bot.id, blockId)
        .then(() => markSettled("start"))
        .catch(() => markFailed("start"));
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleSetPosition = useCallback(
    (blockId: string, x: number, y: number) => {
      if (!bot) return;
      setBot((prev) =>
        prev ? { ...prev, blocks: prev.blocks.map((b) => (b.id === blockId ? { ...b, position_x: x, position_y: y } : b)) } : prev,
      );
      markPending(`${blockId}:pos`);
      builderApi
        .updateBlock(bot.id, blockId, { position_x: x, position_y: y })
        .then(() => markSettled(`${blockId}:pos`))
        .catch(() => markFailed(`${blockId}:pos`));
    },
    [bot, markPending, markSettled, markFailed],
  );

  const handleNameChange = useCallback(
    (name: string) => {
      if (!bot) return;
      setBot((prev) => (prev ? { ...prev, name } : prev));

      markPending("name");
      clearTimeout(nameTimer.current);
      nameTimer.current = setTimeout(async () => {
        try {
          await builderApi.renameBot(bot.id, name);
          markSettled("name");
        } catch {
          markFailed("name");
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [bot, markPending, markSettled],
  );

  const handlePublish = useCallback(
    async (token: string) => {
      if (!bot) return;
      await builderApi.publishBot(bot.id, token);
      const refreshed = await builderApi.getBot(bot.id);
      setBot(refreshed);
    },
    [bot],
  );

  async function handleDeleteBot() {
    if (!bot) return;
    const label = bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "этого бота";
    // То же, что и в списке ботов: сказать, что именно уходит. Здесь корзина
    // стоит рядом с «Касса подключена», то есть под рукой в самый обычный
    // день работы.
    const sold = sales && sales.paid_count > 0 ? ` (продаж: ${sales.paid_count})` : "";
    const confirmed = await confirmDialog(
      `Удалить ${label}?\n\nВместе с ним навсегда пропадёт история продаж и заказы${sold}` +
        (bot.paid_until ? ", а также оставшийся оплаченный период" : "") +
        ". Это нельзя отменить.",
    );
    if (!confirmed) return;

    setDeleting(true);
    try {
      await builderApi.deleteBot(bot.id);
      onDeleted();
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Не удалось удалить бота");
      setDeleting(false);
    }
  }

  if (loadState === "loading") {
    return (
      <div className="screen screen--center">
        <div className="state-icon">🛠</div>
        <p>Загружаем бота…</p>
      </div>
    );
  }

  if (loadState === "error" || !bot) {
    return (
      <div className="screen screen--center">
        <div className="state-icon">😕</div>
        <p>{loadError ?? "Бот не найден"}</p>
        <button type="button" className="back-link" onClick={onBack}>
          ← Назад к списку
        </button>
      </div>
    );
  }

  return (
    // The paywall card is roughly twice the height of the publish button, and
    // the footer is fixed — so the space reserved for it at the bottom of the
    // screen has to know which one is showing, or the card lands on top of the
    // "+ Добавить блок" bar and no block can be added on a phone.
    <div ref={screenRef} className="screen screen--builder">
      <header className="app-header">
        {/* One bar for "out of here" and the tools. On a phone these used to
            be two stacked 44px rows above the title — 56px of the canvas
            spent on a layout accident. */}
        <div className="app-header__bar">
          <button type="button" className="back-link" onClick={onBack}>
            ← Мои боты
          </button>
          <div className="app-header__actions">
            {!isMiniApp && <ThemeToggle />}
            {!isMiniApp && (
              <button
                type="button"
                className={`bot-payments-button ${
                  paymentSettings?.live
                    ? "bot-payments-button--on"
                    : paymentSettings?.provider
                      ? "bot-payments-button--half"
                      : ""
                }`}
                onClick={() => setPaymentPanelOpen(true)}
                title={
                  paymentSettings?.live
                    ? "Платёжная система, через которую бот принимает деньги"
                    : paymentSettings?.ready
                      ? "Касса в тестовом режиме — платежи ненастоящие"
                      : paymentSettings?.provider
                        ? `Касса выбрана, но не заполнено: ${paymentSettings.missing_fields.join(", ")}`
                        : "Платёжная система, через которую бот принимает деньги"
                }
              >
                {/* Two labels, one shown at a time by CSS: on a 390px phone
                    this bar also carries "← Мои боты", and the long form
                    squeezed the way out of the builder to 49px. */}
                {/* Три состояния, а не два. «Касса подключена» по факту
                    выбранного провайдера было прямой ложью: ключи пустые,
                    оплата не откроется, а владелец видит зелёное. */}
                {paymentSettings?.live ? "💳" : paymentSettings?.provider ? "⚠️" : "💳"}{" "}
                <span className="bot-payments-button__long">
                  {paymentSettings?.live
                    ? "Касса подключена"
                    : paymentSettings?.ready
                      ? "Касса в тестовом режиме"
                      : paymentSettings?.provider
                        ? "Касса не настроена"
                        : "Подключить кассу"}
                </span>
                <span className="bot-payments-button__short">Касса</span>
              </button>
            )}
            {!isMiniApp && bot.status === "active" && (
              <button
                type="button"
                className="bot-payments-button"
                onClick={() => setProfileOpen(true)}
                title="Фото, имя и описание бота в Telegram"
              >
                🎨 <span className="bot-payments-button__long">Оформление</span>
                <span className="bot-payments-button__short">Вид</span>
              </button>
            )}
            {!isMiniApp && bot.status === "active" && (
              <button
                type="button"
                className="bot-payments-button"
                onClick={() => setSiteOpen(true)}
                title="Страница с ценами и документами — для банка (Казахстан)"
              >
                🌐 <span className="bot-payments-button__long">Страница</span>
                <span className="bot-payments-button__short">Сайт</span>
              </button>
            )}
            <button
              type="button"
              className="bot-delete-button"
              onClick={handleDeleteBot}
              disabled={deleting}
              aria-label="Удалить бота"
            >
              🗑
            </button>
          </div>
        </div>
        <div className="app-header__top">
          <div className="app-header__icon" aria-hidden="true">
            🛠
          </div>
          <div className="app-header__titles">
            {editingName ? (
              <input
                className="app-header__name-input"
                autoFocus
                value={bot.name ?? ""}
                placeholder={bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Название бота"}
                onChange={(e) => handleNameChange(e.target.value)}
                onBlur={() => setEditingName(false)}
                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              />
            ) : (
              <h1
                className="app-header__name"
                role="button"
                tabIndex={0}
                aria-label="Переименовать бота"
                onClick={() => setEditingName(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setEditingName(true);
                  }
                }}
              >
                <span className="app-header__name-text">
                  {bot.name || (bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Новый бот")}
                </span>
                <span className="app-header__edit-hint" aria-hidden="true">
                  ✎
                </span>
              </h1>
            )}
            <p className="app-header__greeting">
              {bot.status === "active"
                ? "Опубликован — изменения применяются сразу"
                : bot.status === "disabled"
                  ? "Остановлен — правки сохраняются как обычно"
                  : "Черновик"}
              {bot.name && bot.telegram_bot_username ? ` · @${bot.telegram_bot_username}` : ""}
              {!isMiniApp && saveStatus !== "idle" && (
                <span className={`save-status save-status--${saveStatus}`}>
                  {saveStatus === "saving" ? " · Сохраняем…" : saveStatus === "failed" ? "" : " · Сохранено"}
                  {saveStatus === "failed" && (
                    <button type="button" className="save-status__retry" onClick={retryFailedSaves}>
                      · Не сохранено — повторить
                    </button>
                  )}
                </span>
              )}
            </p>
          </div>
        </div>
      </header>

      {isMiniApp && (
        <div className="miniapp-banner">
          <p>📱 Здесь виден сценарий и кнопка публикации. Редактировать — в браузере, с телефона тоже удобно.</p>
          <button type="button" onClick={() => openExternal(`${window.location.origin}/`)}>
            Открыть в браузере →
          </button>
        </div>
      )}

      {bot.status === "active" ? (
        <div className="published-banner">
          <div className="published-banner__badge" aria-hidden="true">
            ✓
          </div>
          <div>
            <p className="published-banner__title">
              {bot.paused ? "Бот на паузе: " : "Бот работает: "}
              <strong>@{bot.telegram_bot_username}</strong>
            </p>
            {bot.paused && (
              <p className="published-banner__hint">
                Новых диалогов нет, оплаты и выдача купленного продолжают работать. Включить обратно — в меню
                Telegram-бота Bot Factory или в списке ботов.
              </p>
            )}
            <p className="published-banner__hint">
              Правки в сообщениях применяются сразу, без повторной публикации.
              {billing && paidUntilLabel(billing) && ` · ${paidUntilLabel(billing)}`}
            </p>
          </div>
        </div>
      ) : bot.status === "disabled" ? (
        /* Off the air, not gone. The editor below stays exactly as it was —
           seeing the scenario still sitting there is most of the reassurance
           this screen has to give. */
        <div className="published-banner published-banner--stopped">
          <div className="published-banner__badge" aria-hidden="true">
            ⏸
          </div>
          <div>
            <p className="published-banner__title">
              Бот остановлен{bot.telegram_bot_username ? `: @${bot.telegram_bot_username}` : ""}
            </p>
            <p className="published-banner__hint">Сценарий, настройки и заказы на месте.</p>
          </div>
        </div>
      ) : (
        !isMiniApp && (
          <>
            {/* Two versions on purpose. On a phone the long one ran to four
                lines — 80px of the 844 the canvas is fighting for — and half
                of it described a block library that only exists on a big
                screen. */}
            <p className="app-hint app-hint--narrow">
              Нажми на блок, чтобы изменить. Потяни от кружка на блоке — что дальше.
            </p>
          </>
        )
      )}

      {/* Its own box, below the status banner rather than inside it: an
          orange "период закончился" nested in the green "бот работает" card
          made the page say two opposite things at once. */}
      {billing && bot.status !== "draft" && (
        <BillingBanner botId={bot.id} billing={billing} onRenewed={handleRenewed} />
      )}

      {/* Проверка исчезала ровно там, где она нужнее всего. Чек-лист рисовался
          только у черновика, а продукт сам зовёт править живого бота —
          «правки применяются сразу, без повторной публикации». То есть сломать
          кассу или оставить кнопку без продолжения можно было молча, на боте,
          который в эту секунду открыт у покупателей. */}
      {bot.status !== "draft" && publishProblems.length > 0 && (
        <details className="live-problems" role="status">
          <summary className="live-problems__title">
            ⚠ {publishProblems.length}{" "}
            {bot.status === "active"
              ? `${plural(publishProblems.length, ["замечание", "замечания", "замечаний"])} у бота в эфире — покупатели уже это видят`
              : `${plural(publishProblems.length, ["замечание", "замечания", "замечаний"])} до следующего запуска`}
          </summary>
          <ul>
            {publishProblems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </details>
      )}

      <FlowCanvas
        bot={bot}
        onChangeContent={handleChangeContent}
        onDelete={handleDelete}
        onAdd={handleAdd}
        onSetNext={handleSetNext}
        onSetStart={handleSetStart}
        onSetPosition={handleSetPosition}
        paymentProvider={paymentSettings?.provider ?? null}
        paymentCurrencies={paymentProviders.find((p) => p.slug === paymentSettings?.provider)?.currencies ?? []}
        paymentProviderInfo={paymentProviders.find((p) => p.slug === paymentSettings?.provider) ?? null}
        paymentMissingFields={paymentSettings?.missing_fields ?? []}
        onPreview={bot.blocks.length > 0 ? () => setPreviewOpen(true) : undefined}
        subscriptionsEnabled={subscriptionsEnabled}
        onOpenPaymentSettings={() => setPaymentPanelOpen(true)}
        disabled={isMiniApp}
      />

      {bot.status === "draft" && (
        <div className="app-footer" ref={footerRef}>
          {publication?.required && !publication.paid ? (
            <PublishPaywall
              botId={bot.id}
              problems={publishProblems}
              info={publication}
              onPaid={() => setPublication((prev) => (prev ? { ...prev, paid: true } : prev))}
            />
          ) : (
            <PublishButton
              onPublish={handlePublish}
              disabled={bot.blocks.length === 0}
              orphanCount={orphanBlocks(bot.blocks, bot.start_block_id).length}
              // Тот же чек-лист, что и до оплаты. Раньше он исчезал вместе с
              // пейволлом — то есть ровно перед последним кликом, после
              // которого бота видят живые покупатели, проверка пропадала.
              problems={publishProblems}
            />
          )}
        </div>
      )}

      {bot.status === "active" && (
        <div className="app-footer" ref={footerRef}>
          <a
            className="publish-button publish-button--link"
            href={`https://t.me/${bot.telegram_bot_username}`}
            target="_blank"
            rel="noreferrer"
          >
            Открыть @{bot.telegram_bot_username} →
          </a>
        </div>
      )}

      {siteOpen && <SitePanel botId={bot.id} onClose={() => setSiteOpen(false)} />}

      {profileOpen && (
        <BotProfilePanel botId={bot.id} botUsername={bot.telegram_bot_username ?? ""} onClose={() => setProfileOpen(false)} />
      )}

      {paymentPanelOpen && (
        <PaymentSettingsPanel
          botId={bot.id}
          onClose={() => setPaymentPanelOpen(false)}
          onSaved={(settings) => setPaymentSettings(settings)}
          onOpenSales={() => {
            setPaymentPanelOpen(false);
            setSalesPanelOpen(true);
          }}
        />
      )}

      {salesPanelOpen && (
        <SalesPanel botId={bot.id} onClose={() => setSalesPanelOpen(false)} onOrdersChanged={setSales} />
      )}

      {previewOpen && <LivePreview bot={bot} botName={bot.name || bot.telegram_bot_username || ""} onClose={() => setPreviewOpen(false)} />}
    </div>
  );
}
