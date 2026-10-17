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
| 2B | O'qituvchi web paneli (`teacher-panel/`, Next.js) | ✅ Tayyor |
| 2C | Jonli darslar (LiveKit) + avtomatik yozib olish → video dars | ✅ Tayyor |
| 3 | Flutter student ilovasi (`mobile/`) | ⬜ Boshlanmagan |
| 4 | Imtihonlar | ⬜ Boshlanmagan |
| 5 | ML kamera nazorati | ⬜ Boshlanmagan |
| 6 | To'lov | ⬜ Boshlanmagan |

## Oxirgi tugallangan bosqich: 2B (o'qituvchi paneli)

Tayyor va push qilingan:
- Backend: CORS (`CORS_ALLOWED_ORIGINS`), ishonchli proxy IP (`TRUSTED_PROXY_IPS`), kursni olish/tahrirlash,
  kurs o'quvchilari ro'yxati va chiqarish, kurs hodisalari jurnali, mock rejimda brauzerdan yuklash
  (`MOCK_VIDEO_UPLOAD_URL`, `/dev/mock-video-upload`), mock "kodlash" kechikishi
  (`MOCK_VIDEO_PROCESSING_SECONDS`). Backend testlari: 83 ta, hammasi o'tadi.
- Panel skeleti: BFF (`src/app/api/bff/[...path]`, `src/app/api/auth/*`), tokenlar faqat httpOnly
  `__Host-` cookie'larda, single-flight refresh (`src/lib/server/session.ts`), nonce CSP (`src/proxy.ts`),
  xavfsizlik headerlari (`next.config.ts`), barcha matnlar `src/lib/i18n/uz.ts`.
- Sahifalar: login, kurslar, kurs ichida tablar (o'quvchilar, video darslar, jonli darslar, hodisalar jurnali).
- Efir sahifasi: `src/components/studio/studio.tsx` (livekit-client).
- Playwright E2E (mock): `teacher-panel/e2e/panel.spec.ts` — 11 ta test, hammasi o'tadi (`npm run test:e2e`).
- **Haqiqiy yozuv sinovi O'TDI** (`e2e/real-recording.spec.ts`, `playwright.real.config.ts`):
  panel -> soxta kamera bilan efir -> LiveKit egress -> MinIO'da haqiqiy mp4 (10,7 MB, 75 s; ikkinchi
  marta 30 s) -> yangi dars -> `processing` -> `ready` -> mp4 MinIO'dan o'chirildi.
  Topilgan va tuzatilgan narsalar: egress Chrome'iga `disable-features: WebRtcHideLocalIpsWithMdns`
  (`backend/docker-compose.yml`), egress manifest JSON o'chirildi (`disable_manifest=True`).
  Shart: lokal yozuv faqat `LIVEKIT_NODE_IP` = Wi-Fi IP va `LIVEKIT_BIND_IP=0.0.0.0` bilan ishladi
  (`127.0.0.1` bilan egress `page load error: websocket url timeout`). Lokal `backend/.env` xavfsiz
  holatga (`127.0.0.1`) qaytarilgan.

Qayerda turibman: 2B tugadi (kod, testlar, hujjatlar push qilingan). Keyingi bosqich — 3.

## Keyingi aniq qadam: 3-bosqich — Flutter o'quvchi ilovasi (`mobile/`)

Foydalanuvchidan 3-bosqich uchun batafsil topshiriq kutiladi. Boshlashdan oldin hisobga olinadigan narsalar:
1. Backend API: `backend/app/api/routes/` (auth, consents, courses, lessons, live). Student oqimi:
   `POST /auth/login` -> `device_binding_required` -> `POST /auth/devices/bind` -> tokenlar;
   har so'rovda `Authorization` + `X-Device-ID`.
2. `X-Device-ID` ilova qayta o'rnatilganda ham o'zgarmasligi kerak (Android Keystore / iOS Keychain).
3. Refresh so'rovi bir vaqtda faqat bitta (aks holda reuse detection barcha sessiyalarni yopadi).
4. Video: VdoCipher Flutter SDK, `POST /lessons/{id}/playback` -> `otp` + `playback_info`.
5. Jonli dars: LiveKit Flutter SDK, `POST /live-sessions/{id}/join` -> token (faqat subscribe),
   `client_options` (adaptive stream, dynacast) va `watermark` (ilova o'zi video ustiga chizadi).
6. Rozilik: `POST /consents` (`camera`, `data_processing`), aks holda kontent 403 `consent_required`.

## Lokal ishga tushirish (qisqa)

- Backend: `backend/README.md`. Demo akkauntlar: `python scripts/seed_demo.py` (telefonlar fayl ichida).
- Panel: `cd teacher-panel && copy .env.example .env.local && npm install && npm run dev` → http://localhost:3000
- Panel sozlamalari: `BACKEND_URL`, `PANEL_ORIGIN`, `COOKIE_SECURE`, `CSP_CONNECT_SRC`.

## Faqat mock bilan sinalgan narsalar

- **VdoCipher** to'liq: upload, URL orqali import (`/videos/importUrl`), webhook formati, OTP/watermark
  (`VDOCIPHER_API_SECRET` hali yo'q). Kod `app/services/video/vdocipher.py` da, bilimga tayanib yozilgan.
- **Yozuvni VdoCipher'ga import qilish**: presigned URL internetdan ochiq bo'lishi kerak, lokal MinIO'ga
  VdoCipher ulana olmaydi.
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
- Egress konteyneri qayta ishga tushgandan keyingi birinchi yozuv ko'pincha yiqiladi (Chrome sovuq start,
  `page load error: websocket url timeout`); qayta urinish ishlaydi. LiveKit Cloud'da alohida tekshirish kerak.
- Lokal yozuv `127.0.0.1` media IP bilan ishlamaydi — sababi to'liq aniqlanmagan, Wi-Fi (LAN) IP kerak.
- Mobil ilova refresh so'rovini bir vaqtda faqat bitta yuborishi kerak (reuse detection).
- Lokal `backend/.env` da haqiqiy lokal LiveKit/MinIO kalitlari bor → live stack o'chiq bo'lsa,
  dars boshlash 502 beradi. Mock'ga qaytish: `LIVEKIT_API_KEY` va `LIVEKIT_API_SECRET` ni bo'shatish.
