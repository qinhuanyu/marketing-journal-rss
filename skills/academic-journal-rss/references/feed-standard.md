# RSS 2.0 Feed Standard & Zotero Compatibility Guide

This reference document details the technical specification, XML schema, metadata sanitization, and compatibility rules required to produce robust academic journal feeds.

---

## 1. Complete RSS 2.0 XML Schema & Template

Feeds must use standard RSS 2.0 with Dublin Core (`xmlns:dc`) and Atom (`xmlns:atom`) namespace extensions.

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>Journal of Consumer Research - Advance Articles</title>
    <link>https://academic.oup.com/jcr/advance-articles</link>
    <description>Latest Advance Articles and Accepted Manuscripts from Journal of Consumer Research (JCR)</description>
    <language>en</language>
    <lastBuildDate>Sat, 29 Aug 2026 04:30:35 +0000</lastBuildDate>
    <generator>MarketingJournalRSS Bot (https://github.com/qinhuanyu/marketing-journal-rss)</generator>
    <atom:link href="https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml" rel="self" type="application/rss+xml"/>
    
    <item>
      <title>The Benefits of Bundling Material Goods with Moderate Usage Complementarity</title>
      <link>https://doi.org/10.1093/jcr/ucag029</link>
      <guid isPermaLink="false">10.1093/jcr/ucag029</guid>
      <pubDate>Mon, 24 Aug 2026 00:00:00 +0000</pubDate>
      <dc:creator>Eugenia C Wu, Sarah G Moore, Peggy J Liu, Daniella Kupor</dc:creator>
      <description>&lt;p&gt;&lt;strong&gt;Authors:&lt;/strong&gt; Eugenia C Wu, Sarah G Moore, Peggy J Liu, Daniella Kupor&lt;/p&gt;&lt;p&gt;&lt;strong&gt;DOI:&lt;/strong&gt; &lt;a href="https://doi.org/10.1093/jcr/ucag029" target="_blank"&gt;10.1093/jcr/ucag029&lt;/a&gt;&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Status:&lt;/strong&gt; Advance Article / Online First (Accepted Manuscript)&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Online Publication Date:&lt;/strong&gt; 2026-08-24&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Abstract:&lt;/strong&gt;&lt;br/&gt;Firms can bundle material goods together in various ways...&lt;/p&gt;&lt;p&gt;&lt;a href="https://doi.org/10.1093/jcr/ucag029" target="_blank"&gt;Read Full Article at Publisher &amp;rarr;&lt;/a&gt;&lt;/p&gt;</description>
    </item>
  </channel>
</rss>
```

---

## 2. Element-by-Element Specification

### Channel Elements
- **`title`**: Full journal name followed by the publication stage (e.g. `Journal of the Academy of Marketing Science - Online First`).
- **`link`**: Canonical publisher landing page for early articles (e.g. `https://link.springer.com/journal/11747/online-first`).
- **`description`**: Clear summary of what the feed tracks.
- **`language`**: Primary language code (`en`).
- **`lastBuildDate`**: Time the feed was generated in RFC 822 format.
- **`atom:link`**: Self-referencing link with `rel="self"` and `type="application/rss+xml"`. Ensures feed validators and readers discover canonical feed updates.

### Item Elements
- **`title`**: Clean article title. HTML tags (such as `<i>`, `<b>`, `<sup>`) must be stripped or converted to plain text. XML special characters (`&`, `<`, `>`, `"`) must be escaped properly.
- **`link`**: Permanent DOI resolution URL (e.g. `https://doi.org/10.1093/jcr/ucag029`).
- **`guid`**: Set `isPermaLink="false"` and use the raw DOI identifier (e.g. `10.1093/jcr/ucag029`). If no DOI exists, use the permanent article URL with `isPermaLink="true"`.
- **`pubDate`**: Exact online publication date formatted per RFC 822 (`%a, %d %b %Y %H:%M:%S +0000`).
- **`dc:creator`**: Dublin Core author element. Comma-separated full names (e.g. `Firstname Lastname, Firstname Lastname`). This is the primary field Zotero and RSS aggregators read for author metadata.
- **`description`**: Formatted HTML containing:
  1. `<strong>Authors:</strong>` Full author list.
  2. `<strong>DOI:</strong>` Clickable link to the DOI resolver.
  3. `<strong>Status:</strong>` Stage indicator (e.g. `Advance Article / Accepted Manuscript` or `Online First`).
  4. `<strong>Online Publication Date:</strong>` `YYYY-MM-DD` string.
  5. `<strong>Abstract:</strong>` Cleaned abstract paragraph.
  6. Publisher link anchor for direct access.

---

## 3. Zotero Compatibility Conventions

Zotero parses RSS feeds to automatically create library items. Follow these rules for flawless Zotero ingestion:

1. **DOI in GUID**: Zotero uses the GUID or link to query Crossref/DOI resolvers for full citation metadata. Providing a clean DOI in `<guid>` allows Zotero to fetch complete bibliographic records in one click.
2. **`dc:creator` Format**: Put authors in `dc:creator`. Avoid formatting like "By John Doe" or "Author: John Doe"; provide plain names `John Doe, Jane Smith`.
3. **Date Resolution**: Zotero requires a valid RFC 822 date in `<pubDate>`. Unformatted date strings (e.g. `2026-08-24`) cause Zotero to fall back to the ingestion timestamp.

---

## 4. JATS Abstract Cleaning Algorithm

Abstracts retrieved from Crossref or publisher APIs frequently contain JATS (Journal Article Tag Suite) XML markup. Use this Python snippet to sanitize them:

```python
import re
import html
from bs4 import BeautifulSoup

def clean_jats_abstract(raw_text: str) -> str:
    """Clean JATS XML tags while preserving readable text."""
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    
    # Decompose title tags like <jats:title>Abstract</jats:title>
    for tag in soup.find_all(re.compile(r".*title.*")):
        if "abstract" in tag.get_text().lower():
            tag.decompose()
            
    # Extract text with single spaces
    text = soup.get_text(separator=" ", strip=True)
    # Collapse multiple consecutive whitespace/newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

---

## 5. Non-Research Content Filtering

Many journal advance feeds interleave administrative, errata, and non-research items. Apply strict regex filters:

```python
NON_RESEARCH_PATTERNS = [
    r"^Correction to:",
    r"^Erratum:",
    r"^Retraction:",
    r"^Expression of Concern:",
    r"^Editorial Expression of Concern:",
    r"^Call for Papers",
    r"^Editorial Board",
    r"^Publisher'?s Note",
    r"^Author Correction:"
]

def is_research_article(title: str, item_type: str = "journal-article") -> bool:
    """Verify if an entry represents an original research article."""
    if item_type and item_type != "journal-article":
        return False
    for pattern in NON_RESEARCH_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return False
    return True
```

---

## 6. Fail-Safe Overwrite Protection

Network failures or temporary upstream rate-limits must never wipe out an existing valid feed.

```python
import os
import logging

MIN_FEED_ARTICLES = 10

def safe_write_feed(file_path: str, new_xml_content: str, article_count: int):
    """Ensure a valid feed is never replaced with empty or corrupted content."""
    if article_count < MIN_FEED_ARTICLES:
        logging.error(
            f"Fetched only {article_count} articles for {file_path}. "
            f"Aborting write to preserve existing feed."
        )
        return False
    
    # Write atomically via temp file
    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(new_xml_content)
    os.replace(temp_path, file_path)
    logging.info(f"Successfully updated {file_path} with {article_count} articles.")
    return True
```
