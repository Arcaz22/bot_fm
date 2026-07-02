# Setup dan testing Ollama

Konfigurasi ini memakai model yang berbeda untuk setiap pekerjaan:

- NLP teks transaksi: `llama3.1:8b`
- Vision/scan nota: `llava:13b`
- Test tanpa NLP: `MockLLM` dan aturan regex lokal

## Setup

Install dan jalankan Ollama, lalu unduh kedua model:

```bash
ollama serve
ollama pull llama3.1:8b
ollama pull llava:13b
```

Salin `.env.example` ke `.env`, pertahankan konfigurasi aplikasi yang sudah ada,
kemudian isi:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TEXT_MODEL=llama3.1:8b
OLLAMA_VISION_MODEL=llava:13b
OLLAMA_TIMEOUT_SECONDS=120
```

Jika aplikasi berjalan di container sementara Ollama berjalan di host, gunakan
`OLLAMA_BASE_URL=http://host.docker.internal:11434`.

Untuk test yang sepenuhnya deterministik dan tidak menjalankan AI:

```env
LLM_PROVIDER=mock
```

## Menjalankan test

Semua unit test (tanpa memanggil Ollama):

```bash
uv run python -m unittest discover -s tests -v
```

Test integrasi NLP nyata dengan `llama3.1:8b`:

```bash
RUN_OLLAMA_TESTS=1 uv run python -m unittest \
  tests.test_llm_modes.OllamaIntegrationTest.test_real_nlp -v
```

Test scan nota nyata dengan `llava:13b`:

```bash
RUN_OLLAMA_TESTS=1 \
OLLAMA_RECEIPT_TEST_IMAGE=tests/nota.jpg \
uv run python -m unittest discover -s tests -v
```

```
uv run python -m unittest discover -s tests -v
```

Test tanpa NLP berada di `NoNLPTest`. Test ini menggunakan `MockLLM` atau regex
domain sehingga cepat, konsisten, dan cocok dijalankan pada setiap commit.

# semua test
uv run pytest tests/ -v

# dengan ollama
RUN_OLLAMA_TESTS=1 uv run pytest tests/ -v

# dengan nota
RUN_OLLAMA_TESTS=1 \
OLLAMA_RECEIPT_TEST_IMAGE=tests/nota.jpg \
uv run pytest tests/ -v
