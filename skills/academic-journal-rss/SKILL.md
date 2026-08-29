---
name: academic-journal-rss
description: Build, enrich, and maintain automated RSS 2.0 feeds for academic journal Advance Articles, Accepted Manuscripts, and Online First papers with Zotero and RSS reader compatibility. Use when creating journal trackers, monitoring publication feeds, or extracting bibliographic metadata from Crossref, publisher APIs, and scrapers.
---

# Academic Journal RSS

A skill for creating and maintaining high-quality, automated RSS 2.0 feeds for academic journals. Focuses on capturing papers at their earliest public stage (Accepted Manuscript, Advance Article, Online First, Early View) with rich bibliographic metadata, Zotero compatibility, and automated GitHub Actions + GitHub Pages hosting.

## Summary

Standard academic journal feeds often suffer from delayed volume/issue release cycles, missing author lists, Cloudflare blocking, truncated feeds (only 10-20 items), or broken XML. This skill provides a proven, multi-source strategy (Crossref REST API + publisher RSS + fallback scrapers) to produce stable, daily-updating RSS feeds with at least 50 recent articles per journal.

## When to Use

- Tracking top academic journals at the earliest publication stage (Accepted Manuscript / Online First) before official volume and issue assignment.
- Generating Zotero-compatible and RSS-reader-compatible feeds with valid DOIs, author tags (`dc:creator`), and publication dates.
- Replacing unreliable or blocked publisher RSS feeds (e.g. Oxford Academic, Springer Nature, Wiley, Elsevier) with clean, automated feeds.
- Setting up scheduled GitHub Actions scrapers and GitHub Pages hosting for academic feeds.

## Core Workflow

### 1. Source Selection and Exploration
Identify the target journal print and electronic ISSNs. Evaluate available upstream endpoints in priority order:

1. **Official Crossref REST API**: Primary choice for unblocked bibliographic data, DOI registration, full author names, and JATS abstracts.
2. **Official Publisher RSS**: Check if available and verify item count, update frequency, and author metadata completeness.
3. **Publisher Web Scraper**: Fallback when official feeds are missing or incomplete, taking bot mitigation into account.

See [source-strategy.md](references/source-strategy.md) for publisher-specific evaluations (OUP, Springer, Wiley, Elsevier) and Cloudflare bypass strategies.

### 2. Multi-Source Merging and Deduplication
To guarantee at least 50 items and complete metadata:
- Fetch primary dataset from Crossref (`rows=60`, sorted by `published` or `deposited` descending).
- Fetch secondary dataset from publisher RSS or web scraper to catch zero-day announcements.
- Deduplicate items using normalized lowercase DOI (or canonical URL if DOI is missing).
- Merge attributes: keep the richest title, complete author list, full abstract, and earliest verified online publication date.
- Sort strictly from newest to oldest by UTC publication timestamp.

### 3. Non-Research Content Filtering
Filter or explicitly flag non-research entries:
- Exclude or tag title prefixes matching: `Correction to:`, `Erratum:`, `Retraction:`, `Expression of Concern:`, `Call for Papers:`.
- Ensure metadata field `type` matches `journal-article`.

### 4. Build Standards-Compliant RSS 2.0 XML
Generate XML conforming strictly to RSS 2.0 and Zotero feed ingestion requirements:
- Use namespaces: `xmlns:atom="http://www.w3.org/2005/Atom"` and `xmlns:dc="http://purl.org/dc/elements/1.1/"`.
- `<guid isPermaLink="false">`: Set to the raw DOI string (e.g. `10.1093/jcr/ucag029`).
- `<pubDate>`: Strict RFC 822 format (`%a, %d %b %Y %H:%M:%S +0000`).
- `<dc:creator>`: Comma-separated full author names for Zotero recognition.
- `<description>`: Formatted HTML with Authors, DOI link, Status, Publication Date, Clean Abstract, and Publisher Link.

See [feed-standard.md](references/feed-standard.md) for full XML templates, element requirements, and abstract cleaning rules.

### 5. Resilient Output and Fail-Safe Overwrite Protection
- Validate the generated XML using Python `xml.etree.ElementTree`.
- **Fail-Safe Gate**: Never overwrite an existing valid feed if the scraper returns 0 items or throws a network error. Require `len(articles) >= MIN_ARTICLES_THRESHOLD` (e.g. 10) before writing to disk.
- Write output XML to `docs/<journal_slug>.xml` and update `docs/index.html`.

### 6. Deployment and Automation
- Store feeds in `docs/` for GitHub Pages hosting (`main` branch, `/docs` folder).
- Configure GitHub Actions workflow (`.github/workflows/update-rss.yml`) to run on schedule (e.g. `0 */6 * * *`) and `workflow_dispatch`.
- Use `git diff --staged --quiet` to only commit and push when feed content actually changes.

## Gotchas

- **OUP Cloudflare Blocking**: Oxford Academic endpoints return HTTP 403 when requested by automated scripts. Never rely on scraping `academic.oup.com` directly; use Crossref with journal ISSN (`0093-5301`) which reflects OUP deposits instantly.
- **Springer RSS Limitations**: Springer search RSS (`search.rss?facet-journal-id=...`) provides only 20 items and lacks author tags in XML. Always merge with Crossref (ISSN `0092-0703`) to reach 50+ articles with full author details.
- **XML Namespace Duplication**: When using Python `xml.etree.ElementTree` with `minidom`, register namespaces via `ET.register_namespace()` before constructing elements. Do not manually inject `xmlns` attributes into root tags to avoid XML duplicate attribute parse errors.
- **JATS Tag Artifacts**: Crossref abstracts contain JATS XML tags like `<jats:p>`, `<jats:sec>`, `<jats:title>Abstract</jats:title>`. Always parse with BeautifulSoup, strip "Abstract" headings, and clean extra whitespace.
- **Timezone Normalization**: Crossref `date-parts` provide `[YYYY, MM, DD]`. Convert to timezone-aware UTC datetime before formatting to RFC 822 to avoid date drift in RSS readers.
