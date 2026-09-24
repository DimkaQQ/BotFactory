export type BlockType =
  | "welcome"
  | "description"
  | "image"
  | "video"
  | "buttons"
  | "poll"
  | "delivery"
  | "payment"
  | "delay";

export interface ButtonAction {
  label: string;
  action_type: "text" | "url";
  action_value: string;
  /** The block this button's arrow points to on the flow canvas — null/unset
   * means the button is just shown, tap does nothing (Phase-1-style). */
  target_block_id?: string | null;
}

export interface BlockContent {
  text?: string;
  media_file_id?: string | null;
  media_type?: string | null;
  buttons?: ButtonAction[];
  question?: string;
  options?: string[];
  anonymous?: boolean;
  seconds?: number;
  /** Payment block: what is being sold, for how much, and what the pay
   * button says. `price` is kept as typed ("990", "990.50") — the backend
   * parses it into minor units. */
  title?: string;
  price?: string;
  currency?: string;
  button_label?: string;
  /** Payment block: charge for a period at a time rather than once.
   * Telegram Stars then bills every 30 days on its own; every other
   * provider re-invoices, which the editor says out loud. */
  subscription?: boolean;
  /** How long one paid period lasts. Ignored for Stars — Telegram supports
   * 30 days and nothing else. */
  period_days?: string | number;
  /** Delivery block: the private group or channel a buyer is let into. A
   * numeric id (-100…) or an @username. Set means the block hands out a
   * single-use invite instead of its text. */
  group_chat_id?: string;
  /** Written by the engine when a poll is sent, so an incoming answer can be
   * matched back to this block. Not edited by hand. */
  telegram_poll_id?: string;
}

export interface BotBlock {
  id: string;
  bot_id: string;
  block_type: BlockType;
  order_index: number;
  content: BlockContent;
  /** Default "what happens after this" edge — the plain arrow out of a node. */
  next_block_id: string | null;
  position_x: number;
  position_y: number;
  created_at: string;
  updated_at: string;
}

export interface Bot {
  id: string;
  client_id: string;
  name: string | null;
  telegram_bot_username: string | null;
  status: "draft" | "active" | "disabled";
  created_at: string;
  published_at: string | null;
  block_count: number;
  /** Entry point of the dialogue graph — where the "▶ Старт" node points. */
  start_block_id: string | null;
  /** End of the paid period, or null when the bot is not on a clock. */
  paid_until: string | null;
}

export interface BotWithBlocks extends Bot {
  blocks: BotBlock[];
}

export interface ClientInfo {
  id: string;
  telegram_user_id: number;
  full_name: string | null;
}

const API_BASE = "/api";
const SESSION_STORAGE_KEY = "bf_session_token";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

type AuthMode = { kind: "telegram-webapp"; getInitData: () => string } | { kind: "session-token"; token: string };

let auth: AuthMode = { kind: "telegram-webapp", getInitData: () => "" };

/** Mini App path — called once from App.tsx after window.Telegram.WebApp is ready. */
export function configureBuilderApi(getInitData: () => string) {
  auth = { kind: "telegram-webapp", getInitData };
}

/** Web login path — called after a successful Telegram Login Widget round trip, or on
 * startup to restore a token already saved in localStorage. */
export function configureSessionAuth(token: string) {
  auth = { kind: "session-token", token };
  localStorage.setItem(SESSION_STORAGE_KEY, token);
}

export function getStoredSessionToken(): string | null {
  return localStorage.getItem(SESSION_STORAGE_KEY);
}

