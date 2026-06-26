# Membership Digital Plan

Dokumen ini menjelaskan rencana pemisahan fitur membership digital ke repo baru, termasuk komponen yang perlu dibuat dan perubahan yang dibutuhkan di repo Financial Management (FM).

## Tujuan

Membership dibuat sebagai service terpisah agar logic plan, subscription, payment, quota, dan entitlement tidak tercampur dengan logic finance bot.

Repo FM tetap fokus pada:

- Telegram bot.
- Wallet, kategori, transaksi, debt.
- Receipt scan dan AI parsing.
- Dashboard finance.

Repo membership menjadi source of truth untuk:

- User membership.
- Tier/plan.
- Subscription.
- Payment.
- Feature access.
- Usage quota.

## Tier Awal

Rencana tier awal:

| Tier | Target | Contoh Akses |
| --- | --- | --- |
| Free | User baru / trial | Transaksi manual, saldo, riwayat dasar, kuota AI kecil. |
| Tier 1 | User aktif personal | Kuota AI lebih besar, receipt scan, dashboard penuh. |
| Tier 2 | Power user | Kuota lebih besar, export, fitur lanjutan, prioritas fitur. |

Contoh feature key:

| Feature Key | Deskripsi |
| --- | --- |
| `transaction_manual` | Input transaksi lewat chat biasa. |
| `balance_check` | Cek saldo. |
| `history_view` | Lihat riwayat transaksi. |
| `ai_parse_transaction` | AI parsing transaksi dari teks natural language. |
| `receipt_scan` | Membaca foto struk/nota. |
| `dashboard_access` | Login dan akses dashboard. |
| `dashboard_export` | Export data dashboard. |
| `debt_tracking` | Hutang/piutang. |

## Arsitektur

Pemisahan service:

```text
membership-service
  - user membership
  - plan/tier
  - subscription
  - payment
  - feature limit
  - usage counter
  - entitlement API

fm-service
  - telegram bot
  - transaksi finance
  - wallet/category/debt
  - receipt scan
  - dashboard finance
```

Alur pengecekan akses:

```text
User kirim command/foto ke Telegram
  -> fm-service terima update
  -> fm-service cek entitlement ke membership-service
  -> membership-service balas allowed/denied + plan + remaining quota
  -> fm-service lanjut proses atau kirim pesan upgrade
```

## Repo Baru: Membership Service

Minimal komponen yang perlu dibuat:

- FastAPI app.
- PostgreSQL database.
- SQLAlchemy model.
- Alembic migration.
- Internal API key untuk komunikasi dari FM.
- Endpoint entitlement.
- Endpoint plan/subscription admin.
- Payment webhook.

Struktur awal yang disarankan:

```text
membership-service/
  app/
    core/
      settings.py
      security.py
      database.py
    domain/
      membership/
        entities.py
        rules.py
        ports.py
    application/
      services/
        entitlement_service.py
        subscription_service.py
        payment_service.py
    infrastructure/
      db/
        models.py
        repositories.py
      payment/
        provider.py
    interfaces/
      http/
        routers/
          plans.py
          subscriptions.py
          entitlements.py
          payments.py
  alembic/
  main.py
  pyproject.toml
  README.md
```

## Data Model

### `users`

Menyimpan user membership. Satu user bisa dikaitkan dengan Telegram user dari FM.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key internal membership. |
| `telegram_user_id` | bigint | ID Telegram dari `sys_telegram_user.id` di FM. |
| `phone_number` | varchar | Optional, untuk login/dashboard. |
| `email` | varchar | Optional. |
| `status` | varchar | `active`, `banned`, `deleted`. |
| `created_at` | timestamp | Waktu dibuat. |
| `updated_at` | timestamp | Waktu update. |

### `plans`

Menyimpan daftar tier.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key. |
| `code` | varchar | `free`, `tier_1`, `tier_2`. |
| `name` | varchar | Nama tampilan. |
| `price` | numeric | Harga plan. |
| `billing_period` | varchar | `monthly`, `yearly`, `lifetime`, atau `free`. |
| `is_active` | boolean | Plan bisa dipakai atau tidak. |
| `created_at` | timestamp | Waktu dibuat. |

### `plan_features`

Menyimpan fitur dan limit tiap plan.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key. |
| `plan_id` | fk | Relasi ke `plans`. |
| `feature_key` | varchar | Contoh `receipt_scan`. |
| `is_enabled` | boolean | Apakah fitur aktif untuk plan ini. |
| `limit_value` | integer | Null berarti unlimited. |
| `limit_period` | varchar | `daily`, `monthly`, `lifetime`, atau null. |

### `subscriptions`

Menyimpan subscription user.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key. |
| `user_id` | fk | Relasi ke `users`. |
| `plan_id` | fk | Relasi ke `plans`. |
| `status` | varchar | `active`, `trialing`, `expired`, `cancelled`, `pending_payment`. |
| `started_at` | timestamp | Mulai aktif. |
| `expires_at` | timestamp | Expired. Null untuk lifetime/free jika diperlukan. |
| `cancelled_at` | timestamp | Waktu cancel. |
| `created_at` | timestamp | Waktu dibuat. |

