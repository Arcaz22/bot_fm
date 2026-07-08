# Midtrans Integration — Setup Guide

## 1. Tambahkan ke `.env`

```env
# --- Midtrans ---
# Ambil dari: https://dashboard.midtrans.com → Settings → Access Keys
MIDTRANS_SERVER_KEY=SB-Mid-server-xxxxxxxxxxxxxxxxxxxx   # sandbox
MIDTRANS_CLIENT_KEY=SB-Mid-client-xxxxxxxxxxxxxxxxxxxx   # sandbox
MIDTRANS_IS_PRODUCTION=false
DASHBOARD_BASE_URL=https://dashboard-finance.rampung.space

# Production (ganti prefix SB- → Mid-)
# MIDTRANS_SERVER_KEY=Mid-server-xxxxxxxxxxxxxxxxxxxx
# MIDTRANS_CLIENT_KEY=Mid-client-xxxxxxxxxxxxxxxxxxxx
# MIDTRANS_IS_PRODUCTION=true
```

## 2. Daftarkan Webhook URL di Midtrans Dashboard

Masuk ke Midtrans Dashboard → **Settings → Configuration**:

| Field | Value |
| --- | --- |
| Payment Notification URL | `https://your-domain.com/payments/webhook/midtrans` |
| Finish Redirect URL | `https://your-dashboard.com/membership?status=success` |
| Unfinish Redirect URL | `https://your-dashboard.com/membership?status=pending` |
| Error Redirect URL | `https://your-dashboard.com/membership?status=error` |

> Midtrans butuh URL **publik** (bukan localhost). Untuk development lokal, pakai [ngrok](https://ngrok.com): `ngrok http 8000`.
> Backend juga mengirim `callbacks.finish` saat membuat Snap token. Tetap isi URL di dashboard Midtrans sebagai fallback.

## 3. Install dependency baru

```bash
pip install httpx
```

`httpx` sudah sering ada di project FastAPI, tapi pastikan ada di `requirements.txt` / `pyproject.toml`.

## 4. Integrasi di Frontend Dashboard

Tambahkan Midtrans Snap.js di halaman dashboard:

```html
<!-- Sandbox -->
<script src="https://app.sandbox.midtrans.com/snap/snap.js"
        data-client-key="{{ MIDTRANS_CLIENT_KEY }}"></script>

<!-- Production -->
<script src="https://app.midtrans.com/snap/snap.js"
        data-client-key="{{ MIDTRANS_CLIENT_KEY }}"></script>
```

Lalu panggil dari JavaScript:

```js
async function handleUpgrade(planCode) {
  // 1. Minta Snap token dari FM backend
  const res = await fetch('/dashboard/membership/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_code: planCode }),
  });

  if (!res.ok) {
    alert('Gagal membuat order. Coba lagi.');
    return;
  }

  const { snap_token } = await res.json();

  // 2. Buka Midtrans Snap popup
  window.snap.pay(snap_token, {
    onSuccess: (result) => {
      console.log('Pembayaran sukses:', result);
      window.location.href = '/membership?status=success';
    },
    onPending: (result) => {
      console.log('Menunggu pembayaran:', result);
      window.location.href = '/membership?status=pending';
    },
    onError: (result) => {
      console.error('Pembayaran gagal:', result);
      alert('Pembayaran gagal. Silakan coba lagi.');
    },
    onClose: () => {
      console.log('Popup ditutup user');
    },
  });
}

// Contoh pemakaian di tombol
document.getElementById('btn-upgrade-tier1').addEventListener('click', () => {
  handleUpgrade('tier_1');
});
```

## 5. Alur Lengkap

```
User klik "Upgrade Tier 1"
  → POST /dashboard/membership/checkout { plan_code: "tier_1" }
  → FM buat MbrPayment status=pending
  → FM call Midtrans Snap API
  → Return { snap_token, redirect_url, amount, plan_name }
  → Dashboard buka Snap popup
  → User pilih metode bayar (VA, QRIS, e-wallet, dll)
  → User bayar
  → Midtrans kirim webhook ke POST /payments/webhook/midtrans
  → FM verifikasi signature SHA512
  → FM update MbrPayment → paid
  → FM cancel subscription lama + buat subscription baru active
  → User reload dashboard → plan sudah berubah
```

## 6. Testing di Sandbox

Midtrans menyediakan nomor VA dan kartu kredit test:

| Metode | Detail |
| --- | --- |
| VA BCA | Bayar berapa saja, langsung settlement |
| Kartu Kredit | `4811 1111 1111 1114`, CVV: `123`, Exp: `01/26` |
| GoPay | Gunakan tombol "Simulate Payment" di Snap popup |

Untuk trigger webhook manual dari sandbox, gunakan fitur **Trigger Notification** di Midtrans Dashboard → Transactions.

## 7. Checklist Sebelum Production

- [ ] Ganti `MIDTRANS_SERVER_KEY` dan `MIDTRANS_CLIENT_KEY` ke key production
- [ ] Set `MIDTRANS_IS_PRODUCTION=true`
- [ ] Ganti script Snap.js dari `app.sandbox` ke `app.midtrans.com`
- [ ] Pastikan webhook URL sudah terdaftar di Midtrans Dashboard production
- [ ] Test satu transaksi nyata dengan nominal kecil
- [ ] Verifikasi subscription aktif setelah webhook diterima
