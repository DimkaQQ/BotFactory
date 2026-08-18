export type BlockType = "welcome" | "description" | "image" | "video" | "buttons" | "poll" | "delivery" | "delay";

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
  getPublicConfig: () => request<{ meta_bot_username: string }>("/config"),
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
};

export { ApiError };
