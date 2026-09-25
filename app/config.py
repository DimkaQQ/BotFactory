from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://botfactory:botfactory@localhost:5432/botfactory"

    # Meta-bot (the bot that opens the constructor Mini App)
    meta_bot_token: str = ""
    # Its @username (no @), needed client-side to render the Telegram Login
    # Widget for the standalone web version of the constructor.
    meta_bot_username: str = ""

    # Optional: base URL of a reverse proxy in front of the Telegram Bot API
    # (e.g. a Cloudflare Worker), for deployments where api.telegram.org is
    # blocked/throttled directly (common for RU-hosted servers). Leave empty
    # to talk to api.telegram.org directly. Expected to proxy requests
    # 1:1 — https://<worker>/bot<token>/<method> -> Telegram's own endpoint.
    telegram_api_base_url: str = ""

    # Public HTTPS base URL of the deployment, e.g. https://your-domain.com
    public_base_url: str = "https://your-domain.com"

    # Fernet master key used to encrypt client bot tokens at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str = ""
    # Прежние ключи, через запятую: ими только РАСШИФРОВЫВАЮТ. Нужны, чтобы
    # смену ключа можно было пережить, а не устроить катастрофу: до этого
    # ключ был один на всё — токены ботов, ключи касс клиентов, секреты
    # вебхуков, сессии веб-входа, — и на вопрос «что делать, если он утёк»
    # ответа не было вовсе. Замена ключа разом разлогинивала всех и делала
    # нечитаемыми все токены и все чужие кассы, без пути назад.
    #
    # Ротация: новый ключ в FERNET_KEY, старый — сюда, перезапуск, затем
    # `python -m app.rotate_keys` (перешифрует всё хранимое новым ключом),
    # и только после этого старый ключ можно убрать отсюда.
    fernet_keys_retired: str = ""
    # Ключ, из которого выводится `secret_token` вебхука. Пуст — берётся
    # FERNET_KEY, как было. Задать его отдельно стоит именно перед первой
    # ротацией: иначе смена FERNET_KEY меняет секреты всех вебхуков разом, и
    # Telegram продолжает слать старые, пока `refresh_all_webhooks` не
    # переставит их при следующем запуске (он это делает, но в этом окне
    # боты молчат).
    webhook_secret_key: str = ""

    # Подписки: регулярная оплата и планировщик за ней. Были выключены, пока
    # обкатывалась разовая продажа; включены обратно, потому что без них
    # продукт не закрывает самый частый сценарий своей аудитории — закрытый
    # канал за деньги в месяц. Клиент, который пришёл именно за этим, собрать
    # его не мог, а лендинг доступ в канал обещал.
    #
    # Выключение (SUBSCRIPTIONS_ENABLED=0) по-прежнему означает две вещи
    # сразу: блок оплаты перестаёт предлагать переключатель, *и* блок, уже
    # помеченный подпиской, продаётся как обычная разовая покупка — прятать
    # одну галочку мало, иначе старые блоки продолжали бы списывать по циклу,
    # которого в интерфейсе не видно. Ничего не удаляется и не мигрирует ни в
    # ту, ни в другую сторону.
    subscriptions_enabled: bool = True

    # ---- Пределы на одного клиента ----
    # Регистрация бесплатна и открыта всякому, у кого есть Telegram, а
    # создание бота и блока стоит нам строки в базе. Без потолка один
    # аккаунт заливает базу за минуты — и попутно ломает бэкап, упирая
    # архив в лимит Telegram. Числа с большим запасом над тем, что нужно
    # живому человеку: кто упрётся, тому мы поднимем руками.
    max_bots_per_client: int = 20
    max_blocks_per_bot: int = 200
    # Размер содержимого одного блока в килобайтах. Текст «Выдачи» с
    # длинным описанием — это единицы килобайт; 64 КБ уже ни на что
    # осмысленное не похожи.
    max_block_content_kb: int = 64
    # Сколько всего мегабайт загруженных файлов может держать один клиент.
    # Отдельный потолок от media_max_upload_mb: тот ограничивает один файл,
    # а без общего один аккаунт заливал по 20 МБ сколько угодно раз — ~7 ГБ
    # в минуту в тот же том, где лежит база. Кончившийся диск останавливает
    # Postgres, то есть гасит ботов всех клиентов сразу.
    media_quota_mb_per_client: int = 300
    # Через сколько часов неприкаянный файл считается мусором. Файл живёт
    # между загрузкой и сохранением блока, поэтому не «сразу»: сутки — это с
    # огромным запасом на «загрузил и ушёл пить чай».
    media_orphan_ttl_hours: int = 24

    # Часовой пояс, в котором боты называют даты покупателям и владельцам
    # («доступ до 24.10.2026»). Всё хранится в UTC и считается в UTC — это
    # правильно, — но показывать UTC человеку в UTC+6 значит иногда назвать
    # дату на сутки раньше. Имя из базы IANA: Europe/Moscow, Asia/Almaty.
    display_timezone: str = "UTC"

    # CORS - Mini App origin(s), comma separated. "*" for local dev.
    cors_origins: str = "*"

    # Where uploaded media (photos/videos attached directly, not via a
    # pasted link) land on disk. Relative paths resolve against the
    # process's cwd — /srv in the Docker image (see Dockerfile's WORKDIR),
    # mounted as a named volume in docker-compose.yml so uploads survive
    # a redeploy.
    media_upload_dir: str = "media_uploads"
    # Cap on a direct upload — Telegram itself allows much larger files,
    # but this app proxies the bytes onto local disk, so a generous-but-
    # bounded limit here. Bigger files are what the "paste a link" option
    # (still on every media block) is for.
    media_max_upload_mb: int = 20

    # ---- Платформа: платная публикация бота ----
    # How *we* get paid, as a JSON array — one entry per method the client
    # may choose at checkout. Several are needed because no single provider
    # covers everyone: cards abroad go through Stripe (which does not operate
    # in Russia or Kazakhstan and so needs a company elsewhere), local cards
    # through a local acquirer, and crypto through Crypto Bot, which needs no
    # company at all.
    #
    # Each entry carries its own price, because the same publication costs
    # $9, ₸4500 and 9 USDT — one number in one currency cannot express that.
    #
    # `renewal_price_minor` is what the bot costs per period afterwards; 0
    # (or absent) means this method sells the launch only and the bot then
    # runs forever.
    #
    #   [{"provider": "stripe",    "price_minor": 9900,   "renewal_price_minor": 990,
    #     "currency": "USD",
    #     "credentials": {"secret_key": "sk_live_…", "webhook_secret": "whsec_…"}},
    #    {"provider": "robokassa", "price_minor": 450000, "renewal_price_minor": 45000,
    #     "currency": "KZT",
    #     "credentials": {"merchant_login": "…", "password1": "…", "password2": "…"}},
    #    {"provider": "cryptobot", "price_minor": 9900,   "renewal_price_minor": 990,
    #     "currency": "USDT",
    #     "credentials": {"token": "…"}}]
    #
    # Empty falls back to the single-provider settings below, so an existing
    # deployment keeps working untouched.
    platform_payment_methods: str = ""

    # Single-method fallback, kept for deployments configured before the list
    # existed.
    platform_payment_provider: str = "test"
    # That provider's credentials as JSON, e.g.
    # {"secret_key": "sk_live_…", "webhook_secret": "whsec_…"} — one variable
    # instead of a field per provider, since each wants a different set.
    platform_payment_credentials: str = ""
    platform_payment_is_test: bool = True
    # Разрешить провайдер `test` в качестве НАШЕЙ кассы. Выключено, и это
    # предохранитель: «Тестовая оплата» помечает счёт оплаченным по открытию
    # ссылки. Для кассы клиента это давно запрещено словами «она отдаёт
    # товар без денег» — а нашу собственную не защищало ничто, при том что
    # `test` стоял дефолтом. Поставил цену, не заметил строку рядом — и
    # каждая публикация бесплатна, с аккуратной записью `paid` в базе.
    # Включать только на стенде.
    platform_allow_test_till: bool = False
    # Price of publishing one bot, in minor units (kopeks/tiyn/cents).
    # 0 disables the paywall entirely — publishing stays free until a price
    # is actually configured, so a fresh deployment is never locked.
    publication_price_minor: int = 0
    publication_currency: str = "KZT"

    # ---- Платформа: ежемесячная плата за работающего бота ----
    # What the bot costs per period once it is on the air, in the same
    # currency as the launch. 0 — the default — means there is no monthly at
    # all: the launch is paid once and the bot runs forever. Nothing here is
    # ever charged automatically; see `platform_billing` for why, and for
    # what actually happens as a period runs out.
    renewal_price_minor: int = 0
    # Length of one paid period. 30 rather than "a calendar month" because
    # the whole thing is arithmetic on a timestamp, and a period that is
    # sometimes 28 and sometimes 31 days long is a support question nobody
    # needs to answer.
    renewal_period_days: int = 30
    # After the period ends the bot keeps working for this long while the
    # owner is reminded. Only once *this* runs out does it go off the air —
    # a shop with paying customers must never be switched off the same hour
    # a card expires.
    renewal_grace_days: int = 7

    @property
    def retired_key_list(self) -> list[str]:
        return [k.strip() for k in self.fernet_keys_retired.split(",") if k.strip()]

    @property
    def webhook_key(self) -> str:
        return self.webhook_secret_key or self.fernet_key

    @property
    def webapp_url(self) -> str:
        # Same app the web version lives at — the Mini App just opens it and
        # detects at runtime that it's inside Telegram (see App.tsx).
        return self.public_base_url.rstrip("/") + "/"

    def webhook_url(self, bot_id: str) -> str:
        return f"{self.public_base_url.rstrip('/')}/webhook/{bot_id}"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
