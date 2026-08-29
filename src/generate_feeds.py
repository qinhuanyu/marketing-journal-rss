#!/usr/bin/env python3
"""
Marketing Journal RSS Generator
Fetches latest Advance Articles / Online First articles for:
- Journal of Consumer Research (JCR)
- Journal of the Academy of Marketing Science (JAMS)
Generates valid RSS 2.0 feeds and updates docs/ index.
"""

import sys
import os
import re
import html
import time
import json
import logging
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("FeedGenerator")

# Register XML namespaces globally
ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")

# Base configuration
BASE_GITHUB_IO_URL = "https://qinhuanyu.github.io/marketing-journal-rss"
USER_AGENT = "MarketingJournalRSS/1.0 (https://github.com/qinhuanyu/marketing-journal-rss; mailto:qinhuanyu.academic@gmail.com)"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7"
}


def get_requests_session() -> requests.Session:
    """Create a resilient requests session with automatic retries."""
    session = requests.Session()
    retries = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def clean_jats_abstract(raw_text: str) -> str:
    """Clean JATS XML tags from abstracts while preserving readability."""
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    
    # Remove headings like 'Abstract' or 'jats:title'
    for tag in soup.find_all(re.compile(r".*title.*")):
        if "abstract" in tag.get_text().lower():
            tag.decompose()
            
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_rfc822_date(dt: datetime) -> str:
    """Format datetime object into RFC 822 format required by RSS 2.0."""
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def parse_date_parts_to_datetime(date_parts: list) -> datetime:
    """Convert Crossref date-parts list [YYYY, MM, DD] to timezone-aware datetime."""
    try:
        year = date_parts[0] if len(date_parts) > 0 else 2026
        month = date_parts[1] if len(date_parts) > 1 else 1
        day = date_parts[2] if len(date_parts) > 2 else 1
        return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    except Exception as e:
        logger.warning(f"Error parsing date parts {date_parts}: {e}")
        return datetime.now(timezone.utc)


def fetch_crossref_articles(issn: str, journal_name: str, max_rows: int = 60) -> list:
    """
    Fetch articles directly from official Crossref REST API using journal ISSN.
    Returns list of standardized article dicts.
    """
    session = get_requests_session()
    url = f"https://api.crossref.org/journals/{issn}/works?sort=published&order=desc&rows={max_rows}"
    logger.info(f"Fetching Crossref metadata for {journal_name} (ISSN: {issn})...")
    
    try:
        resp = session.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        logger.info(f"Retrieved {len(items)} works for {journal_name} from Crossref.")
        
        articles = []
        for it in items:
            title_list = it.get("title", [])
            title = title_list[0] if title_list else "Untitled"
            title = BeautifulSoup(title, "html.parser").get_text(strip=True)
            
            doi = it.get("DOI", "").strip()
            article_url = f"https://doi.org/{doi}" if doi else it.get("URL", "")
            
            # Authors list
            authors = []
            for a in it.get("author", []):
                given = a.get("given", "").strip()
                family = a.get("family", "").strip()
                if family or given:
                    authors.append(f"{given} {family}".strip())
            author_str = ", ".join(authors) if authors else "Authors Not Listed"
            
            # Publication / Online date
            dt = None
            date_keys = ["published-online", "published", "created", "deposited"]
            for dk in date_keys:
                dp = it.get(dk, {}).get("date-parts", [[]])
                if dp and dp[0]:
                    dt = parse_date_parts_to_datetime(dp[0])
                    break
            if not dt:
                dt = datetime.now(timezone.utc)
                
            # Abstract
            raw_abstract = it.get("abstract", "")
            clean_abstract = clean_jats_abstract(raw_abstract)
            
            # Status check
            volume = it.get("volume")
            issue = it.get("issue")
            if not volume or not issue:
                status = "Advance Article / Online First (Accepted Manuscript)"
            else:
                status = f"Volume {volume}, Issue {issue}"
                
            articles.append({
                "title": title,
                "link": article_url,
                "doi": doi,
                "guid": doi if doi else article_url,
                "authors": author_str,
                "date": dt,
                "status": status,
                "abstract": clean_abstract,
                "source": "Crossref / Publisher Deposit"
            })
            
        return articles
    except Exception as e:
        logger.error(f"Failed to fetch Crossref data for {journal_name}: {e}")
        return []


