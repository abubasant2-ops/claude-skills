# QUICKSTART — تشغيل «لفظة» كاملاً على جهازك

دليل خطوة بخطوة لتشغيل المكوّنات الثلاثة محلياً:
قاعدة البيانات → الـ Backend (FastAPI) → تطبيق Flutter + لوحة الأخصائي (Next.js).

## المتطلبات

| الأداة | الإصدار |
|---|---|
| Python | 3.11 أو أحدث |
| PostgreSQL | 15 أو أحدث |
| Flutter SDK | 3.44 (قناة stable) أو أحدث |
| Node.js + npm | Node 20 أو أحدث (للوحة الأخصائي فقط) |

---

## 1) قاعدة البيانات (PostgreSQL)

شغّل الخدمة:

```bash
# Linux (Debian/Ubuntu)
sudo service postgresql start
# macOS (Homebrew)
brew services start postgresql@16
```

أنشئ المستخدم والقاعدة (مرة واحدة):

```bash
sudo -u postgres psql \
  -c "CREATE USER lafza WITH PASSWORD 'lafza';" \
  -c "CREATE DATABASE lafza OWNER lafza;"

# اختياري — قاعدة منفصلة لتشغيل اختبارات الـ backend:
sudo -u postgres psql -c "CREATE DATABASE lafza_test OWNER lafza;"
```

تحقق:

```bash
PGPASSWORD=lafza psql -h localhost -U lafza -d lafza -c "SELECT 1;"
```

---

## 2) الـ Backend (FastAPI)

```bash
cd lafza/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# تطبيق الـ migrations (ينشئ كل الجداول)
.venv/bin/alembic upgrade head

# تشغيل الخادم — استخدم 0.0.0.0 إذا سيتصل به جهاز/محاكي خارجي
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

تحقق:

```bash
curl http://127.0.0.1:8000/health        # → {"status":"ok"}
# توثيق الـ API التفاعلي: http://127.0.0.1:8000/docs
```

تشغيل الاختبارات (يتطلب قاعدة `lafza_test`):

```bash
.venv/bin/python -m pytest
```

### متغيرات البيئة (Backend)

كلها **اختيارية** — القيم الافتراضية تناسب الإعداد أعلاه. يمكن وضعها في
ملف `lafza/backend/.env` أو تصديرها في الطرفية:

| المتغير | الافتراضي | الوصف |
|---|---|---|
| `LAFZA_POSTGRES_HOST` | `localhost` | مضيف قاعدة البيانات |
| `LAFZA_POSTGRES_PORT` | `5432` | المنفذ |
| `LAFZA_POSTGRES_USER` | `lafza` | المستخدم |
| `LAFZA_POSTGRES_PASSWORD` | `lafza` | كلمة المرور |
| `LAFZA_POSTGRES_DB` | `lafza` | اسم القاعدة |

---

## 3) تطبيق Flutter (الطفل + الوالدين)

```bash
cd lafza/mobile
flutter pub get
flutter test          # اختياري: 12 اختباراً يجب أن تنجح
```

عنوان الـ API يُمرَّر وقت البناء عبر `--dart-define=LAFZA_API_BASE=...`
(الافتراضي: `http://127.0.0.1:8000/api/v1`). اختر حسب وجهة التشغيل:

### أ. محاكي أندرويد

المحاكي يرى جهازك على العنوان الخاص `10.0.2.2`:

```bash
flutter run --dart-define=LAFZA_API_BASE=http://10.0.2.2:8000/api/v1
```

### ب. محاكي iOS

`localhost` يعمل مباشرة — لا حاجة لأي تمرير:

```bash
flutter run
```

### ج. جهاز حقيقي (على نفس شبكة الـ Wi-Fi)

1. اعرف عنوان جهازك على الشبكة (مثلاً `192.168.1.10`):
   `ip addr` على لينكس أو `ipconfig getifaddr en0` على ماك.
2. تأكد أن uvicorn يعمل بـ `--host 0.0.0.0` (كما في الخطوة 2).
3. شغّل:

```bash
flutter run --dart-define=LAFZA_API_BASE=http://192.168.1.10:8000/api/v1
```

> **ملاحظة أندرويد:** الاتصال بـ `http` غير المشفّر مسموح في **بناءات
> التطوير (debug) فقط** — مفعّل مسبقاً في
> `android/app/src/debug/AndroidManifest.xml`. بناءات release تتطلب https.

### د. المتصفح (أسرع طريقة للتجربة)

```bash
flutter run -d chrome
```

> أذونات الميكروفون مطلوبة للتسجيل (يطلبها التطبيق/المتصفح عند أول استخدام)،
> ويسبقها داخل التطبيق حوار موافقة وليّ الأمر.

---

## 4) لوحة الأخصائي (Next.js)

```bash
cd lafza/dashboard
npm install
npm run dev           # http://localhost:3000
```

### متغير البيئة (Dashboard)

| المتغير | الافتراضي | متى تغيّره |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000/api/v1` | إذا كان الـ backend على عنوان آخر — ضعه في `lafza/dashboard/.env.local` |

---

## 5) تحقق سريع: الفحص المبدئي من التطبيق حتى قاعدة البيانات

1. شغّل القاعدة والـ backend (الخطوتان 1 و2).
2. افتح التطبيق → «هَيَّا نَبْدَأ» → أيقونة العائلة (أعلى اليسار) →
   بطاقة **«الفحص المبدئي»**.
3. أجب عن الأسئلة ثم اضغط **«عرض النتيجة»** — ستظهر الشدة (0–4)
   بإشارة مرورية وتوصية عربية.
4. تأكد أن التقييم وصل القاعدة:

```bash
PGPASSWORD=lafza psql -h localhost -U lafza -d lafza \
  -c "SELECT type, severity, red_flags, created_at FROM assessments ORDER BY created_at DESC LIMIT 1;"
```

> **ملاحظة:** حتى وصول المصادقة، ينشئ التطبيق عند أول استخدام حساباً
> تجريبياً (وليّ أمر → طفل → جلسة) تلقائياً؛ كل ما تفعله في التطبيق
> يُسجَّل على هذا الطفل، وتراه لوحة الأخصائي في قائمة الحالات.
