# Ish qoidalari (har bir sessiya uchun)

1. **Ish boshlashdan oldin** `docs/PROGRESS.md` ni o'qi: bosqichlar, qayerda to'xtalgan, keyingi aniq qadam.
2. **Har bir mantiqiy qadamdan keyin (har commitdan oldin)** `docs/PROGRESS.md` ni yangila:
   nima qilindi, qayerda turibman, keyingi aniq qadam (yangi sessiya hech narsa so'ramasdan
   davom eta oladigan darajada aniq).
3. **Limit tugashi yaqin bo'lsa yoki ish to'xtasa** — birinchi navbatda `docs/PROGRESS.md` ga
   "qayerda to'xtadim, keyingi aniq qadam" ni yoz, keyin commit + push.
4. **Kichik qismlarda commit + push** qil, hammasini oxiriga qoldirma. Commit xabarlari inglizcha.
5. **`.env`, `.env.local` va boshqa secretlar hech qachon commit qilinmaydi.** PROGRESS.md va boshqa
   hujjatlarda parol/kalit/token yozilmaydi — faqat o'zgaruvchi nomlari. Har commitdan oldin
   staged fayllarda `.env` yo'qligini tekshir.
6. **GitHub login so'ralsa — to'xta** va foydalanuvchiga ayt; token yoki parol kiritishga urinma.
7. Mavjud testlarni buzma: backend `cd backend && pytest`, panel `cd teacher-panel && npm run test:e2e`.

Loyiha tuzilmasi: `backend/` (FastAPI), `teacher-panel/` (Next.js), `mobile/` (Flutter, keyinroq).
Batafsil: `README.md`, `backend/README.md`, `teacher-panel/README.md`.