### `usage_counters`

Menyimpan pemakaian fitur yang punya quota.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key. |
| `user_id` | fk | Relasi ke `users`. |
| `feature_key` | varchar | Contoh `receipt_scan`. |
| `period_start` | date/timestamp | Awal periode quota. |
| `period_end` | date/timestamp | Akhir periode quota. |
| `used` | integer | Total pemakaian. |
| `created_at` | timestamp | Waktu dibuat. |
| `updated_at` | timestamp | Waktu update. |

Tambahkan unique constraint:

```text
user_id + feature_key + period_start + period_end
```

### `payments`

Menyimpan pembayaran atau invoice.

Kolom awal:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | bigint/uuid | Primary key. |
| `user_id` | fk | Relasi ke `users`. |
| `plan_id` | fk | Plan yang dibeli. |
| `provider` | varchar | Contoh `manual`, `midtrans`, `xendit`. |
| `provider_reference` | varchar | ID dari payment provider. |
| `amount` | numeric | Nominal pembayaran. |
| `status` | varchar | `pending`, `paid`, `failed`, `expired`, `refunded`. |
| `paid_at` | timestamp | Waktu pembayaran berhasil. |
| `created_at` | timestamp | Waktu dibuat. |

## API Membership

### Check Entitlement

Digunakan FM sebelum menjalankan fitur.

```http
POST /internal/entitlements/check
Authorization: Bearer <internal-api-key>
Content-Type: application/json
```

Request:

```json
{
  "telegram_user_id": 123456789,
  "feature_key": "receipt_scan"
}
```

Response allowed:

```json
{
  "allowed": true,
  "user_id": "user-id",
  "plan": "tier_1",
  "feature_key": "receipt_scan",
  "limit": 100,
  "used": 12,
  "remaining": 88,
  "reason": null
}
```

Response denied:

```json
{
  "allowed": false,
  "user_id": "user-id",
  "plan": "free",
  "feature_key": "receipt_scan",
  "limit": 3,
  "used": 3,
  "remaining": 0,
  "reason": "quota_exceeded"
}
```

### Consume Usage

Dipanggil FM setelah fitur benar-benar dipakai.

```http
POST /internal/entitlements/consume
Authorization: Bearer <internal-api-key>
Content-Type: application/json
```

Request:

```json
{
  "telegram_user_id": 123456789,
  "feature_key": "receipt_scan",
  "amount": 1
}
```

Response:

```json
{
  "success": true,
  "feature_key": "receipt_scan",
  "used": 13,
  "remaining": 87
}
```

Catatan: `check` dan `consume` sengaja dipisah agar FM tidak mengurangi quota jika proses gagal sebelum fitur dipakai. Untuk fitur AI, `consume` bisa dipanggil setelah call LLM berhasil atau minimal setelah request LLM benar-benar dikirim.

### Get Current Membership

Dipakai dashboard atau bot untuk menampilkan status membership.

```http
GET /internal/users/by-telegram/{telegram_user_id}/membership
Authorization: Bearer <internal-api-key>
```

Response:

```json
{
  "telegram_user_id": 123456789,
  "plan": "tier_1",
  "subscription_status": "active",
  "expires_at": "2026-07-26T00:00:00Z",
  "features": [
    {
      "feature_key": "receipt_scan",
      "enabled": true,
      "limit": 100,
      "period": "monthly",
      "used": 12,
      "remaining": 88
    }
  ]
}
```

### Payment Webhook

Dipakai payment provider untuk update status pembayaran.

```http
POST /payments/webhook/{provider}
```

Saat payment status berubah menjadi `paid`, membership service harus:

1. Validasi signature webhook.
2. Update payment menjadi `paid`.
3. Aktifkan atau perpanjang subscription user.
4. Catat audit log jika nanti dibutuhkan.

## Perubahan di Repo FM

Repo FM tidak perlu menyimpan tabel membership lengkap. Perubahan cukup di titik pengecekan akses.

### Settings

Tambahkan config di `app/core/settings.py`:

```env
MEMBERSHIP_API_URL=http://localhost:8001
MEMBERSHIP_API_KEY=change-me
```

Field Python:

```python
MEMBERSHIP_API_URL: str | None = None
MEMBERSHIP_API_KEY: str | None = None
```

### Membership Client

Buat client HTTP:

```text
app/domain/membership/ports.py
app/infrastructure/membership/client.py
app/application/services/membership_service.py
```

Tanggung jawab:

- `check_entitlement(telegram_user_id, feature_key)`.
- `consume_usage(telegram_user_id, feature_key, amount=1)`.
- Fallback behavior jika membership service down.

Rekomendasi fallback:

- Untuk development: allow jika `MEMBERSHIP_API_URL` kosong.
- Untuk production: deny fitur premium jika membership service tidak bisa dihubungi.

### Ganti Quota Lokal

Saat ini quota AI ada di:

```text
app/application/usecases/telegram.py
```

Logic yang perlu diganti:

- `settings.AI_FREE_QUOTA`.
- `settings.ai_whitelist_ids`.
- penyimpanan `ai_usage` di `user.temp_data`.

Ganti menjadi:

```text
check entitlement -> jalankan fitur -> consume usage
```

Feature key yang dipakai:

| Flow FM | Feature Key |
| --- | --- |
| Parsing transaksi teks dengan LLM | `ai_parse_transaction` |
| Foto struk/nota | `receipt_scan` |
| Export dashboard | `dashboard_export` |
| Debt tracking jika ingin dipremiumkan | `debt_tracking` |

### Pesan Upgrade

Jika access denied, bot mengirim pesan sesuai reason.

Contoh:

```text
Limit AI Free Anda sudah habis.
Upgrade ke Tier 1 atau Tier 2 untuk melanjutkan.
```

Reason yang perlu ditangani:

| Reason | Pesan |
| --- | --- |
| `feature_disabled` | Fitur ini belum tersedia di plan Anda. |
| `quota_exceeded` | Limit fitur ini sudah habis untuk periode ini. |
| `subscription_expired` | Membership Anda sudah expired. |
| `user_inactive` | Akun Anda tidak aktif. |

## Seed Data Awal

Plan awal:

```text
free
tier_1
tier_2
```

Contoh limit awal:

| Feature | Free | Tier 1 | Tier 2 |
| --- | ---: | ---: | ---: |
| `transaction_manual` | unlimited | unlimited | unlimited |
| `balance_check` | unlimited | unlimited | unlimited |
| `history_view` | 5 latest | unlimited | unlimited |
| `ai_parse_transaction` | 20/month | 500/month | 2000/month |
| `receipt_scan` | 3/month | 100/month | 500/month |
| `dashboard_access` | enabled | enabled | enabled |
| `dashboard_export` | disabled | 5/month | 50/month |
| `debt_tracking` | enabled | enabled | enabled |

Angka di atas masih bisa disesuaikan setelah ada data pemakaian real.

## Urutan Pengerjaan

### Tahap 1: Foundation Membership

- Buat repo `membership-service`.
- Setup FastAPI, settings, database, Alembic.
- Buat model `users`, `plans`, `plan_features`, `subscriptions`, `usage_counters`.
- Buat seed plan `free`, `tier_1`, `tier_2`.
- Buat endpoint `check entitlement`.
- Buat endpoint `consume usage`.

### Tahap 2: Integrasi FM

- Tambahkan `MEMBERSHIP_API_URL` dan `MEMBERSHIP_API_KEY` di FM.
- Buat membership client di FM.
- Ganti `_check_ai_quota` agar memakai entitlement API.
- Tambahkan pengecekan untuk `receipt_scan`.
- Tambahkan pesan upgrade saat denied.
- Pastikan development tetap bisa jalan saat membership service belum aktif.

### Tahap 3: Subscription Admin

- Buat endpoint untuk melihat user membership.
- Buat endpoint manual upgrade/downgrade user.
- Buat endpoint cancel subscription.
- Buat endpoint extend subscription.

Tahap ini berguna sebelum payment gateway siap, karena membership bisa dites manual.

### Tahap 4: Payment

- Pilih payment provider.
- Buat tabel `payments`.
- Buat create invoice/order.
- Buat webhook payment.
- Saat payment `paid`, aktifkan subscription.
- Tambahkan halaman/link pembayaran jika dashboard sudah siap.

### Tahap 5: Dashboard Membership

- Tampilkan plan aktif.
- Tampilkan expired date.
- Tampilkan quota usage.
- Tampilkan tombol upgrade.
- Tampilkan riwayat pembayaran.

## Keputusan Teknis yang Perlu Dipilih

Sebelum implementasi payment, tentukan:

- Payment provider: manual transfer, Midtrans, Xendit, Stripe, atau lainnya.
- Masa subscription: monthly saja atau ada yearly/lifetime.
- Apakah Free punya expired trial atau selamanya free.
- Apakah user diidentifikasi dari Telegram ID saja atau juga phone/email.
- Fallback production ketika membership service down: deny premium atau allow sementara.

## Risiko dan Catatan

- Jangan simpan quota di `temp_data` user FM untuk jangka panjang, karena sulit diaudit dan sulit reset bulanan.
- `check` dan `consume` harus aman dari race condition. Gunakan database transaction saat increment usage.
- Payment webhook harus idempotent. Webhook yang sama bisa dikirim lebih dari sekali oleh provider.
- Jangan percaya status pembayaran dari frontend. Aktivasi subscription hanya dari webhook provider atau admin internal.
- Pastikan semua endpoint internal memakai API key atau service token.

## Definisi Selesai MVP

MVP membership dianggap selesai jika:

- User Free otomatis punya limit default.
- Tier 1 dan Tier 2 bisa diaktifkan manual.
- FM bisa cek entitlement sebelum AI/receipt scan.
- Quota berkurang saat fitur dipakai.
- User mendapat pesan upgrade saat limit habis.
- Admin bisa melihat plan aktif dan usage user.