def fetch_springer_rss(journal_id: str = "11747") -> list:
    """
    Fetch and parse Springer's official search RSS feed for a journal ID.
    Returns list of article dicts.
    """
    session = get_requests_session()
    url = f"https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id={journal_id}"
    logger.info(f"Fetching Springer official RSS for journal ID {journal_id}...")
    
    articles = []
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall("./channel/item")
        logger.info(f"Parsed {len(items)} items from Springer RSS.")
        
        for it in items:
            title_elem = it.find("title")
            link_elem = it.find("link")
            pub_elem = it.find("pubDate")
            desc_elem = it.find("description")
            
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Untitled"
            title = BeautifulSoup(title, "html.parser").get_text(strip=True)
            link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
            
            doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", link)
            doi = doi_match.group(0) if doi_match else ""
            
            pub_str = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
            dt = None
            if pub_str:
                for fmt in ["%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"]:
                    try:
                        dt = datetime.strptime(pub_str, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass
            if not dt:
                dt = datetime.now(timezone.utc)
                
            desc_html = desc_elem.text if desc_elem is not None and desc_elem.text else ""
            clean_abstract = clean_jats_abstract(desc_html)
            
            articles.append({
                "title": title,
                "link": link,
                "doi": doi,
                "guid": doi if doi else link,
                "authors": "",
                "date": dt,
                "status": "Online First",
                "abstract": clean_abstract,
                "source": "Springer Official RSS"
            })
            
        return articles
    except Exception as e:
        logger.warning(f"Failed to fetch Springer RSS: {e}")
        return []


def fetch_springer_online_first_web(journal_id: str = "11747") -> list:
    """
    Scrape Springer Online First webpage as additional fallback/enrichment.
    """
    session = get_requests_session()
    url = f"https://link.springer.com/journal/{journal_id}/online-first"
    logger.info(f"Scraping Springer Online First webpage: {url}...")
    articles = []
    
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        cards = soup.find_all(["li", "article"], class_=lambda c: c and ("c-card" in c or "app-card" in c or "c-listing__item" in c))
        for card in cards:
            title_tag = card.find(["h3", "h2", "a"], class_=lambda c: c and "title" in c.lower()) or card.find(["h3", "h2"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            
            link_tag = title_tag if title_tag.name == "a" else card.find("a", href=True)
            href = link_tag.get("href", "") if link_tag else ""
            if href.startswith("/"):
                href = f"https://link.springer.com{href}"
                
            doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", href)
            doi = doi_match.group(0) if doi_match else ""
            
            authors_tags = card.find_all("li", class_=lambda c: c and "author" in c.lower())
            authors = [a.get_text(strip=True) for a in authors_tags if a.get_text(strip=True)]
            author_str = ", ".join(authors) if authors else ""
            
            articles.append({
                "title": title,
                "link": href,
                "doi": doi,
                "guid": doi if doi else href,
                "authors": author_str,
                "date": datetime.now(timezone.utc),
                "status": "Online First",
                "abstract": "",
                "source": "Springer Online First Web"
            })
            
        logger.info(f"Scraped {len(articles)} articles from Springer Online First webpage.")
        return articles
    except Exception as e:
        logger.warning(f"Error scraping Springer web page: {e}")
        return []


def merge_and_deduplicate(primary_list: list, secondary_list: list, max_count: int = 60) -> list:
    """
    Merge multiple article lists, deduplicating by DOI or link, keeping richer metadata.
    """
    merged_dict = {}
    
    for item in secondary_list + primary_list:
        key = item.get("doi") or item.get("link")
        if not key:
            continue
        key = key.lower().strip()
        
        if key not in merged_dict:
            merged_dict[key] = item
        else:
            existing = merged_dict[key]
            for field in ["authors", "abstract", "doi", "status", "title", "link"]:
                if item.get(field) and (not existing.get(field) or len(str(item.get(field))) > len(str(existing.get(field)))):
                    existing[field] = item[field]
            if item.get("date") and item["date"] > existing.get("date", datetime.min.replace(tzinfo=timezone.utc)):
                existing["date"] = item["date"]
                
    result = list(merged_dict.values())
    result.sort(key=lambda x: x.get("date", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return result[:max_count]


def build_rss_xml(
    journal_title: str,
    journal_link: str,
    feed_self_link: str,
    description: str,
    articles: list
) -> str:
    """
    Construct standardized, strictly compliant RSS 2.0 XML.
    """
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    
    # Channel metadata
    ET.SubElement(channel, "title").text = journal_title
    ET.SubElement(channel, "link").text = journal_link
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "lastBuildDate").text = format_rfc822_date(datetime.now(timezone.utc))
    ET.SubElement(channel, "generator").text = "MarketingJournalRSS Bot (https://github.com/qinhuanyu/marketing-journal-rss)"
    
    # Self atom link
    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {
        "href": feed_self_link,
        "rel": "self",
        "type": "application/rss+xml"
    })
    
    for art in articles:
        item = ET.SubElement(channel, "item")
        
        ET.SubElement(item, "title").text = art["title"]
        ET.SubElement(item, "link").text = art["link"]
        
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false" if art.get("doi") else "true"})
        guid.text = art.get("doi") if art.get("doi") else art["link"]
        
        ET.SubElement(item, "pubDate").text = format_rfc822_date(art["date"])
        
        if art.get("authors"):
            ET.SubElement(item, "{http://purl.org/dc/elements/1.1/}creator").text = art["authors"]
            
        desc_parts = []
        if art.get("authors"):
            desc_parts.append(f"<p><strong>Authors:</strong> {html.escape(art['authors'])}</p>")
        if art.get("doi"):
            doi_link = f"https://doi.org/{html.escape(art['doi'])}"
            desc_parts.append(f"<p><strong>DOI:</strong> <a href=\"{doi_link}\" target=\"_blank\">{html.escape(art['doi'])}</a></p>")
        if art.get("status"):
            desc_parts.append(f"<p><strong>Status:</strong> {html.escape(art['status'])}</p>")
        
        date_str = art["date"].strftime("%Y-%m-%d")
        desc_parts.append(f"<p><strong>Online Publication Date:</strong> {date_str}</p>")
        
        if art.get("abstract"):
            desc_parts.append(f"<p><strong>Abstract:</strong><br/>{html.escape(art['abstract'])}</p>")
            
        desc_parts.append(f"<p><a href=\"{html.escape(art['link'])}\" target=\"_blank\">Read Full Article at Publisher &rarr;</a></p>")
        
        desc_html = "".join(desc_parts)
        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = desc_html
        
    rough_string = ET.tostring(rss, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def generate_index_html(jcr_count: int, jams_count: int, jcr_latest: dict, jams_latest: dict) -> str:
    """Generate docs/index.html web dashboard."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    jcr_title = html.escape(jcr_latest.get("title", "N/A")) if jcr_latest else "N/A"
    jcr_date = jcr_latest.get("date", datetime.now(timezone.utc)).strftime("%Y-%m-%d") if jcr_latest else "N/A"
    
    jams_title = html.escape(jams_latest.get("title", "N/A")) if jams_latest else "N/A"
    jams_date = jams_latest.get("date", datetime.now(timezone.utc)).strftime("%Y-%m-%d") if jams_latest else "N/A"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Marketing Journal RSS Feeds</title>
  <meta name="description" content="Real-time RSS feeds for Advance Articles and Online First papers from top marketing journals: JCR and JAMS.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --accent: #818cf8;
      --border: #334155;
      --badge-bg: #0369a1;
      --badge-text: #e0f2fe;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2.5rem 1rem;
    }}
    .container {{
      max-width: 880px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      margin-bottom: 3rem;
    }}
    h1 {{
      font-size: 2.25rem;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.025em;
      margin-bottom: 0.75rem;
    }}
    .subtitle {{
      color: var(--text-muted);
      font-size: 1.05rem;
      max-width: 600px;
      margin: 0 auto;
    }}
    .status-bar {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      padding: 0.4rem 0.9rem;
      border-radius: 9999px;
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: 1.25rem;
    }}
    .status-dot {{
      width: 8px;
      height: 8px;
      background-color: #22c55e;
      border-radius: 50%;
      box-shadow: 0 0 8px #22c55e;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 1.75rem;
      margin-bottom: 3rem;
    }}
    @media (min-width: 768px) {{
      .grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    .card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.2s, border-color 0.2s;
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: var(--primary);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1rem;
    }}
    .journal-tag {{
      background: var(--badge-bg);
      color: var(--badge-text);
      padding: 0.2rem 0.6rem;
      border-radius: 0.375rem;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .card-title {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }}
    .publisher {{
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-bottom: 1rem;
    }}
    .meta-box {{
      background: #0f172a80;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.85rem;
      margin-bottom: 1.25rem;
      font-size: 0.85rem;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 0.3rem;
    }}
    .meta-row:last-child {{ margin-bottom: 0; }}
    .meta-label {{ color: var(--text-muted); }}
    .meta-value {{ font-weight: 500; text-align: right; }}
    .rss-url-container {{
      position: relative;
      margin-bottom: 1rem;
    }}
    .rss-input {{
      width: 100%;
      background-color: #0f172a;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.65rem 0.85rem;
      color: var(--text);
      font-size: 0.85rem;
      font-family: monospace;
      outline: none;
    }}
    .rss-input:focus {{
      border-color: var(--primary);
    }}
    .btn-group {{
      display: flex;
      gap: 0.5rem;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.65rem 1rem;
      border-radius: 0.5rem;
      font-size: 0.9rem;
      font-weight: 500;
      text-decoration: none;
      cursor: pointer;
      border: none;
      transition: background-color 0.2s;
    }}
    .btn-primary {{
      background-color: var(--primary);
      color: #0f172a;
      font-weight: 600;
      flex: 1;
    }}
    .btn-primary:hover {{
      background-color: var(--primary-hover);
    }}
    .btn-secondary {{
      background-color: #334155;
      color: var(--text);
      padding: 0.65rem 0.85rem;
    }}
    .btn-secondary:hover {{
      background-color: #475569;
    }}
    .info-section {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.75rem;
      margin-bottom: 2rem;
    }}
    .info-section h2 {{
      font-size: 1.2rem;
      font-weight: 600;
      margin-bottom: 1rem;
      color: var(--primary);
    }}
    .info-section ul {{
      list-style-position: inside;
      color: var(--text-muted);
      font-size: 0.95rem;
    }}
    .info-section li {{
      margin-bottom: 0.5rem;
    }}
    footer {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.85rem;
      margin-top: 2rem;
    }}
    footer a {{ color: var(--primary); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Marketing Journal RSS Feeds</h1>
      <p class="subtitle">Automatic tracking of Advance Articles & Online First papers from premier marketing journals.</p>
      <div class="status-bar">
        <span class="status-dot"></span>
        <span>Auto-updated every 6h &bull; Last Generated: <strong>{now_utc}</strong></span>
      </div>
    </header>

    <div class="grid">
      <!-- JCR Card -->
      <div class="card">
        <div>
          <div class="card-header">
            <span class="journal-tag">Advance Articles</span>
            <span style="font-size: 0.85rem; color: var(--text-muted);">{jcr_count} papers</span>
          </div>
          <h2 class="card-title">Journal of Consumer Research (JCR)</h2>
          <p class="publisher">Publisher: Oxford University Press (OUP)</p>
          <div class="meta-box">
            <div class="meta-row">
              <span class="meta-label">Coverage:</span>
              <span class="meta-value">Accepted Manuscripts / Advance</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Paper:</span>
              <span class="meta-value" style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{jcr_title}">{jcr_title}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Date:</span>
              <span class="meta-value">{jcr_date}</span>
            </div>
          </div>
          <div class="rss-url-container">
            <input type="text" readonly class="rss-input" id="jcr-url" value="{BASE_GITHUB_IO_URL}/jcr.xml">
          </div>
        </div>
        <div class="btn-group">
          <button class="btn btn-secondary" onclick="navigator.clipboard.writeText(document.getElementById('jcr-url').value); alert('JCR RSS URL Copied!');">Copy URL</button>
          <a class="btn btn-primary" href="jcr.xml" target="_blank">View RSS XML</a>
        </div>
      </div>

      <!-- JAMS Card -->
      <div class="card">
        <div>
          <div class="card-header">
            <span class="journal-tag">Online First</span>
            <span style="font-size: 0.85rem; color: var(--text-muted);">{jams_count} papers</span>
          </div>
          <h2 class="card-title">Journal of the Academy of Marketing Science (JAMS)</h2>
          <p class="publisher">Publisher: Springer Nature</p>
          <div class="meta-box">
            <div class="meta-row">
              <span class="meta-label">Coverage:</span>
              <span class="meta-value">Online First Articles</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Paper:</span>
              <span class="meta-value" style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{jams_title}">{jams_title}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Date:</span>
              <span class="meta-value">{jams_date}</span>
            </div>
          </div>
          <div class="rss-url-container">
            <input type="text" readonly class="rss-input" id="jams-url" value="{BASE_GITHUB_IO_URL}/jams.xml">
          </div>
        </div>
        <div class="btn-group">
          <button class="btn btn-secondary" onclick="navigator.clipboard.writeText(document.getElementById('jams-url').value); alert('JAMS RSS URL Copied!');">Copy URL</button>
          <a class="btn btn-primary" href="jams.xml" target="_blank">View RSS XML</a>
        </div>
      </div>
    </div>

    <div class="info-section">
      <h2>How to Subscribe in RSS Readers & Tools</h2>
      <ul>
        <li><strong>Feedly / Inoreader / NetNewsWire:</strong> Click "Add Feed" and paste either RSS URL above.</li>
        <li><strong>Zotero:</strong> In Zotero, click File &rarr; New Library &rarr; New Feed &rarr; From URL, and enter the RSS feed URL to auto-import newly accepted marketing research papers.</li>
        <li><strong>Updates:</strong> GitHub Actions runs every 6 hours automatically to fetch and publish new papers without manual intervention.</li>
      </ul>
    </div>

    <footer>
      <p>Maintained by <a href="https://github.com/qinhuanyu/marketing-journal-rss" target="_blank">qinhuanyu/marketing-journal-rss</a> &bull; Powered by GitHub Actions & Pages</p>
    </footer>
  </div>
</body>
</html>
"""


def main():
    logger.info("=== Starting Marketing Journal RSS Generation ===")
    os.makedirs("docs", exist_ok=True)
    
    # 1. JCR Processing
    logger.info("--- Processing JCR ---")
    jcr_articles = fetch_crossref_articles(issn="0093-5301", journal_name="Journal of Consumer Research", max_rows=60)
    if not jcr_articles:
        logger.warning("Falling back to electronic ISSN 1537-5277 for JCR...")
        jcr_articles = fetch_crossref_articles(issn="1537-5277", journal_name="Journal of Consumer Research", max_rows=60)
        
    jcr_xml = build_rss_xml(
        journal_title="Journal of Consumer Research - Advance Articles",
        journal_link="https://academic.oup.com/jcr/advance-articles",
        feed_self_link=f"{BASE_GITHUB_IO_URL}/jcr.xml",
        description="Latest Advance Articles and Accepted Manuscripts from Journal of Consumer Research (JCR)",
        articles=jcr_articles
    )
    with open("docs/jcr.xml", "w", encoding="utf-8") as f:
        f.write(jcr_xml)
    logger.info(f"Successfully generated docs/jcr.xml ({len(jcr_articles)} articles).")
    
    # 2. JAMS Processing
    logger.info("--- Processing JAMS ---")
    jams_cr = fetch_crossref_articles(issn="0092-0703", journal_name="Journal of the Academy of Marketing Science", max_rows=60)
    jams_rss = fetch_springer_rss(journal_id="11747")
    jams_web = fetch_springer_online_first_web(journal_id="11747") if len(jams_cr) < 10 else []
    
    jams_articles = merge_and_deduplicate(primary_list=jams_cr, secondary_list=jams_rss + jams_web, max_count=60)
    
    jams_xml = build_rss_xml(
        journal_title="Journal of the Academy of Marketing Science - Online First",
        journal_link="https://link.springer.com/journal/11747/online-first",
        feed_self_link=f"{BASE_GITHUB_IO_URL}/jams.xml",
        description="Latest Online First articles from Journal of the Academy of Marketing Science (JAMS)",
        articles=jams_articles
    )
    with open("docs/jams.xml", "w", encoding="utf-8") as f:
        f.write(jams_xml)
    logger.info(f"Successfully generated docs/jams.xml ({len(jams_articles)} articles).")
    
    # 3. Generate docs/index.html
    jcr_latest = jcr_articles[0] if jcr_articles else None
    jams_latest = jams_articles[0] if jams_articles else None
    
    index_html = generate_index_html(
        jcr_count=len(jcr_articles),
        jams_count=len(jams_articles),
        jcr_latest=jcr_latest,
        jams_latest=jams_latest
    )
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    logger.info("Successfully generated docs/index.html.")
    
    logger.info("=== All feeds and dashboard generated successfully ===")


if __name__ == "__main__":
    main()