export function clearSessionAuth() {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

function authHeaders(): Record<string, string> {
  return auth.kind === "session-token" ? { Authorization: `Bearer ${auth.token}` } : { "X-Telegram-Init-Data": auth.getInitData() };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Multipart upload — kept separate from request() because it must NOT
 * send a Content-Type header itself (the browser sets one with the right
 * multipart boundary from the FormData body; overriding it breaks parsing
 * on the server side). */
async function uploadFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export interface TelegramLoginPayload {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export const builderApi = {
  getMe: () => request<ClientInfo>("/me"),
  getPublicConfig: () => request<PublicConfig>("/config"),
  loginWithTelegram: (payload: TelegramLoginPayload) =>
    request<{ token: string }>("/auth/telegram-login", { method: "POST", body: JSON.stringify(payload) }),

  listBots: () => request<Bot[]>("/bots"),
  createBot: () => request<Bot>("/bots", { method: "POST" }),
  getBot: (botId: string) => request<BotWithBlocks>(`/bots/${botId}`),
  deleteBot: (botId: string) => request<void>(`/bots/${botId}`, { method: "DELETE" }),
  renameBot: (botId: string, name: string) =>
    request<Bot>(`/bots/${botId}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  setStartBlock: (botId: string, startBlockId: string | null) =>
    request<Bot>(`/bots/${botId}`, { method: "PATCH", body: JSON.stringify({ start_block_id: startBlockId }) }),

  publishBot: (botId: string, token: string) =>
    request<{ status: string; telegram_bot_username: string }>(`/bots/${botId}/publish`, {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  listBlocks: (botId: string) => request<BotBlock[]>(`/bots/${botId}/blocks`),

  createBlock: (
    botId: string,
    blockType: BlockType,
    content: BlockContent = {},
    position?: { x: number; y: number },
  ) =>
    request<BotBlock>(`/bots/${botId}/blocks`, {
      method: "POST",
      body: JSON.stringify({
        block_type: blockType,
        content,
        ...(position ? { position_x: position.x, position_y: position.y } : {}),
      }),
    }),

  updateBlock: (
    botId: string,
    blockId: string,
    patch: {
      content?: BlockContent;
      order_index?: number;
      next_block_id?: string | null;
      position_x?: number;
      position_y?: number;
    },
  ) =>
    request<BotBlock>(`/bots/${botId}/blocks/${blockId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteBlock: (botId: string, blockId: string) =>
    request<void>(`/bots/${botId}/blocks/${blockId}`, { method: "DELETE" }),

  uploadMedia: (botId: string, file: File) =>
    uploadFile<{ url: string; media_type: "photo" | "video" }>(`/bots/${botId}/media/upload`, file),

  reorderBlocks: (botId: string, items: { id: string; order_index: number }[]) =>
    request<BotBlock[]>(`/bots/${botId}/blocks/reorder`, {
      method: "PATCH",
      body: JSON.stringify({ items }),
    }),

  // ---- Payments ----
  listPaymentProviders: () => request<PaymentProviderCatalogue>("/payments/providers"),
  getPaymentSettings: (botId: string) => request<PaymentSettings>(`/bots/${botId}/payment-settings`),
  savePaymentSettings: (botId: string, payload: { provider: string | null; is_test: boolean; credentials?: Record<string, string> }) =>
    request<PaymentSettings>(`/bots/${botId}/payment-settings`, { method: "PUT", body: JSON.stringify(payload) }),

  getPublicationInfo: (botId: string) => request<PublicationInfo>(`/bots/${botId}/publication`),
  startPublicationCheckout: (botId: string, provider?: string) =>
    request<PaymentInfo>(`/bots/${botId}/publication-checkout`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),
  getBilling: (botId: string) => request<BillingState>(`/bots/${botId}/billing`),
  startRenewalCheckout: (botId: string, provider?: string) =>
    request<PaymentInfo>(`/bots/${botId}/renewal-checkout`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),
  getPayment: (paymentId: string) => request<PaymentInfo>(`/payments/${paymentId}`),
  listOrders: (botId: string) => request<OrdersReport>(`/bots/${botId}/orders`),
  listSubscribers: (botId: string) => request<SubscribersReport>(`/bots/${botId}/subscribers`),
  broadcast: (botId: string, blockId: string, audience: "all" | "subscribers") =>
    request<{ queued: number }>(`/bots/${botId}/broadcast`, {
      method: "POST",
      body: JSON.stringify({ block_id: blockId, audience }),
    }),
  confirmOrder: (botId: string, paymentId: string) =>
    request<{ status: string; delivered: boolean }>(`/bots/${botId}/orders/${paymentId}/confirm`, { method: "POST" }),
  rejectOrder: (botId: string, paymentId: string) =>
    request<{ status: string }>(`/bots/${botId}/orders/${paymentId}/reject`, { method: "POST" }),
};

export interface PaymentRegion {
  slug: string;
  title: string;
}

export interface PaymentProviderCatalogue {
  providers: PaymentProviderInfo[];
  /** Whether the constructor offers subscriptions at all. Off while the
   * one-off sale is being shaken out — the engine keeps the feature, the
   * editor just does not show it. */
  subscriptions_enabled?: boolean;
  /** Section headings for the provider grid, in display order. Comes from
   * the server so a new gateway needs no frontend change. */
  regions: PaymentRegion[];
}

export interface PaymentProviderInfo {
  slug: string;
  title: string;
  hint: string;
  currencies: string[];
  /** Which `PaymentRegion` this gateway is filed under. */
  region: string;
  /** Whether this gateway can take money a second time, and who initiates it.
   * "gateway" — it runs the subscription itself (Telegram Stars, Stripe);
   * "token" — the first payment saves a card and the bot charges it each
   * period (ЮKassa, CloudPayments); "none" — a fresh invoice every time. */
  recurring: "none" | "gateway" | "token";
  /** Asked once per shop, in the settings panel. */
  fields: PaymentField[];
  /** Asked per product, on the payment block itself — Lava's offerId, the
   * link a "pay by link" block points at. */
  block_fields: PaymentField[];
  /** False when the bot can't ask the provider whether a payment went
   * through, so «Я оплатил» goes to the owner to confirm instead. */
  supports_status_check: boolean;
  /** Whether this provider posts to our callback URL at all — Stars and
   * pay-by-link don't, so there is no address to paste anywhere. */
  uses_callback: boolean;
  has_test_mode: boolean;
}

export interface PaymentField {
  key: string;
  label: string;
  hint: string;
  secret: boolean;
}

export interface PaymentSettings {
  provider: string | null;
  is_test: boolean;
  /** Which credential fields already have a stored value — the values
   * themselves never leave the server. */
  filled_fields: string[];
  callback_url: string | null;
}

export interface PaymentInfo {
  id: string;
  status: "pending" | "paid" | "failed" | "refunded";
  amount_minor: number;
  currency: string;
  checkout_url: string | null;
}

/** What a browser may know before anyone has logged in. The acquirer list
 * comes from the server rather than the page so the landing's claim about
 * "17 касс" cannot drift away from the adapters that actually exist. */
export interface PublicConfig {
  meta_bot_username: string;
  payment_regions: { slug: string; title: string; gateways: string[] }[];
  gateway_count: number;
}

export interface PublicationInfo {
  required: boolean;
  paid: boolean;
  /** The first method's price — what a single-method deployment shows. */
  price_minor: number;
  currency: string;
  /** Every way to pay, each with its own price: the same publication costs
   * $9, ₸4500 and 9 USDT, which one number cannot express. */
  methods: PublicationMethod[];
  /** What keeping the bot on the air costs per period afterwards, 0 if the
   * launch is all there is. Shown *before* the launch is paid for: finding
   * out about a monthly a month later is how a refund request starts. */
  renewal_price_minor: number;
  renewal_period_days: number;
  renewal_grace_days: number;
}

export interface PublicationMethod {
  provider: string;
  title: string;
  price_minor: number;
  currency: string;
  renewal_price_minor: number;
}

/** Where a live bot stands with us. `state`: "off" — nothing is charged per
 * period; "active" — paid; "grace" — the period ended and the bot is still
 * running on borrowed time; "suspended" — off the air until it is renewed. */
export interface BillingState {
  state: "off" | "active" | "grace" | "suspended";
  paid_until: string | null;
  grace_until: string | null;
  days_left: number | null;
  price_minor: number;
  currency: string;
  period_days: number;
}

export interface OrdersReport {
  orders: Order[];
  /** One row per currency — a shop selling for 990 ₽ and 250 ⭐ has not
   * earned "1240" of anything, so these are never added together. */
  totals: { currency: string; count: number; total_minor: number }[];
  paid_count: number;
  paid_total_minor: number;
}

export interface Buyer {
  /** "Дима (@dimkaqq)" — name and @username, however much of each is known. */
  title: string;
  username: string | null;
  telegram_user_id: number;
}

export interface Order {
  id: string;
  invoice_no: number;
  status: "pending" | "paid" | "failed" | "refunded";
  amount_minor: number;
  currency: string;
  description: string;
  telegram_user_id: number | null;
  /** Who bought. Null for orders placed before the bot started recording
   * its people. */
  buyer: Buyer | null;
  created_at: string;
  paid_at: string | null;
  /** When the buyer tapped «Я оплатил» on a provider we can't verify. */
  claimed_at: string | null;
  /** Waiting on the owner to say whether the money arrived. */
  needs_confirmation: boolean;
}

/** 99000 -> "990" / 99050 -> "990.50" — prices are shown the way they were
 * entered, without a trailing ".00" nobody typed. */
export function formatAmount(amountMinor: number): string {
  const whole = Math.floor(amountMinor / 100);
  const frac = amountMinor % 100;
  return frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(2, "0")}`;
}

export { ApiError };


export interface SubscribersReport {
  subscriptions: SubscriptionRow[];
  /** Everyone who ever wrote to the bot, newest first — a subscriber list
   * exists at all only since the bot started recording its people. */
  people: PersonRow[];
  active_count: number;
}

export interface SubscriptionRow {
  id: string;
  title: string;
  status: "active" | "expired" | "cancelled";
  /** "auto" = Telegram Stars charges by itself; "renewal" = the bot
   * re-invoices and access continues only if that invoice is paid. */
  billing_mode: "auto" | "renewal";
  provider: string;
  period_days: number;
  periods_paid: number;
  amount_minor: number;
  currency: string;
  current_period_end: string;
  created_at: string;
  buyer: Buyer | null;
  telegram_user_id: number;
}

export interface PersonRow {
  telegram_user_id: number;
  title: string;
  username: string | null;
  first_seen_at: string;
  last_seen_at: string;
  blocked: boolean;
}
