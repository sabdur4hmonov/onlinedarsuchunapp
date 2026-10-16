# Backend — himoyalangan kurs platformasi

FastAPI + PostgreSQL. Bu yerda: foydalanuvchilar, kurslar, qurilma bog'lash (maks. 2 ta),
bitta aktiv sessiya, rozilik (consent), audit log, darslar va DRM video (VdoCipher).

---

## 1. Kerakli dasturlar (bir marta o'rnatiladi)

| Dastur | Qayerdan | Tekshirish (PowerShell'da) |
|---|---|---|
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ | `docker --version` |
| **Python 3.12** | https://www.python.org/downloads/ (o'rnatishda **"Add python.exe to PATH"** ni belgilang) | `py -3.12 --version` |
| **Git** | https://git-scm.com/download/win | `git --version` |

Docker Desktop **ochiq va ishlab turgan** bo'lishi kerak (pastki o'ng burchakda kit belgisi yashil).

---

## 2. Ishga tushirish — qadam-baqadam

Hamma buyruqlar **PowerShell**'da. Papka nomida bo'sh joy bor, shuning uchun qo'shtirnoq shart.

### 2.1. Backend papkasiga o'tish

```powershell
cd "D:\Coding projects\onlinedarsuchunapp\backend"
```

### 2.2. `.env` faylini yaratish

```powershell
copy .env.example .env
```

Keyin `.env` ni Notepad yoki VS Code'da oching va o'zgartiring:

- `POSTGRES_PASSWORD` — o'zingiz o'ylab topgan kuchli parol.
  **Shu parolni** `DATABASE_URL` va `TEST_DATABASE_URL` ichidagi `change-me-strong-password` o'rniga ham yozing.
- `JWT_SECRET` — uzun tasodifiy qator. Uni shunday olish mumkin:

  ```powershell
  py -3.12 -c "import secrets; print(secrets.token_urlsafe(64))"
  ```

> `.env` — maxfiy fayl. U `.gitignore`'da, GitHub'ga **hech qachon** yuklanmaydi.

### 2.3. PostgreSQL'ni Docker'da ishga tushirish

```powershell
docker compose up -d
docker compose ps
```

`STATUS` ustunida `healthy` chiqsa — baza tayyor. Birinchi ishga tushishda ikkita baza yaratiladi:
`course_platform` (asosiy) va `course_platform_test` (testlar uchun).

### 2.4. Virtual muhit (venv) va kutubxonalar

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Muvaffaqiyatli faollashsa, qator boshida `(.venv)` paydo bo'ladi.
Har safar yangi PowerShell oynasi ochganda `.\.venv\Scripts\Activate.ps1` ni qayta yozing.

> **"running scripts is disabled on this system"** xatosi chiqsa, bir marta shuni bajaring
> (faqat sizning foydalanuvchingiz uchun ruxsat beradi), so'ng faollashtirishni qaytaring:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 2.5. Migratsiya (jadvallarni yaratish)

```powershell
alembic upgrade head
```

### 2.6. Birinchi o'qituvchini yaratish

O'qituvchilar ochiq ro'yxatdan o'ta olmaydi, ular shu buyruq bilan yaratiladi (parol so'raladi, ekranda ko'rinmaydi):

```powershell
python -m app.cli create-teacher --phone +998901234567 --name "Ali Valiyev"
```

### 2.7. Serverni ishga tushirish

```powershell
uvicorn app.main:app --reload
```

Brauzerda oching: **http://127.0.0.1:8000/docs** — barcha endpointlarni shu yerda sinab ko'rish mumkin.
To'xtatish: `Ctrl + C`.

### 2.8. Testlarni ishga tushirish

```powershell
pytest
```

Oxirida `passed` va qizil `failed` yo'qligi — hammasi joyida.
Testlar **faqat** `course_platform_test` bazasini ishlatadi va har safar uni tozalaydi.

---

## 3. Qanday ishlaydi (mobil app uchun qisqacha)

Har bir so'rovda app o'zining unikal qurilma ID'sini yuboradi: header `X-Device-ID` (8–128 belgi).

**Student login oqimi:**

1. `POST /auth/login` `{phone, password}` →
   - qurilma allaqachon bog'langan bo'lsa: `{"status": "ok", "access_token", "refresh_token", ...}`
   - yangi qurilma va joy bor bo'lsa: `{"status": "device_binding_required", "binding_token", "message"}`
     → app foydalanuvchidan so'raydi: *"Bu akkauntga faqat 2 ta qurilma bog'lay olasiz, bu qurilmani bog'laysizmi?"*
   - 2 ta qurilma allaqachon bog'langan bo'lsa: `403 device_limit_reached`
