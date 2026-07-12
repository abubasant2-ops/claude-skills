#!/usr/bin/env bash
# share_demo.sh — نشر «لفظة» مؤقتًا عبر Cloudflare Quick Tunnels لمشاركة
# رابط تجريبي مع شخص خارجي.
#
# المتطلبات قبل التشغيل:
#   - الـ backend يعمل محليًا على :8000 (انظر QUICKSTART.md خطوة 2)
#   - cloudflared و flutter و npm و python3 مثبتة
#
# لماذا ثلاثة أنفاق؟ التطبيق واللوحة يستدعيان الـ API من متصفح الزائر
# نفسه، وعنوان الـ API يُخبز وقت البناء — لذلك نفتح نفق الـ API أولًا ثم
# نعيد بناء الواجهتين موجّهتين إليه.
#
# ⚠️ الروابط عامة: أي شخص يملكها يصل إلى الـ API (لا مصادقة بعد).
#    للتجربة ببيانات تجريبية فقط، وأوقف كل شيء بـ Ctrl+C فور الانتهاء.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$(mktemp -d)"
PIDS=()

cleanup() {
  echo
  echo "⏹ إيقاف الأنفاق والخوادم…"
  [ ${#PIDS[@]} -gt 0 ] && kill "${PIDS[@]}" 2>/dev/null || true
}
trap cleanup EXIT

command -v cloudflared >/dev/null 2>&1 || {
  echo "❌ cloudflared غير مثبت."
  echo "   macOS:  brew install cloudflared"
  echo "   Linux:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
}
curl -sf -m 5 http://127.0.0.1:8000/health >/dev/null || {
  echo "❌ الـ backend لا يستجيب على :8000 — شغّله أولًا (QUICKSTART خطوة 2)."
  exit 1
}

wait_for_url() { # $1 = ملف السجل → يطبع رابط trycloudflare
  local url
  for _ in $(seq 1 60); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$1" | head -1 || true)
    [ -n "$url" ] && { echo "$url"; return 0; }
    sleep 1
  done
  return 1
}

start_tunnel() { # $1 = العنوان المحلي، $2 = اسم السجل → يطبع الرابط العام
  local log="$LOG_DIR/$2.log"
  cloudflared tunnel --url "$1" --no-autoupdate >"$log" 2>&1 &
  PIDS+=($!)
  wait_for_url "$log" || { echo "❌ تعذر فتح نفق $2 (راجع $log)" >&2; return 1; }
}

echo "▶ (1/4) نفق الـ API…"
API_URL=$(start_tunnel http://127.0.0.1:8000 api)
echo "   API: $API_URL"

echo "▶ (2/4) إعادة بناء تطبيق الويب موجّهًا للنفق، ثم خدمته على :8090…"
(cd "$ROOT/mobile" &&
  flutter build web --release --dart-define=LAFZA_API_BASE="$API_URL/api/v1")
(cd "$ROOT/mobile/build/web" && exec python3 -m http.server 8090) >/dev/null 2>&1 &
PIDS+=($!)
APP_URL=$(start_tunnel http://127.0.0.1:8090 app)
echo "   App: $APP_URL"

echo "▶ (3/4) إعادة بناء اللوحة موجّهة للنفق، ثم تشغيلها على :3000…"
(cd "$ROOT/dashboard" &&
  NEXT_PUBLIC_API_BASE="$API_URL/api/v1" npm run build >/dev/null)
(cd "$ROOT/dashboard" && exec npm start -- -p 3000) >/dev/null 2>&1 &
PIDS+=($!)
DASH_URL=$(start_tunnel http://127.0.0.1:3000 dashboard)
echo "   Dashboard: $DASH_URL"

echo
echo "✅ (4/4) جاهز — شارك هذين الرابطين:"
echo "   👶 تطبيق الطفل/الوالدين : $APP_URL"
echo "   🩺 لوحة الأخصائي         : $DASH_URL"
echo
echo "روابط trycloudflare مؤقتة وتتغير مع كل تشغيل."
echo "أبقِ هذه النافذة مفتوحة ما دامت التجربة جارية، وأوقف الكل بـ Ctrl+C."
wait
