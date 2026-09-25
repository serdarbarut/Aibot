# Servis Kartı — AI Marketing Platform (Aibot)

**Proje durduruldu (2026-09-25, Serdar'ın kararı).** Bu projede geliştirmeye devam edilmeyecek; aşağıdaki açık işler yapılmadan kalır.

Bu dosya oturumlar arası devir içindir. Yeni bir oturum önce bunu okur.
Doğruluk sırası: **kod (`dosya:satır`)** → bu kart → geri kalan her şey (eski ADR'ler, `.planning/`, issue'lar) yalnızca geçmiştir, kaynak gösterilmez.

Son güncelleme: 2026-09-25. Test: 92 geçiyor.

---

## Uzaktan depolar

| Remote | Adres | Not |
|---|---|---|
| `origin` | `DSMPromo/Aibot` | Orijinal repo. **Buraya push edilmez.** |
| `fork` | `serdarbarut/Aibot` | Serdar'ın fork'u. `git push fork master` |

Push durumu: `e9b5510`'a kadar her şey `fork`'a gönderildi (2026-09-25).

## Nasıl çalıştırılır

```bash
cd ~/Desktop/githubrepos/Aibot
cp .env.example .env          # yalnızca ilk seferde; SECRET_KEY / ENCRYPTION_KEY üretilmeli (README)
docker compose up -d --build  # migrate servisi tabloları kurar, sonra api + worker açılır
(cd frontend && npm install && npm run build)   # Caddy frontend/dist'i sunar
docker compose restart caddy
```

- Arayüz: https://localhost (Caddy kendi imzalı sertifikayı kullanır, tarayıcı uyarısı normal)
- API dokümanı: https://localhost/api/docs (yalnızca `DEBUG=true` iken; yerel `.env`'de açık)
- Grafana: http://localhost:3001

Testler (çevrimdışı, ağ ve veritabanı yok):

```bash
docker build --target development -t aibot-backend-dev backend
docker run --rm -e ENVIRONMENT=development aibot-backend-dev python -m pytest -q
```

---

## KARAR

`S` = Serdar verdi. `K` = Claude seçti, Serdar ayrıca onaylamadı (değiştirmek isterse serbest).

| Tarih | Kim | Karar | Neden |
|---|---|---|---|
| 2026-09-23 | S | Yerel çalıştırma için Docker Desktop + `docker compose` (README yolu) | Postgres/Redis'i elle kurmaktan hafif ve README ile aynı |
| 2026-09-23 | S | Eksik `frontend/src/lib/{api,utils}.ts` dosyaları yeniden yazıldı | Dosyalar `.gitignore`'daki `lib/` kuralı yüzünden upstream'e hiç girmemişti; frontend derlenmiyordu |
| 2026-09-23 | S | "Büyük yol": sahte auth yerine gerçek kayıt/giriş/JWT | Backend iskeletti; uygulama gerçek kullanıcıyla çalışmalı |
| 2026-09-24 | S | Tablo kurulumu: **B** — başlangıç migrasyonu (`000`) + kırık zincirin onarımı (`create_all` kısayolu değil) | Üretim kalitesi, geri alınabilir; `init_db()` kısayolu sonradan yine migrasyon gerektirirdi |
| 2026-09-24 | S | `ai_usage_quotas` enum adı `plan_tier` → `ai_quota_plan_tier` | `organizations` ile aynı adı taşıyıp farklı değer listesi kullanıyordu; aynı veritabanında kurulamaz |
| 2026-09-24 | S | E-posta doğrulaması: **A** — yalnızca `ENVIRONMENT=development` iken hesap otomatik doğrulanır | Resend yapılandırılmadı; yerelde giriş yapılabilmeli |
| 2026-09-24 | S | Refresh token: **C** — rotasyon + 30 sn tolerans, `sessions`'a 2 sütun | `NotificationCenter` her 30 sn istek atıyor, token'lar `localStorage`'ı paylaşıyor: iki sekme aynı anda yeniler, tolerans olmazsa biri kullanıcıyı her yerden atar |
| 2026-09-24 | S | **Tur 4** (e-posta doğrulama, parola sıfırlama, MFA) ertelendi | Önce başka konulara bakılacak; e-posta servisi kararı gerekiyor |
| 2026-09-24 | K | Hesap kilidi: 5 başarısız denemede 15 dk | Yaygın varsayılan |
| 2026-09-24 | K | Aynı e-posta ikinci kez kayıtta 409 döner (genel benzersizlik uygulama seviyesinde) | Tabloda yalnızca `(org_id, email)` benzersiz; giriş e-postayla yapılıyor |
| 2026-09-24 | K | Süresi dolan/iptal edilen oturumlar 30 gün saklanıp silinir | Son oturum geçmişi ve geriye dönük inceleme için yeterli |
| 2026-09-24 | K | `campaign_metrics` birincil anahtarı `(id, timestamp)` yapıldı (migrasyon `001`) | TimescaleDB hypertable bölümleme sütununun anahtarda olmasını şart koşar; `001` aksi halde hiç çalışmıyordu |
| 2026-09-24 | K | `infrastructure/init-db.sql`'den enum tipleri çıkarıldı | 5'i migrasyonla çakışıyor, 3'ünü hiçbir model kullanmıyor; şemayı Alembic yönetir |
| 2026-09-24 | K | `plan_tier` AI kotasında şimdilik sabit `"free"` | Gerçek plan `starter`/`agency` ise `ai_usage_quotas` enum'u kabul etmez (bkz. Açık işler) |

---

## DURUM

Ne çalışıyor, kanıtıyla.

**Altyapı**
- `migrate` servisi `alembic upgrade head` çalıştırır; `api` ve `worker` bunu beklemez → `docker-compose.yml:24` (`service_completed_successfully`).
- Migrasyon zinciri: `000_initial_schema` → `001_metrics` → `002_add_report_schedules` → `003_add_automation_tables` → `004_session_rotation`. Boş veritabanında sıfırdan, geri alma ve tekrar yükseltme denendi.
- Clean-install denendi (2026-09-25): `docker compose down -v` (7 hacim silindi) → `up -d --build`; `migrate` `000`→`004` sırayla çalıştı, çıkış kodu 0, `alembic_version = 004_session_rotation`, `public`'te 32 tablo, 1 hypertable; `api`/`worker`/`postgres`/`redis` sağlıklı, arayüz ve `/api/docs` 200.
- Worker sağlık kontrolü `arq --check` → `docker-compose.yml:130`; aralık `backend/app/workers/settings.py:156`.

**Kimlik doğrulama** (Tur 1–3)
- Kayıt: organizasyon + ilk kullanıcı `admin`, Argon2id → `backend/app/services/auth_service.py:92`.
- Giriş, kilitleme (5 deneme / 15 dk → `:27`), sahte özetle zamanlama eşitleme → `auth_service.py:139`.
- MFA'lı hesap girişi bilerek 403 → `backend/app/api/v1/auth.py:211`.
- `get_current_user`: JWT + kullanıcı + oturum kontrolü; rol ve org veritabanından → `backend/app/middleware/auth.py:48`.
- Refresh rotasyonu + tolerans → `backend/app/services/session_service.py:92` (tolerans `:26`); şema `backend/app/models/user.py:245`.
- Eski oturum temizliği → `session_service.py:228`, günlük 03:00 UTC → `workers/settings.py:129`.
- 95 handler'daki sabit org/kullanıcı kimliği `current_user` ile değiştirildi; `app/` içinde sabit kimlik yok (test denetler).
- Çok kiracılı izolasyon canlı denendi: B kullanıcısı A'nın verisine 404 alır.

**Güvenlik düzeltmeleri**
- `GET /analytics/campaigns/{id}` artık sahiplik kontrol eder (başka org'un metriği okunabiliyordu).
- Slack webhook URL'si yalnızca `https://hooks.slack.com/services/...` → `backend/app/services/notification_service.py:700` (SSRF).
- Sabit yollar dinamik yollardan önce tanımlı → `backend/app/api/v1/alerts.py:264`; gölgelenen rota olmadığını bir test denetler.

**Frontend**
- `frontend/src/lib/api.ts`: HTTP istemcisi, 401'de tek seferlik token yenileme, sekmeler arası eşitleme (`stores/auth.ts`).
- `tsc` 0 hata, `npm run build` başarılı.
- Tarayıcıda uçtan uca denendi (2026-09-25): giriş, sayfa yenileme, bozuk access token → 4×401 + tek `/auth/refresh` + 4 yeniden deneme 200, iki sekme aynı anda yenileme (ikisi de 200, ikisi de giriş yapmış kaldı, aynı token'a eşitlendi), çıkış (`POST /auth/logout` 200, iki sekme `/login`'e düştü, `sessions` satırı `revoked`).

**Testler** (`backend/tests/`, 92 test): kimlik servisi, `get_current_user`, oturum servisi, oturum temizliği, kampanya sahipliği, Slack URL, rota güvenliği (kimliksiz açık uçların listesini kilitler).

---

## AÇIK İŞLER

Öncelik sırası benim önerimdir; karar Serdar'ındır. Şema değiştirenler onay ister.

1. **Tur 4 — e-posta doğrulama, parola sıfırlama, MFA.** Serdar erteledi. Önce e-posta servisi kararı: Resend anahtarı şu an sahte (`.env.example`). Üretimde doğrulama zorunlu ama gönderim yok → üretimde kimse giriş yapamaz. `auth.py`'de parola sıfırlama ve MFA uçları hâlâ iskelet.
2. **18 iskelet uç kimliksiz ve sahte veri dönüyor** — organizasyon davetleri, üyeler, rol değiştirme, hesap silme (`DELETE /users/me`), MFA kurulum uçları. Tam liste: `backend/tests/test_route_security.py:29` (`STUBS_PENDING_AUTH`). Gerçekleyince listeden çıkarılır (test "bayat kayıt" olarak yakalar).
3. **`plan_tier` enum'u (ŞEMA, onay gerekir).** `ai_usage_quotas.plan_tier` yalnızca `free/pro/enterprise` kabul eder (`models/ai_generation.py:165`); organizasyon planı `starter/agency` olabilir. Şimdilik sabit `"free"` → `api/v1/ai.py:132`. Seçenek: enum'u 5 değere genişletmek (migrasyon).
4. **001–003 eski migrasyonları ile modeller arasında fark (ŞEMA, onay gerekir).** `alembic check`: 58 `server_default` ve 20 `nullable` farkı, yalnızca 001–003'ün kurduğu 10 tabloda (modeller `NOT NULL`/varsayılansız, migrasyonlar varsayılanlı ve null'a izinli). Yeni 19 tabloda fark yok.
5. **İki sekme yarışında eski refresh token'ın `localStorage`'da kalma riski** (ölçülmedi). Yarışta sunucu iki farklı geçerli token üretiyor; `sessions` yalnızca bir "önceki" token tutuyor (`session_service.py:144-145`). `localStorage`'a eski olan en son yazılırsa, sonraki yenilemede (~15 dk) reddedilir ve istemcinin yedek denemesi çalışmaz (`api.ts:79`, `latest === refreshToken`) → kullanıcı çıkış yapar. Gerçek arayüzde tetiklenemedi; iki sekme aynı token'a indi ama bunun sunucudaki güncel token olduğu doğrulanamadı.

Kod içinde `TODO` sayısı: `backend/app/api` altında 78 (Tur 3 öncesi 201). Ölçüm: `grep -rn TODO backend/app/api | wc -l`.

---

## Bilinen tuzaklar

- **Hız sınırı:** kimlik uçları dakikada 5 istek (`RATE_LIMIT_AUTH`). Elle denemede 429 görürsen bir dakika bekle.
- **Kod bağlama:** `api`/`worker`/`migrate` kodu `./backend:/app:ro` ile bağlar; Python değişikliğinden sonra ilgili servisi yeniden başlatmak gerekir (`docker compose restart api worker`). Frontend için `npm run build` yeter, Caddy `frontend/dist`'i doğrudan sunar.
- **`.env`:** yerelde `DEBUG=true` (API dokümanı için); git'e girmez.
- **`requirements-dev.txt`** düzeltildi; geliştirme imajı derlenir.
