# Backend — himoyalangan kurs platformasi

FastAPI + PostgreSQL. Bu yerda: foydalanuvchilar, kurslar, qurilma bog'lash (maks. 2 ta),
bitta aktiv sessiya, rozilik (consent) va audit log.

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
- Kurs kontenti (`GET /courses/{id}/content`) `camera` va `data_processing` roziligisiz `403 consent_required` qaytaradi.
  Rozilik: `POST /consents` `{"type": "camera"}`.
- Login'ga limit: bitta IP yoki bitta telefon uchun daqiqasiga 5 urinish (`429`).
- Muhim hodisalar `audit_logs` jadvaliga yoziladi.

Xatolar formati: `{"detail": {"code": "device_limit_reached", "message": "..."}}` — app `code` bo'yicha ishlaydi.

---

## 4. Muammolar va yechimlar

| Muammo | Yechim |
|---|---|
| `docker: command not found` yoki ulanish xatosi | Docker Desktop'ni oching, to'liq ishga tushishini kuting |
| `port is already allocated` (5432 band) | `.env` da `POSTGRES_PORT=5433` qiling va ikkala URL'dagi `5432` ni ham `5433` ga o'zgartiring |
| `password authentication failed` | Baza birinchi ishga tushgandagi parolni eslab qoladi. Ma'lumot kerak bo'lmasa: `docker compose down -v` so'ng `docker compose up -d` (**hamma ma'lumot o'chadi!**) |
| Testlarda `database "course_platform_test" does not exist` | `docker compose exec postgres createdb -U course_user course_platform_test` |
| `ModuleNotFoundError` | venv faollashtirilmagan: `.\.venv\Scripts\Activate.ps1` |

---

## 5. Papka tuzilmasi

```
backend/
  app/
    api/          endpointlar va tekshiruvlar (deps.py — har so'rovdagi token/qurilma tekshiruvi)
    core/         sozlamalar, xavfsizlik (argon2, JWT), rate limit
    db/           baza ulanishi
    models/       jadvallar (SQLAlchemy)
    schemas/      so'rov/javob formatlari (Pydantic)
    services/     biznes-mantiq: auth, qurilmalar, sessiyalar, rozilik, audit
    cli.py        admin buyruqlar (o'qituvchi yaratish)
  alembic/        migratsiyalar
  tests/          pytest testlari
  docker-compose.yml
```
