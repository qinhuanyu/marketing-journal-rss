# Academic Journal Source Selection & Scraping Strategy

This reference captures the operational lessons, publisher evaluations, failed approaches, and proven fallback strategies for building reliable academic journal feeds.

---

## 1. Earliest Publication Stage Taxonomy

Academic journals publish research in multiple phases before final volume and issue assignment:

| Term | Typical Publishers | Description | Target Priority |
| :--- | :--- | :--- | :--- |
| **Accepted Manuscript (AM)** | Oxford University Press, Wiley | Peer-reviewed and accepted text, unformatted by publisher. Earliest public metadata. | **Highest** |
| **Advance Article / Online First** | OUP, Springer Nature, SAGE | Final formatted article published online prior to issue assignment. | **Highest** |
| **Early View** | Wiley-Blackwell | Fully peer-reviewed, formatted version of record published before volume release. | **Highest** |
| **Article in Press (AiP)** | Elsevier (ScienceDirect) | Accepted manuscript or corrected proof before inclusion in a volume. | **Highest** |
| **Current Issue / Final Issue** | All publishers | Formal volume/issue publication (can be delayed by 3–18 months). | **Avoid for real-time tracking** |

---

## 2. Publisher-Specific Case Studies & Lessons Learned

### A. Oxford University Press (OUP) — e.g. Journal of Consumer Research (JCR)

- **Attempt 1: Direct Web Scraping (`https://academic.oup.com/jcr/advance-articles`)**
  - *Result*: **Failed with HTTP 403 Forbidden**.
  - *Root Cause*: OUP employs Cloudflare Bot Management (`cf-mitigated: challenge`), actively rejecting automated curl/requests calls.
- **Attempt 2: Direct Publisher RSS (`https://academic.oup.com/rss/site_.../advanceArticles.xml`)**
  - *Result*: **Failed with HTTP 404 Not Found**.
  - *Root Cause*: OUP deprecated public unauthenticated Advance Article RSS feeds.
- **Attempt 3 (Winning Strategy): Crossref REST API via Journal ISSN**
  - *Query*: `https://api.crossref.org/journals/0093-5301/works?sort=published&order=desc&rows=60`
  - *Result*: **100% Success**. OUP immediately deposits metadata with `content-version: am` and DOI upon acceptance.
  - *Data Available*: Clean article titles, complete author lists, JATS abstracts, DOI permalinks, and exact online publication dates without Cloudflare interference.

### B. Springer Nature — e.g. Journal of the Academy of Marketing Science (JAMS)

- **Attempt 1: Springer Official Search RSS (`https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=11747`)**
  - *Result*: **Partial Success**. HTTP 200 OK with valid RSS 2.0 XML.
  - *Limitations*: Capped at 20 items; lacks `<dc:creator>` tags; descriptions contain truncated snippets without full author names.
- **Attempt 2: Springer Online First Web Scraper (`https://link.springer.com/journal/11747/online-first`)**
  - *Result*: **Successful**. Parses ~47 article cards, but requires continuous maintenance against HTML structure changes.
- **Attempt 3 (Winning Strategy): Multi-Source Enrichment & Merge**
  - *Approach*: Combine Crossref API (ISSN `0092-0703`, 60 items) + Springer official RSS + Springer Web Scraper.
  - *Result*: Produces 60 fully populated articles with real-time freshness, complete author metadata, and rich abstracts.

---

## 3. Crossref API Best Practices for Journal Feeds

Crossref is the official DOI registration agency for scholarly publishers (OUP, Springer, Wiley, Elsevier, SAGE, Taylor & Francis, IEEE). It provides the most resilient foundation for academic feeds.

### Request Headers (The Polite Pool)
Always include a contact email in the `User-Agent` to use the Crossref Polite Pool for higher rate limits and guaranteed SLA:

```python
HEADERS = {
    "User-Agent": "AcademicJournalRSS/1.0 (https://github.com/<owner>/<repo>; mailto:<your-email>@example.com)",
    "Accept": "application/json"
}
```

### Date Extraction Hierarchy
Crossref records multiple timestamps depending on publisher deposit workflow. Extract dates using this priority:

1. `published-online` (Preferred: Represents the date the paper went live online)
2. `published` (General publication date)
3. `created` (Date Crossref record was minted)
4. `deposited` (Date metadata was pushed by the publisher)

```python
def extract_online_date(item: dict) -> datetime:
    for key in ["published-online", "published", "created", "deposited"]:
        parts = item.get(key, {}).get("date-parts", [[]])
        if parts and parts[0]:
            year = parts[0][0] if len(parts[0]) > 0 else 2026
            month = parts[0][1] if len(parts[0]) > 1 else 1
            day = parts[0][2] if len(parts[0]) > 2 else 1
            return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
```

---

## 4. Multi-Source Merging & Deduplication Pattern

When combining multiple data streams (Crossref + Official RSS + Web Scraper), merge them by normalized DOI:

```python
def merge_and_deduplicate(primary_list: list, secondary_list: list, max_count: int = 60) -> list:
    """
    Merge articles by DOI/URL, keeping the richest metadata for each paper.
    """
    merged = {}
    
    # Process secondary first, then primary overwrites/enriches
    for item in secondary_list + primary_list:
        key = (item.get("doi") or item.get("link") or "").lower().strip()
        if not key:
            continue
            
        if key not in merged:
            merged[key] = item
        else:
            existing = merged[key]
            # Retain non-empty, longer fields (e.g. full author strings or full abstracts)
            for field in ["authors", "abstract", "doi", "status", "title", "link"]:
                if item.get(field) and len(str(item.get(field))) > len(str(existing.get(field, ""))):
                    existing[field] = item[field]
            # Keep newest verified date
            if item.get("date") and item["date"] > existing.get("date", datetime.min.replace(tzinfo=timezone.utc)):
                existing["date"] = item["date"]
                
    results = list(merged.values())
    results.sort(key=lambda x: x.get("date", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return results[:max_count]
```

---

## 5. Automated Hosting Architecture

```
                               ┌─────────────────────────────┐
                               │  Crossref REST API          │
                               │  (OUP, Springer, Wiley...)  │
                               └──────────────┬──────────────┘
                                              │
┌────────────────────────────┐                │
│ Springer / Publisher RSS   ├────────────────┼─────────────┐
└────────────────────────────┘                │             │
                                              ▼             ▼
┌────────────────────────────┐     ┌─────────────────────────────┐
│ GitHub Actions Workflow    │────▶│    src/generate_feeds.py    │
│ (Cron: Every 6 Hours)      │     └──────────────┬──────────────┘
└────────────────────────────┘                    │
                                                  ▼
                                   ┌─────────────────────────────┐
                                   │  docs/jcr.xml & docs/jams.xml│
                                   └──────────────┬──────────────┘
                                                  │
                                                  ▼
                                   ┌─────────────────────────────┐
                                   │ GitHub Pages (Free Hosting) │
                                   │  https://<user>.github.io/  │
                                   └──────────────┬──────────────┘
                                                  │
                      ┌───────────────────────────┴───────────────────────────┐
                      ▼                                                       ▼
        ┌───────────────────────────┐                           ┌───────────────────────────┐
        │  RSS Readers (Feedly,     │                           │   Zotero Feed Library     │
        │  Inoreader, NetNewsWire)  │                           │   (Auto Research Import)  │
        └───────────────────────────┘                           └───────────────────────────┘
```