2. "Ha" bosilsa: `POST /auth/devices/bind` `{binding_token, device_name, platform}` → tokenlar.
3. Himoyalangan so'rovlar: `Authorization: Bearer <access_token>` + `X-Device-ID`.
4. Access token 15 daqiqa yashaydi. Tugaganda: `POST /auth/refresh` `{refresh_token}` →
   **yangi** juft token (eski refresh token endi ishlamaydi — rotation).

**Qoidalar:**

- Studentda bir vaqtda faqat 1 ta aktiv sessiya: yangi login oldingi barcha sessiyalarni darhol o'chiradi.
- Har so'rovda tekshiriladi: token, sessiya o'chirilmaganmi, `X-Device-ID` sessiyaga mosmi, qurilma hali bog'langanmi. Biror narsa mos kelmasa — `401`.
- Qurilmani faqat studentning kursi egasi bo'lgan o'qituvchi reset qila oladi:
  `POST /teacher/students/{student_id}/devices/reset` (`{}` — hammasi, `{"device_id": "<uuid>"}` — bittasi).
- O'qituvchilarga qurilma cheklovi va "1 sessiya" qoidasi qo'llanmaydi.
- Bitta qurilma bir vaqtda faqat **bitta** student akkauntiga bog'langan bo'lishi mumkin.
  Boshqa akkauntdagi qurilmadan kirish/bog'lash — `409 device_already_bound_to_other_account`.
  O'qituvchi reset qilsa, qurilma bo'shaydi.
- Eski (allaqachon almashtirilgan) refresh token qayta kelsa — bu o'g'irlik belgisi:
  foydalanuvchining **barcha** sessiyalari yopiladi va hammasi qaytadan login qiladi.
  Shuning uchun mobil app bir vaqtda faqat **bitta** refresh so'rovi yuborishi kerak.
- Kurs kontenti (`GET /courses/{id}/content`) `camera` va `data_processing` roziligisiz `403 consent_required` qaytaradi.
  Rozilik: `POST /consents` `{"type": "camera"}`.
- Login'ga limit: bitta IP yoki bitta telefon uchun daqiqasiga 5 urinish (`429`).
- Muhim hodisalar `audit_logs` jadvaliga yoziladi.

Xatolar formati: `{"detail": {"code": "device_limit_reached", "message": "..."}}` — app `code` bo'yicha ishlaydi.

---

## 4. Video darslar (VdoCipher)

Video servisi — **VdoCipher** (DRM, dinamik watermark, Flutter SDK). Kod `VideoProvider` interfeysi
orqali yozilgan (`app/services/video/`), boshqa servisga o'tish uchun bitta yangi klass yetarli.

### 4.1. Mock rejim (API kalit yo'q bo'lsa)

`.env` da `VDOCIPHER_API_SECRET` **bo'sh** bo'lsa, server avtomatik **MockVideoProvider** bilan ishlaydi:

- server ishga tushganda logda ogohlantirish chiqadi, `GET /health` → `"video_provider": "mock"`;
- `video-upload` soxta upload manzil qaytaradi (unga fayl yuklab bo'lmaydi — bu normal);
- `POST /teacher/lessons/{id}/sync-status` chaqirilsa, video darhol `ready` bo'ladi;
- `playback` soxta OTP qaytaradi (`mock-otp-...`). Haqiqiy DRM **yo'q** — faqat ishlab chiqish uchun.
- Testlar **har doim** mock bilan ishlaydi, `.env` da kalit bo'lsa ham.
- `ENVIRONMENT=production` bo'lsa va kalit bo'sh bo'lsa, server umuman ishga tushmaydi (xavfsizlik uchun).

### 4.2. Haqiqiy VdoCipher kalitini ulash

1. https://www.vdocipher.com saytida ro'yxatdan o'ting (sinov davri bor) va dashboard'ga kiring.
2. **Config → API Keys** bo'limida yangi API Secret yarating va nusxa oling.
3. `.env` ga qo'ying (qo'shtirnoqsiz):
   ```
   VDOCIPHER_API_SECRET=bu_yerga_kalit
   ```
4. Webhook uchun tasodifiy maxfiy qator yarating va `.env` ga yozing:
   ```powershell
   py -3.12 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   ```
   VDOCIPHER_WEBHOOK_SECRET=yaratilgan_qator
   ```
5. VdoCipher dashboard'ida (yoki ularning API'si orqali) webhook manzilini ro'yxatdan o'tkazing:
   `https://SIZNING-DOMEN/webhooks/vdocipher?token=<VDOCIPHER_WEBHOOK_SECRET>`.
   Lokal kompyuterga VdoCipher webhook yubora olmaydi — lokalda `sync-status` endpointidan foydalaning.
