# ADR-0019: Web pages are a knowledge source

- Status: Accepted
- Date: 2026-10-05
- Deciders: Fares

## Context

The first PRD draft took knowledge only from uploaded files (PDF with selectable text, DOCX, Markdown, plain text) and listed website crawling and URL import as non-goals. In grilling round 7 the vendor added web pages.

## Decision

Besides the four file formats, an install's knowledge base can take content from web pages. The business's Owner adds them, and the AI uses them as soon as they are processed, like uploaded files.

## Consequences

- The PRD non-goal "no website crawling or URL import" no longer holds.
- Pages change after import, so imported content can go stale.

## Open

- How pages come in: single URLs, a crawl from a start URL, or a sitemap.
- How imported pages are kept current.

## Update, 2026-10-05 (grilling round 7)

Imported pages are refreshed manually: the Owner clicks refresh. There is no scheduled re-sync. How pages come in is still open; a proposal follows the vendor's answer.

## Update, 2026-10-06 (grilling round 7)

How pages come in, approved as proposed and copied from Intercom and similar tools:

- The Owner enters a start URL. The install crawls that site's public pages, as static HTML, up to a page limit, and lists them. The Owner picks which to import.
- The Owner can also paste individual URLs or a sitemap.
- Pages that need JavaScript to show their text come back empty and are reported as such. Pages behind a login cannot be imported.
