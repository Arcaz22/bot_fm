# Rangkuman Deployment Finance Bot ke STB HG680P

> **Perangkat:** STB HG680P · Armbian di microSD 16GB  
> **Stack:** FastAPI + Supabase + Cloudflared + Docker

---

## 1. Analisis Awal & Keputusan Arsitektur

### Masalah yang Ditemukan
- **Port mismatch** — `.env` pakai `8000`, Dockerfile pakai `8080`
- **Cloudflare config salah** — `tunnel:` diisi nama file `.json`, harusnya Tunnel ID saja
- **Build di STB = merusak microSD** — write cycle terbatas, build dependency sangat write-intensive

### Keputusan
- ✅ **Build di PC** (cross-compile ARM64), push ke registry
- ✅ **STB hanya pull & run** — tidak pernah build
- ✅ **Source code tidak perlu ada di STB** — hanya config files
- ✅ **Pakai `/opt/finance-bot/`** sebagai folder deployment di STB

---

## 2. Struktur Folder

### Di PC (source code + build)
```
~/project/portofolio/bot/fm/
├── main.py
├── app/
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── .dockerignore
├── docker-compose.yml
├── .env
└── cloudflared/
    ├── config.yml
    └── 80a3ea78-xxxx.json
```

### Di STB `/opt/finance-bot/` (config only)
```
/opt/finance-bot/
├── docker-compose.yml
├── .env
└── cloudflared/
    ├── config.yml
    └── 80a3ea78-xxxx.json
```

> Source code **tidak ada** di STB — sudah ada di dalam Docker image.

---

## 3. Perbaikan File Konfigurasi

### Dockerfile (fix port 8080 → 8000)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
services:
  finance-bot:
    image: ghcr.io/arcaz22/finance-bot:latest
    container_name: finance-bot
    restart: unless-stopped
    env_file: .env
    ports:
      - "8000:8000"

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --config /etc/cloudflared/config.yml run
    volumes:
      - ./cloudflared:/etc/cloudflared
    depends_on:
      - finance-bot
```

### cloudflared/config.yml (fix tunnel ID)
```yaml
# SALAH — jangan pakai nama file .json
# tunnel: 80a3ea78-9e68-4c40-af98-257d7c2b5255.json

# BENAR — pakai Tunnel ID saja
tunnel: 80a3ea78-9e68-4c40-af98-257d7c2b5255
credentials-file: /etc/cloudflared/80a3ea78-9e68-4c40-af98-257d7c2b5255.json
protocol: http2

ingress:
  - hostname: finance.rampung.space
    service: http://finance-bot:8000
  - service: http_status:404
```

---

## 4. Build & Push Image ARM64 di PC

### Login ke GitHub Container Registry
```bash
echo "YOUR_TOKEN" | docker login ghcr.io -u arcaz22 --password-stdin
```

> Token dibuat di: https://github.com/settings/tokens/new  
> Scope yang diperlukan: `write:packages`

### Build untuk ARM64 & Push
```bash
cd ~/project/portofolio/bot/fm

docker buildx build \
  --platform linux/arm64 \
  --tag ghcr.io/arcaz22/finance-bot:latest \
  --push .
```

> **Catatan:** Tag harus **lowercase** — `arcaz22` bukan `Arcaz22`

---

## 5. Transfer Config ke STB via Rsync

```bash
# Buat folder tujuan di STB
ssh root@192.168.101.15 "mkdir -p /opt/finance-bot/cloudflared"

# Rsync dari PC — hanya file config, bukan source code
rsync -avz --progress \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='*.py' \
  --exclude='*.toml' \
  --exclude='*.lock' \
  ~/project/portofolio/bot/fm/ \
  root@192.168.101.15:/opt/finance-bot/

# Set permission file sensitif
ssh root@192.168.101.15 "
  chmod 600 /opt/finance-bot/.env && \
  chmod 600 /opt/finance-bot/cloudflared/*.json
"
```

---

## 6. Menjalankan di STB

```bash
ssh root@192.168.101.15

cd /opt/finance-bot

# Login ghcr.io di STB (jika image private)
echo "YOUR_TOKEN" | docker login ghcr.io -u arcaz22 --password-stdin

# Pull image terbaru
docker compose pull

# Jalankan semua service
docker compose up -d

# Monitor logs
docker compose logs -f
```

---

## 7. Auto Restart Saat STB Reboot

`restart: unless-stopped` di docker-compose sudah menangani restart otomatis.  
Pastikan Docker daemon juga auto-start:

```bash
systemctl is-enabled docker
# Jika disabled:
systemctl enable docker
```

### Behaviour Restart

| Kondisi | Auto Restart? |
|---|---|
| STB reboot / mati-nyala | ✅ Ya |
| Container crash | ✅ Ya |
| Manual `docker compose down` | ❌ Tidak |

---

## 8. Workflow Update Selanjutnya

Setiap ada perubahan kode, cukup:

```bash
# Di PC — build & push image baru
docker buildx build \
  --platform linux/arm64 \
  --tag ghcr.io/arcaz22/finance-bot:latest \
  --push .

# Di STB — pull & restart
cd /opt/finance-bot
docker compose pull
docker compose up -d
```

> STB **tidak pernah build** — microSD tetap aman. ✅

---

## 9. Status Akhir

| Komponen | Status |
|---|---|
| Docker image ARM64 | ✅ Berhasil build & push |
| Cloudflared tunnel | ✅ Terkoneksi (sin14, cgk07) |
| Finance bot container | ⚠️ Perlu fix port (8080 → 8000) lalu build ulang |
| Config files di STB | ✅ Ada di `/opt/finance-bot/` |
| Auto restart | ✅ `restart: unless-stopped` aktif |

### Yang Masih Perlu Dilakukan
1. Fix Dockerfile — ganti port `8080` → `8000`
2. Build ulang image di PC
3. `docker compose pull && docker compose up -d` di STB
4. Verifikasi bot menerima webhook dari Telegram
