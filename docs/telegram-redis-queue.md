# Telegram Redis Queue Flow

Dokumen ini menjelaskan alur antrean Redis untuk update Telegram, termasuk alasan `REDIS_URL` default dan perilaku ketika update baru masuk saat update sebelumnya belum selesai diproses.

## Konfigurasi Redis

Default konfigurasi ada di `app/core/settings.py`:

```env
REDIS_URL=redis://localhost:6379/0
```

Maknanya:

- `redis://`: koneksi memakai protokol Redis.
- `localhost`: Redis berjalan di host yang sama dengan aplikasi.
- `6379`: port default Redis.
- `/0`: database Redis index `0`.

Nilai ini adalah default untuk development lokal. Untuk Docker, staging, atau production, override lewat environment variable:

```env
REDIS_URL=redis://redis:6379/0
```

atau gunakan host Redis eksternal sesuai environment.

## Komponen Utama

Webhook Telegram tidak langsung menjalankan logic bisnis. Endpoint `/webhook` menerima update, lalu memasukkannya ke Redis queue.

Komponen yang terlibat:

- `app/interfaces/http/routers/telegram_webhook.py`: menerima update dari Telegram.
- `app/infrastructure/telegram/queue.py`: enqueue, dedupe, lock, dan worker queue.
- `main.py`: menjalankan worker saat aplikasi start.
- `app/core/di.py`: membuat Redis client dan handler untuk memproses update.

## Key Redis

Queue memakai beberapa key Redis:

| Key | Fungsi |
| --- | --- |
| `telegram:updates:ready` | Queue global berisi `chat_id` yang siap diproses worker. |
| `telegram:updates:active_users` | Set berisi `chat_id` yang sedang punya antrean aktif. |
| `telegram:updates:user:{chat_id}` | List update untuk satu chat/user tertentu. |
| `telegram:updates:dedupe:{update_id}` | Key dedupe agar update Telegram yang sama tidak diproses ulang. |
| `telegram:updates:lock:{chat_id}` | Lock per chat/user agar satu user tidak diproses paralel oleh lebih dari satu worker. |

## Alur Enqueue

Saat update masuk ke webhook:

1. Aplikasi mengambil `chat_id` dari update.
2. Aplikasi membuat dedupe key dari `update_id`.
3. Redis menjalankan script atomik:
   - Jika `telegram:updates:dedupe:{update_id}` sudah ada, update dianggap duplikat dan diabaikan.
   - Jika belum ada, update disimpan ke `telegram:updates:user:{chat_id}` dengan `RPUSH`.
   - Jika `chat_id` belum ada di `telegram:updates:active_users`, `chat_id` dimasukkan ke `telegram:updates:ready`.

Efeknya, untuk satu user yang sama, hanya ada satu penanda aktif di ready queue walaupun user tersebut mengirim banyak pesan berurutan.

## Alur Worker

Saat aplikasi start, `main.py` menjalankan sejumlah worker sesuai konfigurasi:

```env
TELEGRAM_QUEUE_WORKERS=2
```

Setiap worker:

1. Menunggu item dari `telegram:updates:ready` dengan `BLPOP`.
2. Mengambil `chat_id`.
3. Mencoba membuat lock `telegram:updates:lock:{chat_id}`.
4. Jika lock berhasil, worker memproses semua update di `telegram:updates:user:{chat_id}` satu per satu.
5. Setelah selesai, lock dihapus.
6. Jika list user kosong, `chat_id` dihapus dari `telegram:updates:active_users`.
7. Jika list user masih punya update, `chat_id` dimasukkan lagi ke `telegram:updates:ready`.

## Jika Tugas 1 Belum Selesai Lalu Tugas 2 Masuk

### User yang Sama

Misalnya user A mengirim tugas 1, lalu sebelum tugas 1 selesai user A mengirim tugas 2.

Alurnya:

1. Tugas 1 masuk ke `telegram:updates:user:{chat_id_A}`.
2. `chat_id_A` masuk ke `telegram:updates:ready`.
3. Worker mengambil `chat_id_A` dan memasang lock `telegram:updates:lock:{chat_id_A}`.
4. Worker mulai memproses tugas 1.
5. Tugas 2 masuk saat tugas 1 masih berjalan.
6. Tugas 2 ditambahkan ke list `telegram:updates:user:{chat_id_A}`.
7. Karena `chat_id_A` masih ada di `telegram:updates:active_users`, `chat_id_A` tidak dimasukkan ulang ke ready queue.
8. Setelah tugas 1 selesai, worker lanjut mengambil tugas 2 dari list user yang sama.

Kesimpulan: untuk user yang sama, tugas diproses berurutan. Tugas 2 menunggu tugas 1 selesai.

### User yang Berbeda

Misalnya user A mengirim tugas 1, lalu user B mengirim tugas 2.

Alurnya:

1. Tugas 1 masuk ke `telegram:updates:user:{chat_id_A}`.
2. Tugas 2 masuk ke `telegram:updates:user:{chat_id_B}`.
3. `chat_id_A` dan `chat_id_B` sama-sama bisa masuk ke `telegram:updates:ready`.
4. Jika ada worker kosong, keduanya bisa diproses paralel.

Kesimpulan: user berbeda bisa diproses bersamaan, dibatasi jumlah `TELEGRAM_QUEUE_WORKERS`.

## Dedupe Update

Telegram bisa mengirim update yang sama lebih dari sekali, misalnya karena webhook timeout atau retry. Queue memakai:

```env
TELEGRAM_UPDATE_DEDUPE_TTL_SECONDS=604800
```

Default `604800` detik berarti dedupe key bertahan 7 hari. Dalam periode itu, `update_id` yang sama akan diabaikan.

## Lock Per User

Lock per user memakai:

```env
TELEGRAM_USER_QUEUE_LOCK_TTL_SECONDS=300
```

Default `300` detik berarti lock otomatis expired setelah 5 menit.

Catatan penting:

- Lock ini mencegah dua worker memproses user yang sama secara paralel.
- Jika proses satu user lebih lama dari 5 menit, lock bisa expired sebelum proses selesai.
- Jika itu terjadi, secara teori worker lain bisa masuk dan memproses queue user yang sama.

Untuk proses yang bisa lama, seperti AI atau pemrosesan receipt, pertimbangkan menaikkan TTL lock atau menambahkan mekanisme lock renewal.

## Ringkasan Perilaku

| Kondisi | Perilaku |
| --- | --- |
| Update duplikat masuk | Diabaikan berdasarkan `update_id`. |
| User sama kirim banyak tugas | Diproses berurutan. |
| User berbeda kirim tugas | Bisa diproses paralel. |
| Worker lebih dari satu | Paralel antar user, bukan paralel untuk user yang sama. |
| Redis mati | Webhook gagal enqueue dan update tidak bisa diproses. |
| Proses lebih lama dari lock TTL | Ada risiko lock expired sebelum proses selesai. |
