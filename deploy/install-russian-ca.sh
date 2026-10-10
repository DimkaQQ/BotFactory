#!/usr/bin/env bash
# Сертификаты Минцифры (Russian Trusted Root CA + Sub CA) для запросов к API Т-Банка.
#
# Банк переходит на эти сертификаты, а в хранилище certifi, которым пользуется Python в
# контейнере, их нет — без них запросы к securepay.tinkoff.ru падают с ошибкой проверки TLS.
#
# Скрипт ТОЛЬКО скачивает два файла в ./certs/russian_trusted.pem и ничего не перезапускает
# и не трогает. Дальше: TBANK_CA_BUNDLE=/certs/russian_trusted.pem в .env и пересоздать api и worker
# (bfdeploy --restart или `docker compose up -d --no-deps --force-recreate api worker`).
#
# Сверь отпечатки, которые скрипт напечатает, с официальной страницей Госуслуг/Минцифры:
# доверять корневому сертификату нужно осознанно, а не потому, что он скачался.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p certs
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

ROOT_URL="https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt"
SUB_URL="https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt"

curl -fsSL "$ROOT_URL" -o "$tmp/root.crt"
curl -fsSL "$SUB_URL" -o "$tmp/sub.crt"

for f in root sub; do
  # Файл должен быть настоящим PEM-сертификатом, а не страницей с ошибкой.
  openssl x509 -in "$tmp/$f.crt" -noout >/dev/null 2>&1 || { echo "$f.crt — не сертификат PEM, стоп" >&2; exit 1; }
  echo "== $f"
  openssl x509 -in "$tmp/$f.crt" -noout -subject -enddate -fingerprint -sha256
done

cat "$tmp/root.crt" "$tmp/sub.crt" > certs/russian_trusted.pem
chmod 644 certs/russian_trusted.pem
echo
echo "Готово: certs/russian_trusted.pem. Сверь отпечатки выше, затем добавь в .env:"
echo "  TBANK_CA_BUNDLE=/certs/russian_trusted.pem"
echo "и пересоздай api и worker."
