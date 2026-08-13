export type BlockType = "welcome" | "description" | "buttons" | "delivery";

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
  telegram_bot_username: string | null;
  status: "draft" | "active" | "disabled";
  created_at: string;
  published_at: string | null;
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

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

let initDataProvider: () => string = () => "";

/** Called once from App.tsx after the Telegram WebApp becomes available. */
export function configureBuilderApi(getInitData: () => string) {
  initDataProvider = getInitData;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initDataProvider(),
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

export const builderApi = {
  getMe: () => request<ClientInfo>("/me"),

  listBots: () => request<Bot[]>("/bots"),
  createBot: () => request<Bot>("/bots", { method: "POST" }),
  getBot: (botId: string) => request<BotWithBlocks>(`/bots/${botId}`),

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
