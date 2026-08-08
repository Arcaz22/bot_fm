# Dashboard Savings and Investment API Update

Dokumen ini merangkum perubahan API dashboard untuk mendukung tabungan pribadi, investasi pribadi, dan tabungan bersama.

## Model Data Baru

Transaksi tabungan/investasi sekarang dibedakan berdasarkan kontrol aset user:

- `TRANSFER` + category `Savings`: tabungan pribadi, contoh `BCA -> Tabungan`.
- `TRANSFER` + category `Investment`: aset investasi pribadi, contoh `BCA -> RDN`, `BCA -> Investasi`.
- `EXPENSE` + category `Joint Savings`: tabungan bersama/patungan yang uangnya dikirim ke orang lain.

Implikasi FE:

- `Savings` dan `Investment` jangan dimasukkan ke chart pengeluaran.
- `Joint Savings` tetap tampil di chart pengeluaran per kategori.
- Transfer tabungan/investasi tidak menurunkan total aset, hanya memindahkan saldo antar wallet.

## Endpoint Yang Berubah

### `GET /dashboard/summary`

Endpoint ini tetap kompatibel dengan response lama, tetapi menambah field berikut:

```json
{
  "total_joint_savings": 1000000,
  "total_savings": 500000,
  "total_investment": 2000000,
  "total_asset_allocation": 2500000,
  "net_after_asset_allocation": -500000
}
```

Field baru:

- `total_joint_savings`: total `EXPENSE` dengan category `Joint Savings`.
- `total_savings`: total `TRANSFER` dengan category `Savings`.
- `total_investment`: total `TRANSFER` dengan category `Investment`.
- `total_asset_allocation`: `total_savings + total_investment`.
- `net_after_asset_allocation`: `total_income - total_expense - total_asset_allocation`.

Catatan:

- `total_expense` tetap menghitung semua expense, termasuk `Joint Savings`.
- `net_cashflow` tetap `total_income - total_expense`.
- `wallet_balance` tetap total saldo semua wallet, jadi tidak turun karena `Savings`/`Investment` transfer.

Update FE yang disarankan:

- Tambahkan summary card `Nabung Pribadi` dari `total_savings`.
- Tambahkan summary card `Investasi` dari `total_investment`.
- Tambahkan summary card `Tabungan Bersama` dari `total_joint_savings`.
- Pakai `net_after_asset_allocation` jika UI ingin menampilkan sisa cash setelah pengeluaran dan alokasi aset.

### `GET /dashboard/charts/cashflow`

Setiap item chart sekarang menambah field:

```json
{
  "period": "2026-08-03",
  "income": 5000000,
  "expense": 1500000,
  "joint_savings": 1000000,
  "savings": 500000,
  "investment": 2000000,
  "asset_allocation": 2500000,
  "net": 3500000,
  "net_after_asset_allocation": 1000000
}
```

Update FE yang disarankan:

- Chart cashflow lama bisa tetap memakai `income`, `expense`, dan `net`.
- Jika ingin tampilan baru, tambahkan series `asset_allocation` atau pecah menjadi `savings` dan `investment`.
- `joint_savings` bisa dipakai sebagai highlight/subset expense, bukan sebagai transfer.

### `GET /dashboard/charts/expenses-by-category`

Tidak ada perubahan struktur response.

Perubahan perilaku:

- `Joint Savings` akan muncul sebagai salah satu kategori expense.
- `Savings` dan `Investment` tidak muncul di endpoint ini karena keduanya adalah transfer.

Update FE yang disarankan:

- Biarkan chart ini tetap sebagai chart pengeluaran.
- Pastikan legend/category dapat menampilkan label `Joint Savings`.

## Endpoint Baru

### `GET /dashboard/charts/asset-allocation`

Endpoint baru untuk chart tabungan dan investasi pribadi.

Query params:

- `start_date`: optional, format `YYYY-MM-DD`.
- `end_date`: optional, format `YYYY-MM-DD`.

Response:

```json
{
  "chart": "donut",
  "items": [
    {
      "category": "Investment",
      "target_wallet": "RDN",
      "amount": 2000000
    },
    {
      "category": "Savings",
      "target_wallet": "Tabungan",
      "amount": 500000
    }
  ],
  "total": 2500000
}
```

Update FE yang disarankan:

- Buat chart baru `Tabungan & Investasi`.
- Gunakan `target_wallet` untuk label utama jika ingin menampilkan tujuan aset: `RDN`, `Tabungan`, `Investasi`, `Stockbit`, dan seterusnya.
- Gunakan `category` untuk grouping warna besar: `Savings` vs `Investment`.
- Jangan gabungkan endpoint ini ke chart pengeluaran per kategori.

## Recent Transactions

### `GET /dashboard/recent-transactions`

Tidak ada perubahan struktur response, tetapi FE perlu siap menerima:

- `type: "transfer"` dengan `category: "Savings"` dan `target_wallet: "Tabungan"`.
- `type: "transfer"` dengan `category: "Investment"` dan target seperti `RDN` atau `Investasi`.
- `type: "expense"` dengan `category: "Joint Savings"` dan `target_wallet: null`.

Update FE yang disarankan:

- Tampilkan transfer tabungan/investasi dengan ikon transfer/aset, bukan ikon expense.
- Untuk transfer, tampilkan format wallet `source -> target`.
- Untuk `Joint Savings`, tampilkan seperti expense biasa.

## Checklist FE

- Tambahkan label kategori `Joint Savings`, `Savings`, dan `Investment`.
- Pastikan chart expense tetap hanya memakai `/dashboard/charts/expenses-by-category`.
- Tambahkan chart baru memakai `/dashboard/charts/asset-allocation`.
- Tambahkan summary cards dari field baru `/dashboard/summary`.
- Update mapping warna agar `Savings`, `Investment`, dan `Joint Savings` mudah dibedakan.
- Pastikan recent transaction mendukung target wallet untuk transfer aset.
