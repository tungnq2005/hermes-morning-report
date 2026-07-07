# Model Fallback

Use this reference only for internal Morning Report runtime fallback setup or troubleshooting.

Do not mention model/provider fallback details to the customer unless the operator explicitly asks.

## Purpose

Morning Report should keep its normal primary model and use fallback models only when the primary model fails with a failover-worthy runtime error.

Do not use fallback setup to change report content, topics, style, language, delivery time, or Telegram delivery.

## Inspect First

Before changing fallback configuration, inspect the current state:

```bash
openclaw models fallbacks list
openclaw models status
openclaw cron show <job-id>
```

If a command returns `GatewaySecretRefUnavailableError`, do not conclude that fallback or cron is missing. Use a gateway-resolved command path, pass a supported token outside workspace files, or ask the operator/OpenClaw runtime to verify.

## Global Default Fallback

Use global default fallback when the Morning Report cron job has no job-level model override and no job-level fallback override.

Command shape:

```bash
openclaw models fallbacks add <provider/model>
```

Expected default model shape after setup:

```json
{
  "primary": "<primary-provider/model>",
  "fallbacks": ["<fallback-provider/model>"]
}
```

Use only fallback models/providers that are actually available in the current runtime.

Do not hard-code a fallback provider/model in reusable prompts. The operator may choose a different fallback per customer/runtime.

## Cron Job Interaction

For Morning Report cron jobs:

- `payload.model` or `cron edit --model` is a job primary model override.
- `payload.fallbacks` is a job-level fallback override when the runtime supports setting it.
- `payload.fallbacks: []` means strict/no fallback.
- If the job has no `payload.model` and no `payload.fallbacks`, it can inherit `agents.defaults.model.fallbacks`.

Do not run this to configure fallback:

```bash
openclaw cron edit <job-id> --model <fallback-provider/model>
```

That changes the cron job primary model. It does not configure a fallback from the existing primary model.

If the installed OpenClaw version supports a documented cron fallback flag, inspect `openclaw cron add --help` and `openclaw cron edit --help` first. Use job-level fallback only when it is supported by the current runtime and the operator explicitly wants fallback scoped to that job.

## Verification

After changing fallback configuration, verify:

```bash
openclaw models fallbacks list
openclaw models status
openclaw cron show <job-id>
```

Treat fallback as verified only when reliable runtime output or inspected config shows:

- the primary model remains the intended primary model
- the fallback list contains the intended fallback model
- the Morning Report cron job does not accidentally override the primary model
- the job does not contain `payload.fallbacks: []`

If CLI verification is blocked by gateway secret resolution, say fallback was written to config but runtime verification is pending.

## Cost And Reliability

Fallback models may be more expensive than the primary model. Use them as backup, not as the default primary, unless the operator explicitly asks.

A fallback within the same provider may not protect against provider-wide outages. It can still help when the primary model is busy, degraded, unavailable, or rate-limited differently.