6. Serverni qayta ishga tushiring. `GET /health` → `"video_provider": "vdocipher"`.

> API kalit — maxfiy. Faqat `.env` da saqlang, hech kimga yubormang, kodga yozmang.

### 4.3. Oqim

**O'qituvchi:**
1. `POST /teacher/courses/{course_id}/lessons` `{title, description}` — dars yaratish (kurs oxiriga qo'shiladi).
2. `POST /teacher/lessons/{id}/video-upload` → `{upload_url, fields}`. Klient faylni **to'g'ridan-to'g'ri**
   `upload_url` ga yuklaydi (multipart POST: avval barcha `fields`, oxirida `file`). Video bizning serverdan o'tmaydi.
3. VdoCipher videoni qayta ishlab bo'lgach, webhook chaqiradi → dars `ready` bo'ladi.
   Soxta webhook: token noto'g'ri bo'lsa `401`. Token to'g'ri bo'lsa ham, status so'rov tanasidan emas,
   VdoCipher API'sidan qayta olinadi.
4. Boshqalar: `PATCH /teacher/lessons/{id}`, `DELETE /teacher/lessons/{id}`,
   `PUT /teacher/courses/{course_id}/lessons/order` `{lesson_ids: [...barcha darslar yangi tartibda]}`.

**Student:**
1. `GET /courses/{course_id}/content` — tayyor darslar ro'yxati.
2. `POST /lessons/{id}/playback` → `{otp, playback_info, expires_in}` → VdoCipher Flutter player'ga beriladi.
   Tekshiriladi: sessiya, qurilma va `X-Device-ID` (`401`), rate limit — daqiqasiga 10 ta (`429`),
   rozilik (`403 consent_required`), kursga yozilganmi (`403 not_enrolled`), dars tayyormi (`409 lesson_not_ready`).
3. OTP 5 daqiqadan ko'p yashamaydi. Videoda studentning **to'liq telefon raqami va ID'si**
   yarim shaffof holda har 5 soniyada joyini o'zgartirib turadi — dars tarqalsa, kim tarqatgani ko'rinadi.
4. Har bir playback so'rovi (ruxsat berilgan ham, rad etilgan ham) `audit_logs` ga yoziladi.

## 5. Muammolar va yechimlar

| Muammo | Yechim |
|---|---|
| `docker: command not found` yoki ulanish xatosi | Docker Desktop'ni oching, to'liq ishga tushishini kuting |
| `port is already allocated` (5432 band) | `.env` da `POSTGRES_PORT=5433` qiling va ikkala URL'dagi `5432` ni ham `5433` ga o'zgartiring |
| `password authentication failed` | Baza birinchi ishga tushgandagi parolni eslab qoladi. Ma'lumot kerak bo'lmasa: `docker compose down -v` so'ng `docker compose up -d` (**hamma ma'lumot o'chadi!**) |
| Testlarda `database "course_platform_test" does not exist` | `docker compose exec postgres createdb -U course_user course_platform_test` |
| `ModuleNotFoundError` | venv faollashtirilmagan: `.\.venv\Scripts\Activate.ps1`. Yangi versiyadan keyin: `pip install -r requirements-dev.txt` |
| Yangi versiyadan keyin baza xatolari | Migratsiyalarni qo'llang: `alembic upgrade head` |
| `RuntimeError: VDOCIPHER_API_SECRET is empty` | `ENVIRONMENT=production` da kalit majburiy. Lokalda `ENVIRONMENT=development` qiling |
| `playback` → `502 video_provider_error` | VdoCipher kaliti noto'g'ri yoki internet yo'q |

---

## 6. Papka tuzilmasi

```
backend/
  app/
    api/          endpointlar va tekshiruvlar (deps.py — har so'rovdagi token/qurilma tekshiruvi)
    core/         sozlamalar, xavfsizlik (argon2, JWT), rate limit
    db/           baza ulanishi
    models/       jadvallar (SQLAlchemy)
    schemas/      so'rov/javob formatlari (Pydantic)
    services/     biznes-mantiq: auth, qurilmalar, sessiyalar, rozilik, audit, darslar, playback
      video/      VideoProvider interfeysi: vdocipher.py (haqiqiy), mock.py (dev/test)
    cli.py        admin buyruqlar (o'qituvchi yaratish)
  alembic/        migratsiyalar
  tests/          pytest testlari
  docker-compose.yml
```
