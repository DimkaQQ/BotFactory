export type BlockType = "welcome" | "description" | "image" | "video" | "buttons" | "poll" | "delivery" | "delay";

export interface ButtonAction {
  label: string;
  action_type: "text" | "url";
  action_value: string;
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const authHeaders: Record<string, string> =
    auth.kind === "session-token" ? { Authorization: `Bearer ${auth.token}` } : { "X-Telegram-Init-Data": auth.getInitData() };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
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

  publishBot: (botId: string, token: string) =>
    request<{ status: string; telegram_bot_username: string }>(`/bots/${botId}/publish`, {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  listBlocks: (botId: string) => request<BotBlock[]>(`/bots/${botId}/blocks`),

  createBlock: (botId: string, blockType: BlockType, content: BlockContent = {}) =>
    request<BotBlock>(`/bots/${botId}/blocks`, {
      method: "POST",
      body: JSON.stringify({ block_type: blockType, content }),
    }),

  updateBlock: (botId: string, blockId: string, patch: { content?: BlockContent; order_index?: number }) =>
    request<BotBlock>(`/bots/${botId}/blocks/${blockId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteBlock: (botId: string, blockId: string) =>
    request<void>(`/bots/${botId}/blocks/${blockId}`, { method: "DELETE" }),

  reorderBlocks: (botId: string, items: { id: string; order_index: number }[]) =>
    request<BotBlock[]>(`/bots/${botId}/blocks/reorder`, {
      method: "PATCH",
      body: JSON.stringify({ items }),
    }),
};

export { ApiError };
