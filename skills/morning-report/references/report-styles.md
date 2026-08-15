# Report Styles

Use the configured report language from config. All headings, content, and date format must be in that language.

Use exactly one canonical style: `concise`, `deep_analysis`, or `opportunities_risks`.

## concise

Scan-friendly. 400-600 words.

```md
# Morning Brief — <date in report language>

## <section heading in report language>
- One most important update.

## <section heading in report language>
- 3-5 bullets: what changed + why it matters.

## <section heading in report language>
- 1-3 signals.
```

Heading translations vary by language — use the configured `report_language`.

## deep_analysis

900-1200 words. Needs ### subsections.

```md
# Morning Analysis — <date in report language>

## <section heading in report language>
- 2-4 judgments.

## <section heading in report language>
### Theme
- What happened. Evidence. Why it matters.

## <section heading in report language>
- Short-term / Medium-term.

## <section heading in report language>
```

Heading translations vary by language — use the configured `report_language`.

## opportunities_risks

900-1200 words. Needs ### subsections.

```md
# Opportunities & Risks — <date in report language>

## <section heading in report language>
- 2-3 important changes.

## <section heading in report language>
### Opportunityhết

## <section heading in report language>
- Indicators.

## <section heading in report language>
- Actions.
```

Heading translations vary by language — use the configured `report_language`.

## Rules

- All section headings must be in the configured report language — never in English unless config says English.
- Start directly with the title.
- No progress logs, debug notes, or second recap.
- Include 3-5 Markdown evidence links using `SOURCE_URL` values from source files.
- Put evidence links in a footer section.
- Keep tone calm. Avoid hype.
