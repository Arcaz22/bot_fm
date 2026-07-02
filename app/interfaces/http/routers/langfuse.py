import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse

from app.core.di import get_llm_client
from app.core.settings import settings
from app.domain.llm.ports import LLMPort
from app.presentation.schemas.langfuse import ExtractionTestResponse, TokenUsage, TransactionTestRequest


router = APIRouter(prefix="/internal/langfuse-test", tags=["internal"])

def _ensure_interface_enabled() -> None:
    if not settings.LANGFUSE_TEST_INTERFACE_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _verify_test_token(provided_token: str | None) -> None:
    configured_token = settings.LANGFUSE_TEST_INTERFACE_TOKEN
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LANGFUSE_TEST_INTERFACE_TOKEN belum dikonfigurasi",
        )
    if not provided_token or not secrets.compare_digest(provided_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interface tidak valid",
        )


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def langfuse_test_page() -> HTMLResponse:
    _ensure_interface_enabled()
    headers = {
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
    }
    return HTMLResponse(content=PAGE_HTML, headers=headers)


@router.post("/transaction", response_model=ExtractionTestResponse)
async def test_transaction(
    payload: TransactionTestRequest,
    x_langfuse_test_token: str | None = Header(default=None),
    llm: LLMPort = Depends(get_llm_client),
) -> ExtractionTestResponse:
    _ensure_interface_enabled()
    _verify_test_token(x_langfuse_test_token)

    result = await llm.parse_transaction(
        text=payload.prompt,
        include_usage=True,
    )
    return ExtractionTestResponse(
        data=result["data"],
        model=result["model"],
        usage=TokenUsage(**result["usage"]),
    )


@router.post("/receipt", response_model=ExtractionTestResponse)
async def test_receipt(
    file: UploadFile = File(...),
    context: str | None = Form(default=None, max_length=1000),
    x_langfuse_test_token: str | None = Header(default=None),
    llm: LLMPort = Depends(get_llm_client),
) -> ExtractionTestResponse:
    _ensure_interface_enabled()
    _verify_test_token(x_langfuse_test_token)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="File gambar kosong")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ukuran gambar maksimal 10 MB")

    result = await llm.parse_receipt_image(
        image_bytes=image_bytes,
        context=context,
        include_usage=True,
    )
    return ExtractionTestResponse(
        data=result["data"],
        model=result["model"],
        usage=TokenUsage(**result["usage"]),
    )


PAGE_HTML = """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Langfuse Token Test</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #0b1020; color: #e8ecf4; }
    main { width: min(820px, calc(100% - 32px)); margin: 48px auto; }
    .panel { background: #141b2d; border: 1px solid #29324a; border-radius: 14px; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    p { color: #aeb8cd; margin: 0 0 24px; }
    label { display: block; margin: 16px 0 8px; font-weight: 600; }
    input, select, textarea, button { box-sizing: border-box; width: 100%; font: inherit; }
    input, select, textarea { background: #0d1425; color: #f5f7fb; border: 1px solid #34405d; border-radius: 9px; padding: 11px 12px; }
    textarea { min-height: 120px; resize: vertical; }
    button { margin-top: 18px; border: 0; border-radius: 9px; padding: 12px; background: #5b7cfa; color: white; font-weight: 700; cursor: pointer; }
    button:disabled { cursor: wait; opacity: .65; }
    .result { display: none; margin-top: 20px; }
    .hidden { display: none; }
    .hint { margin: 7px 0 0; font-size: 13px; }
    .usage { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0; }
    .metric { background: #0d1425; border-radius: 9px; padding: 12px; }
    .metric span { display: block; color: #94a0b8; font-size: 12px; }
    .metric strong { display: block; margin-top: 4px; font-size: 20px; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0d1425; border-radius: 9px; padding: 14px; }
    .error { color: #ff9d9d; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Langfuse Token Test</h1>
      <p>Uji parsing transaksi atau scan nota langsung ke provider LLM tanpa menyimpan ke database aplikasi.</p>
      <form id="test-form">
        <label for="token">Access token</label>
        <input id="token" type="password" autocomplete="off" required>
        <label for="mode">Jenis pengujian</label>
        <select id="mode">
          <option value="transaction">Teks transaksi</option>
          <option value="receipt">Scan nota</option>
        </select>
        <section id="transaction-fields">
          <label for="prompt">Teks transaksi</label>
          <textarea id="prompt" placeholder="Contoh: makan 20k"></textarea>
          <p class="hint">System instruction transaksi dari aplikasi digunakan otomatis.</p>
        </section>
        <section id="receipt-fields" class="hidden">
          <label for="receipt">Foto nota</label>
          <input id="receipt" type="file" accept="image/*">
          <label for="context">Konteks tambahan (opsional)</label>
          <textarea id="context" placeholder="Contoh: belanja bulanan"></textarea>
          <p class="hint">System instruction scan nota dari aplikasi digunakan otomatis.</p>
        </section>
        <button id="submit" type="submit">Kirim ke LLM</button>
      </form>
      <section id="result" class="result">
        <div id="usage" class="usage"></div>
        <pre id="output"></pre>
      </section>
    </section>
  </main>
  <script>
    const form = document.getElementById('test-form');
    const button = document.getElementById('submit');
    const result = document.getElementById('result');
    const output = document.getElementById('output');
    const usage = document.getElementById('usage');
    const mode = document.getElementById('mode');
    const transactionFields = document.getElementById('transaction-fields');
    const receiptFields = document.getElementById('receipt-fields');

    mode.addEventListener('change', () => {
      const isReceipt = mode.value === 'receipt';
      transactionFields.classList.toggle('hidden', isReceipt);
      receiptFields.classList.toggle('hidden', !isReceipt);
    });

    function metric(label, value) {
      const node = document.createElement('div');
      node.className = 'metric';
      const caption = document.createElement('span');
      caption.textContent = label;
      const number = document.createElement('strong');
      number.textContent = value ?? '-';
      node.append(caption, number);
      return node;
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = 'Memproses...';
      result.style.display = 'block';
      output.className = '';
      output.textContent = 'Menunggu respons...';
      usage.replaceChildren();

      try {
        const token = document.getElementById('token').value;
        let url;
        let options;

        if (mode.value === 'transaction') {
          const prompt = document.getElementById('prompt').value.trim();
          if (!prompt) throw new Error('Teks transaksi wajib diisi');
          url = '/internal/langfuse-test/transaction';
          options = {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Langfuse-Test-Token': token,
            },
            body: JSON.stringify({ prompt }),
          };
        } else {
          const file = document.getElementById('receipt').files[0];
          if (!file) throw new Error('Foto nota wajib dipilih');
          const body = new FormData();
          body.append('file', file);
          const context = document.getElementById('context').value.trim();
          if (context) body.append('context', context);
          url = '/internal/langfuse-test/receipt';
          options = {
            method: 'POST',
            headers: { 'X-Langfuse-Test-Token': token },
            body,
          };
        }

        const response = await fetch(url, options);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Request gagal');

        usage.append(
          metric('Input tokens', data.usage.input),
          metric('Output tokens', data.usage.output),
          metric('Total tokens', data.usage.total),
        );
        output.textContent = `${data.model}\n\n${JSON.stringify(data.data, null, 2)}`;
      } catch (error) {
        output.className = 'error';
        output.textContent = error.message;
      } finally {
        button.disabled = false;
        button.textContent = 'Kirim ke LLM';
      }
    });
  </script>
</body>
</html>
"""
