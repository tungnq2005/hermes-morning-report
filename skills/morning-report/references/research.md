# Research

Use configured topics only.

## Search

- Use the source collection helper when available.
- Search 10 URLs per call.
- Dedupe URLs before fetch.
- Fetch only URLs with search publish time inside the last 24 hours.
- Stop after 5 readable fetched web sources or after 5 search calls.
- Facebook/TikTok: use only as site-search social signals. Do not claim direct crawling.

## Sources

- Use `fetched_sources` from the helper.
- Read every `text_file` before writing the report.
- If fewer than 5 sources were fetched, do not write the report.

## Claims

- Main claims need fetched source evidence.
- Do not invent dates, numbers, URLs, or source details.
- Do not include technical fetch failures in the customer-facing report.
