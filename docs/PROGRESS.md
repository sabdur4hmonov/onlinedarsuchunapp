# Loyiha holati (PROGRESS)

> Har bir sessiya ishni boshlashdan oldin shu faylni o'qiydi va har commitdan oldin yangilaydi
> (qoidalar: root'dagi `CLAUDE.md`). Bu yerda parol, kalit yoki token YOZILMAYDI —
> faqat o'zgaruvchi nomlari.

Oxirgi yangilanish: 2026-10-17

## Bosqichlar

| # | Bosqich | Holat |
|---|---|---|
| 1 | Backend asosi: auth, qurilma qoidalari, sessiyalar, rozilik, audit | ✅ Tayyor |
| 2A | Xavfsizlik tuzatishlari (1 qurilma = 1 akkaunt, refresh reuse) + video darslar, VdoCipher (`VideoProvider`) | ✅ Tayyor |
| 2B | O'qituvchi web paneli (`teacher-panel/`, Next.js) | 🟡 Jarayonda |
| 2C | Jonli darslar (LiveKit) + avtomatik yozib olish → video dars | ✅ Tayyor |
| 3 | Flutter student ilovasi (`mobile/`) | ⬜ Boshlanmagan |
| 4 | Imtihonlar | ⬜ Boshlanmagan |
| 5 | ML kamera nazorati | ⬜ Boshlanmagan |
| 6 | To'lov | ⬜ Boshlanmagan |

## Hozir nima qilinyapti (2B)

Tayyor va push qilingan:
- Backend: CORS (`CORS_ALLOWED_ORIGINS`), ishonchli proxy IP (`TRUSTED_PROXY_IPS`), kursni olish/tahrirlash,
  kurs o'quvchilari ro'yxati va chiqarish, kurs hodisalari jurnali, mock rejimda brauzerdan yuklash
  (`MOCK_VIDEO_UPLOAD_URL`, `/dev/mock-video-upload`). Backend testlari: 82 ta, hammasi o'tadi.
- Panel skeleti: BFF (`src/app/api/bff/[...path]`, `src/app/api/auth/*`), tokenlar faqat httpOnly
  `__Host-` cookie'larda, single-flight refresh (`src/lib/server/session.ts`), nonce CSP (`src/proxy.ts`),
  xavfsizlik headerlari (`next.config.ts`), barcha matnlar `src/lib/i18n/uz.ts`.
- Sahifalar: login, kurslar, kurs ichida tablar (o'quvchilar, video darslar, jonli darslar, hodisalar jurnali).
- Efir sahifasi: `src/components/studio/studio.tsx` (livekit-client).
- Playwright E2E (mock rejim): `teacher-panel/e2e/panel.spec.ts` — 11 ta test, hammasi o'tadi
  (`npm run test:e2e`; o'zi 8100-portda backend va 3100-portda panel ishga tushiradi,
  `course_platform_e2e` bazasini har safar tozalaydi).

Qayerda turibman: E2E testlar tayyor, endi **haqiqiy yozuv sinovi**.

## Keyingi aniq qadam

1. **Haqiqiy yozuv sinovi** — `teacher-panel/e2e/real-recording.spec.ts` yozish (oddiy `npm run test:e2e`
   dan chiqarilgan: `playwright.config.ts` da `testIgnore: /real-recording/`). Alohida config
   (`playwright.real.config.ts`) bilan ishga tushadi:
   - Oldindan: `cd backend && docker compose --profile live up -d`; backend 8000-portda haqiqiy
     `backend/.env` bilan (LiveKit + MinIO sozlangan, video provider mock); panel 3000-portda (`npm run dev`).
   - Chromium flaglari: `--use-fake-device-for-media-stream`, `--use-fake-ui-for-media-stream`.
   - Qadamlar: demo o'qituvchi bilan login → kurs → jonli dars rejalashtirish → efir sahifasi →
     "Darsni boshlash" → 70-90 soniya kutish → "Darsni tugatish" → `recording_status` ni kuzatish.
   - Tekshirish: MinIO'da `recordings/<live_session_id>/...mp4` paydo bo'lishi (boto3 yoki
     `docker compose exec minio ...`) va `recording_status` `processing`/`ready` ga o'tishi.
   - Ishlamasa: sababini qisqa yozib qo'yish (ko'p vaqt sarflamaslik), keyingi qadamga o'tish.
2. `teacher-panel/README.md` — Windows'da ishga tushirish (oddiy tilda), root `README.md` ni yangilash.
3. PROGRESS.md'ni yangilash, commit + push, foydalanuvchiga xulosa.

## Lokal ishga tushirish (qisqa)

- Backend: `backend/README.md`. Demo akkauntlar: `python scripts/seed_demo.py` (telefonlar fayl ichida).
- Panel: `cd teacher-panel && copy .env.example .env.local && npm install && npm run dev` → http://localhost:3000
- Panel sozlamalari: `BACKEND_URL`, `PANEL_ORIGIN`, `COOKIE_SECURE`, `CSP_CONNECT_SRC`.

## Faqat mock bilan sinalgan narsalar

- **VdoCipher** to'liq: upload, URL orqali import (`/videos/importUrl`), webhook formati, OTP/watermark
  (`VDOCIPHER_API_SECRET` hali yo'q). Kod `app/services/video/vdocipher.py` da, bilimga tayanib yozilgan.
- **Yozuvni VdoCipher'ga import qilish**: presigned URL internetdan ochiq bo'lishi kerak, lokal MinIO'ga
  VdoCipher ulana olmaydi.
- **Haqiqiy mp4 yozuv** hali olinmagan (oldingi urinish: xonada video yuboruvchi yo'q edi →
  egress "Start signal not received"; Python test-publisher LiveKit'ga ulana olmadi — sababi aniqlanmagan).
- Panelda brauzerdan VdoCipher S3'ga to'g'ridan-to'g'ri yuklash (mock endpoint orqali sinalgan).

## Ma'lum muammolar / e'tibor berish kerak

- Rate limiter va panelning single-flight refresh xotirasi bitta jarayonda (process) yashaydi →
  bir nechta instance bo'lsa Redis kerak.
- Panel ishlab chiqarishda reverse proxy ortida turishi va `X-Forwarded-For` ni ustidan yozishi shart
  (Next.js mijoz yuborgan headerni saqlab qoladi).
- `used_refresh_tokens` jadvali tozalanmaydi (eski yozuvlarni davriy o'chirish kerak).
- Hodisalar jurnali JSONB bo'yicha qidiradi, indeks yo'q — ma'lumot ko'payganda indeks kerak.
- Rasmiy `minio/minio` Docker image'lari endi tarqatilmaydi; lokal dev uchun `pgsty/minio` ishlatilgan.
- Egress uchun `shm_size: 1gb` shart (aks holda Chrome ishga tushmaydi).
- Mobil ilova refresh so'rovini bir vaqtda faqat bitta yuborishi kerak (reuse detection).
- Lokal `backend/.env` da haqiqiy lokal LiveKit/MinIO kalitlari bor → live stack o'chiq bo'lsa,
  dars boshlash 502 beradi. Mock'ga qaytish: `LIVEKIT_API_KEY` va `LIVEKIT_API_SECRET` ni bo'shatish.
