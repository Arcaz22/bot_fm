# Financial Management API

## Documentation

- [Telegram Redis Queue Flow](docs/telegram-redis-queue.md)

## Langfuse token test interface

The internal test page calls Gemini directly without writing to the application
database. Enable and protect it using server environment variables:

```env
LANGFUSE_TEST_INTERFACE_ENABLED=true
LANGFUSE_TEST_INTERFACE_TOKEN=replace-with-a-long-random-token
```

After deployment, open `/internal/langfuse-test`. The page supports the actual
transaction parser and receipt-image parser, including Gemini input, output,
and total token usage. Use the configured token in the page. Disable the
interface again after testing by setting
`LANGFUSE_TEST_INTERFACE_ENABLED=false`.
