"""Проверка платёжных способов платформы без единого платежа.

Запуск на сервере:

    docker compose exec api python -m app.platform_check

Что делает: читает `PLATFORM_PAYMENT_METHODS`, для каждого способа проверяет, что ключи
настоящие (не тестовые), и делает безвредный запрос «кто я» к самому провайдеру (Stripe:
данные аккаунта, Crypto Bot: `getMe`, Stars: `getMe` мета-бота). Деньги не двигаются.
Ключи и токены не печатаются. Выводит адреса, которые нужно вписать в кабинеты.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from app.config import get_settings
from app.services import payment_service

OK, BAD, WARN = "[ok]", "[!!]", "[??]"


def _fmt_price(minor: int, currency: str) -> str:
    if currency == "XTR":
        return f"{minor // 100} ⭐"
    return f"{minor / 100:.2f} {currency}"


async def _stripe(client: httpx.AsyncClient, creds: dict) -> list[str]:
    out: list[str] = []
    key = (creds.get("secret_key") or "").strip()
    whsec = (creds.get("webhook_secret") or "").strip()
    if key.startswith(("sk_live_", "rk_live_")):
        out.append(f"{OK} ключ боевой")
    elif key.startswith(("sk_test_", "rk_test_")):
        out.append(f"{WARN} ключ ТЕСТОВЫЙ: настоящие деньги принимать не будет")
    else:
        out.append(f"{BAD} secret_key не похож на ключ Stripe (ждём sk_live_… или sk_test_…)")
        return out
    out.append(f"{OK if whsec.startswith('whsec_') else BAD} webhook_secret {'задан' if whsec.startswith('whsec_') else 'пуст или неверный (ждём whsec_…)'}")
    try:
        resp = await client.get("https://api.stripe.com/v1/account", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        out.append(f"{WARN} Stripe недоступен с этого сервера: {type(exc).__name__}")
        return out
    if resp.status_code != 200:
        out.append(f"{BAD} Stripe не принял ключ (HTTP {resp.status_code})")
        return out
    data = resp.json()
    out.append(f"{OK} аккаунт найден, страна {data.get('country')}, приём платежей: {'включён' if data.get('charges_enabled') else 'ВЫКЛЮЧЕН (завершите анкету в Stripe)'}")
    return out


async def _cryptobot(client: httpx.AsyncClient, creds: dict, is_test: bool) -> list[str]:
    token = (creds.get("token") or "").strip()
    if not token:
        return [f"{BAD} token пуст (@CryptoBot → Crypto Pay → Create App)"]
    host = "https://testnet-pay.crypt.bot/api" if is_test else "https://pay.crypt.bot/api"
    try:
        resp = await client.get(f"{host}/getMe", headers={"Crypto-Pay-API-Token": token})
    except httpx.HTTPError as exc:
        return [f"{WARN} Crypto Bot недоступен с этого сервера: {type(exc).__name__}"]
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or not body.get("ok"):
        return [f"{BAD} Crypto Bot не принял токен (HTTP {resp.status_code})"]
    mode = "ТЕСТНЕТ (не настоящие деньги)" if is_test else "боевая сеть"
    return [f"{OK} приложение «{body['result'].get('name')}», {mode}"]


async def _stars(client: httpx.AsyncClient) -> list[str]:
    settings = get_settings()
    token = settings.meta_bot_token.strip()
    if not token:
        return [f"{BAD} META_BOT_TOKEN пуст: звёзды выставляет мета-бот"]
    api_base = (settings.telegram_api_base_url or "https://api.telegram.org").rstrip("/")
    try:
        resp = await client.get(f"{api_base}/bot{token}/getMe")
    except httpx.HTTPError as exc:
        return [f"{WARN} Telegram недоступен с этого сервера: {type(exc).__name__}"]
    if resp.status_code != 200:
        return [f"{BAD} Telegram не принял токен мета-бота (HTTP {resp.status_code})"]
    name = resp.json().get("result", {}).get("username")
    return [
        f"{OK} мета-бот @{name} отвечает; звёзды копятся на его балансе",
        f"{WARN} вывод звёзд (Fragment/TON) проверьте в Telegram заранее: BotFather → мини-приложение → ваш бот → Balance",
    ]


async def main() -> int:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    print(f"Публичный адрес: {base}")
    if "your-domain.com" in base:
        print(f"{BAD} PUBLIC_BASE_URL не задан: вебхуки и ссылки возврата будут вести на заглушку")
    if payment_service.platform_methods_misconfigured():
        print(f"{BAD} PLATFORM_PAYMENT_METHODS задан, но разобрать его нельзя: публикация отвечает 503")
        return 1
    methods = payment_service.platform_methods()
    if not methods:
        print(f"{WARN} PLATFORM_PAYMENT_METHODS пуст: запуск бота сейчас бесплатный")
        return 0
    failed = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for m in methods:
            renewal = f", подписка {_fmt_price(m.renewal_price_minor, m.currency)}" if m.renewal_price_minor else ""
            print(f"\n{m.provider}: запуск {_fmt_price(m.price_minor, m.currency)}{renewal}")
            if m.provider == "stripe":
                lines = await _stripe(client, m.credentials)
                lines.append(f"    вебхук в кабинете Stripe: {base}/webhook/pay/stripe")
            elif m.provider == "cryptobot":
                lines = await _cryptobot(client, m.credentials, m.is_test)
                lines.append(f"    вебхук в Crypto Pay → My Apps → Webhooks: {base}/webhook/pay/cryptobot")
            elif m.provider == "stars":
                lines = await _stars(client)
            else:
                lines = [f"{WARN} для этого способа отдельной проверки нет"]
            failed += sum(1 for line in lines if line.startswith(BAD))
            print("\n".join(f"  {line}" for line in lines))
    print("\nИтог:", "есть ошибки" if failed else "ошибок нет")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
