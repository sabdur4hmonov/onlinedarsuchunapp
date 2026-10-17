# O'qituvchi paneli (teacher-panel)

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. O'qituvchi shu yerda:
- kurslar yaratadi;
- o'quvchilarni qo'shadi va ularning qurilmalarini reset qiladi;
- video darslarni yuklaydi;
- jonli dars o'tkazadi;
- hodisalar jurnalini ko'radi.

---

## 1. Kerakli dasturlar

| Dastur | Qayerdan | Tekshirish (PowerShell) |
|---|---|---|
| **Node.js 22 yoki yangiroq** (LTS) | https://nodejs.org | `node --version` |
| **Ishlab turgan backend** | [`../backend/README.md`](../backend/README.md) | http://127.0.0.1:8000/health |

Panel backend'siz ishlamaydi: avval backend'ni ishga tushiring (Docker'dagi PostgreSQL + `uvicorn`).

---

## 2. Ishga tushirish — qadam-baqadam

```powershell
cd "D:\Coding projects\onlinedarsuchunapp\teacher-panel"
copy .env.example .env.local
npm install
npm run dev
```

Brauzerda oching: **http://localhost:3000**.

### Kirish uchun akkaunt

O'qituvchini backend papkasida yarating (parol so'raladi):

```powershell
cd "D:\Coding projects\onlinedarsuchunapp\backend"
python -m app.cli create-teacher --phone +998901234567 --name "Ali Valiyev"
```

Yoki faqat sinov uchun demo akkauntlarni yarating: `python scripts/seed_demo.py`.
Telefonlar va test parollari shu faylning boshida yozilgan; ularni hech qayerda haqiqiy ish uchun ishlatmang.

> Panelga **faqat o'qituvchi** kira oladi. O'quvchi kirmoqchi bo'lsa, "Bu panel faqat o'qituvchilar uchun" chiqadi.

---

## 3. Sozlamalar (`.env.local`)

| O'zgaruvchi | Nima uchun |
|---|---|
| `BACKEND_URL` | Backend manzili; panel **serveri** u bilan gaplashadi (brauzer emas) |
| `PANEL_ORIGIN` | Panelning ochiq manzili (CSRF tekshiruvi uchun) |
| `COOKIE_SECURE` | `true` qoldiring. Faqat boshqa qurilmadan oddiy `http://IP` orqali sinashda `false` |
| `CSP_CONNECT_SRC` | Brauzer ulanishi mumkin bo'lgan qo'shimcha manzillar: LiveKit (`ws://`/`wss://`) va video yuklash manzili |

`.env.local` hech qachon GitHub'ga yuklanmaydi (`.gitignore` da).

---

## 4. Xavfsizlik qanday ishlaydi (qisqacha)

- **Tokenlar brauzer JavaScript'ida yo'q.** Panel serveri (BFF: `src/app/api/...`) backend bilan o'zi gaplashadi.
  Tokenlar va qurilma ID'si `httpOnly`, `Secure`, `SameSite=Strict`, `__Host-` cookie'larda turadi.
  localStorage/sessionStorage ishlatilmaydi.
- **Refresh bir vaqtda faqat bitta**: bir nechta so'rov bir paytda kelsa ham backend'ga bitta refresh boradi.
  Natija 60 soniya umumiy ishlatiladi, shuning uchun backend'dagi reuse detection o'qituvchini chiqarib yubormaydi.
- **Panel qurilma ID'si**: har brauzer uchun barqaror `panel-...` ID, httpOnly cookie'da.
- **Headerlar**:
  - nonce asosidagi CSP (`src/proxy.ts`);
  - `X-Frame-Options: DENY` va `frame-ancestors 'none'`;
  - `Referrer-Policy`, `Permissions-Policy`;
  - HSTS faqat production'da (`next.config.ts`).
- **CSRF**: o'zgartiruvchi so'rovlarda `Origin` aniq tekshiriladi.
- **BFF faqat `teacher/...` va `auth/me` yo'llarini** backend'ga o'tkazadi.

---

## 5. Testlar

### Avtomatik E2E (mock rejim)

```powershell
npx playwright install chromium    # bir marta
npm run test:e2e
```

Test o'zi:
- 8100-portda alohida backend'ni ishga tushiradi (barcha tashqi servislar mock);
- `course_platform_e2e` bazasini har safar tozalaydi;
- 3100-portda panelning production build'ini ishga tushiradi.

Sizning 3000/8000-portdagi serverlaringizga tegmaydi. Docker'dagi PostgreSQL ishlab turishi kerak.

### Haqiqiy jonli efir va yozuv sinovi

Soxta kamera bilan haqiqiy efir → LiveKit egress → MinIO'da mp4 → video dars → mp4 o'chirilishi.
Talablar va ishga tushirish [`playwright.real.config.ts`](playwright.real.config.ts) boshida yozilgan;
lokal yozuv uchun LiveKit sozlamasi: [`../backend/README.md`](../backend/README.md), 5.2-bo'lim.

```powershell
npx playwright test -c playwright.real.config.ts
```

---

## 6. Ishlab chiqarish (production) uchun

- Faqat **HTTPS**. `PANEL_ORIGIN=https://panel.sizning-domen.uz`.
- Panel **reverse proxy (nginx va h.k.) ortida** turishi va `X-Forwarded-For` ni haqiqiy mijoz IP'si
  bilan **ustidan yozishi** shart. Next.js mijoz yuborgan headerni o'zgartirmaydi.
  Backend'da `TRUSTED_PROXY_IPS` = panel serverining IP'si, `CORS_ALLOWED_ORIGINS` = panel manzili.
- `CSP_CONNECT_SRC`: `wss://` LiveKit manzili va VdoCipher yuklash hosti.
- Refresh "bitta so'rov" himoyasi bitta Node jarayonining xotirasida. Bir nechta instance ishlatilsa —
  sticky session yoki umumiy xotira (Redis) kerak.
- Build: `npm run build`, ishga tushirish: `npm run start`.

---

## 7. Tuzilma

```
src/
  app/
    api/auth/        login / logout (BFF)
    api/bff/         backend'ga xavfsiz proxy (faqat teacher endpointlari)
    login/           kirish sahifasi
    (panel)/         login qilingan sahifalar: kurslar, kurs ichi, efir
  components/
    course/          tablar: o'quvchilar, video darslar, jonli darslar, hodisalar
    studio/          efir sahifasi (livekit-client)
    ui/              shadcn/ui komponentlari
  lib/
    i18n/uz.ts       BARCHA matnlar (rus tilini qo'shish uchun shu fayldan nusxa)
    server/          faqat serverda: cookie'lar, refresh, backend chaqiruvlari
  proxy.ts           CSP nonce + login talab qilish
e2e/                 Playwright testlari
```
