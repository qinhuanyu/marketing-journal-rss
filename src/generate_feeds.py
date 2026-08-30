#!/usr/bin/env python3
"""
Marketing Journal RSS Generator
Generates automated, rich, Zotero-compatible RSS 2.0 feeds for 9 top marketing journals:
1. JCR  - Journal of Consumer Research (Oxford University Press)
2. JAMS - Journal of the Academy of Marketing Science (Springer Nature)
3. JM   - Journal of Marketing (SAGE / AMA)
4. JMR  - Journal of Marketing Research (SAGE / AMA)
5. JCP  - Journal of Consumer Psychology (Wiley / SCP)
6. IJRM - International Journal of Research in Marketing (Elsevier / EMAC)
7. JR   - Journal of Retailing (Elsevier)
8. JSR  - Journal of Service Research (SAGE)
9. MS   - Marketing Science (INFORMS)

Outputs valid RSS 2.0 XML files in docs/ and updates the docs/index.html web dashboard.
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

MIN_FEED_ARTICLES = 10

NON_RESEARCH_PATTERNS = [
    r'^Correction to:',
    r'^Erratum',
    r'^Retraction',
    r'^Expression of Concern',
    r'^Editorial Expression of Concern',
    r'^Call for Papers',
    r'^Editorial Board',
    r'^Publisher\'?s Note',
    r'^Author Correction',
    r'^Issue Information',
    r'^Table of Contents',
    r'^Cover Image',
    r'^Front Cover',
    r'^Back Cover',
    r'^Front Matter',
    r'^Back Matter',
    r'^FM \w+:',
    r'Copyright/ ID Statement',
    r'Copyright Statement',
    r'^Index to Volume',
    r'Reviewers for Volume',
    r'Ad Hoc Reviewers',
    r'^In Memoriam',
    r'^Corrigendum',
    r'Welcomes New Co-Editors',
    r'Welcomes New',
    r'^A Word of Thanks',
    r'^Word of Thanks',
    r'^Focus on Authors',
    r'^About the Authors',
    r'^Author Index',
    r'^Subject Index',
    r'^Acknowledgment of Reviewers',
    r'^Reviewer Acknowledgment'
]


def is_research_article(title: str, item_type: str = "journal-article", authors: list = None) -> bool:
    """Verify if an entry represents a legitimate research article rather than administrative noise."""
    if not title or len(title.strip()) < 3:
        return False
    if item_type and item_type not in ["journal-article", "article"]:
        return False
    for pattern in NON_RESEARCH_PATTERNS:
        if re.search(pattern, title.strip(), re.IGNORECASE):
            return False
    if authors is not None and len(authors) == 0:
        return False
    return True


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
    """Clean JATS XML tags and HTML markup from abstracts while preserving readability."""
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


def normalize_title(t: str) -> str:
    """Normalize title for fuzzy deduplication."""
    return re.sub(r'[^a-z0-9]', '', t.lower())


def fetch_crossref_articles(
    primary_issn: str,
    secondary_issn: str,
    journal_name: str,
    default_status: str = "Online First",
    max_rows: int = 70
) -> list:
    """
    Fetch articles directly from official Crossref REST API using journal ISSNs.
    Returns list of standardized article dicts.
    """
    session = get_requests_session()
    articles = []
    issns_to_try = [primary_issn]
    if secondary_issn and secondary_issn != primary_issn:
        issns_to_try.append(secondary_issn)
        
    for issn in issns_to_try:
        url = f"https://api.crossref.org/journals/{issn}/works?sort=published&order=desc&rows={max_rows}"
        logger.info(f"Fetching Crossref metadata for {journal_name} (ISSN: {issn})...")
        try:
            resp = session.get(url, headers=HEADERS, timeout=25)
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                logger.info(f"Retrieved {len(items)} works for {journal_name} (ISSN: {issn}) from Crossref.")
                for it in items:
                    title_list = it.get("title", [])
                    raw_title = title_list[0] if title_list else ""
                    title = BeautifulSoup(raw_title, "html.parser").get_text(separator=" ", strip=True)
                    item_type = it.get("type", "journal-article")
                    raw_authors = it.get("author", [])
                    
                    if not is_research_article(title, item_type, raw_authors):
                        continue
                        
                    doi = it.get("DOI", "").strip()
                    article_url = f"https://doi.org/{doi}" if doi else it.get("URL", "")
                    
                    authors = []
                    for a in raw_authors:
                        given = a.get("given", "").strip()
                        family = a.get("family", "").strip()
                        if family or given:
                            authors.append(f"{given} {family}".strip())
                    author_str = ", ".join(authors) if authors else ""
                    
                    dt = None
                    for dk in ["published-online", "published", "created", "deposited"]:
                        dp = it.get(dk, {}).get("date-parts", [[]])
                        if dp and dp[0]:
                            dt = parse_date_parts_to_datetime(dp[0])
                            break
                    if not dt:
                        dt = datetime.now(timezone.utc)
                        
                    raw_abstract = it.get("abstract", "")
                    clean_abstract = clean_jats_abstract(raw_abstract)
                    
                    volume = it.get("volume")
                    issue = it.get("issue")
                    if not volume or not issue:
                        status = default_status
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
                        "source": f"Crossref ({issn})"
                    })
                if len(articles) >= MIN_FEED_ARTICLES:
                    break
        except Exception as e:
            logger.error(f"Failed to fetch Crossref data for {journal_name} ({issn}): {e}")
            
    return articles


def fetch_springer_rss(journal_id: str = "11747") -> list:
    """Fetch and parse Springer search RSS feed for a journal ID."""
    session = get_requests_session()
    url = f"https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id={journal_id}"
    logger.info(f"Fetching Springer official RSS for journal ID {journal_id}...")
    articles = []
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall("./channel/item")
            for it in items:
                title_elem = it.find("title")
                link_elem = it.find("link")
                pub_elem = it.find("pubDate")
                desc_elem = it.find("description")
                
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                title = BeautifulSoup(title, "html.parser").get_text(separator=" ", strip=True)
                if not is_research_article(title):
                    continue
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
            logger.info(f"Parsed {len(articles)} research items from Springer RSS.")
    except Exception as e:
        logger.warning(f"Failed to fetch Springer RSS: {e}")
    return articles


def fetch_springer_online_first_web(journal_id: str = "11747") -> list:
    """Scrape Springer Online First webpage as fallback/enrichment."""
    session = get_requests_session()
    url = f"https://link.springer.com/journal/{journal_id}/online-first"
    logger.info(f"Scraping Springer Online First webpage: {url}...")
    articles = []
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all(["li", "article"], class_=lambda c: c and ("c-card" in c or "app-card" in c or "c-listing__item" in c))
            for card in cards:
                title_tag = card.find(["h3", "h2", "a"], class_=lambda c: c and "title" in c.lower()) or card.find(["h3", "h2"])
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not is_research_article(title):
                    continue
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
    except Exception as e:
        logger.warning(f"Error scraping Springer web page: {e}")
    return articles


def fetch_wiley_rss(feed_url: str, default_status: str = "Early View") -> list:
    """Fetch and parse Wiley RSS feed."""
    session = get_requests_session()
    articles = []
    logger.info(f"Fetching Wiley RSS feed: {feed_url}...")
    try:
        resp = session.get(feed_url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall("./channel/item")
            for it in items:
                raw_title = it.findtext("title", "")
                title = BeautifulSoup(raw_title, "html.parser").get_text(separator=" ", strip=True)
                
                creator = it.findtext("{http://purl.org/dc/elements/1.1/}creator") or ""
                creator = re.sub(r"\s+", " ", creator).strip().strip(",")
                
                if not is_research_article(title, authors=[creator] if creator else []):
                    continue
                link = it.findtext("link", "").strip()
                doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", link)
                doi = doi_match.group(0) if doi_match else ""
                
                pub_str = it.findtext("pubDate", "").strip()
                dt = None
                if pub_str:
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"]:
                        try:
                            dt = datetime.strptime(pub_str, fmt).astimezone(timezone.utc)
                            break
                        except ValueError:
                            pass
                if not dt:
                    dt = datetime.now(timezone.utc)
                    
                desc = it.findtext("description", "")
                clean_abstract = clean_jats_abstract(desc)
                
                articles.append({
                    "title": title,
                    "link": link,
                    "doi": doi,
                    "guid": doi if doi else link,
                    "authors": creator,
                    "date": dt,
                    "status": default_status,
                    "abstract": clean_abstract,
                    "source": "Wiley RSS"
                })
            logger.info(f"Parsed {len(articles)} items from Wiley RSS.")
    except Exception as e:
        logger.warning(f"Wiley RSS error: {e}")
    return articles


def fetch_sciencedirect_rss(feed_url: str, default_status: str = "Articles in Press / Online First") -> list:
    """Fetch and parse Elsevier ScienceDirect RSS feed, extracting precise dates and authors."""
    session = get_requests_session()
    articles = []
    logger.info(f"Fetching ScienceDirect RSS feed: {feed_url}...")
    try:
        resp = session.get(feed_url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall("./channel/item")
            for it in items:
                raw_title = it.findtext("title", "")
                title = BeautifulSoup(raw_title, "html.parser").get_text(separator=" ", strip=True)
                desc = it.findtext("description", "")
                
                authors_match = re.search(r"Author\(s\):\s*([^<]+)", desc)
                authors = authors_match.group(1).strip() if authors_match else ""
                
                if not is_research_article(title, authors=[authors] if authors else []):
                    continue
                link = it.findtext("link", "").strip()
                
                dt = None
                date_match = re.search(r"Publication date:\s*(?:Available online\s*)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", desc)
                if date_match:
                    try:
                        dt = datetime.strptime(date_match.group(1), "%d %B %Y").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
                if not dt:
                    month_year = re.search(r"Publication date:\s*([A-Za-z]+\s+\d{4})", desc)
                    if month_year:
                        try:
                            dt = datetime.strptime(month_year.group(1), "%B %Y").replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                if not dt:
                    dt = datetime.now(timezone.utc)
                    
                abstract = ""
                snippet_match = re.search(r"Abstract:\s*([^<]+)", desc)
                if snippet_match:
                    abstract = snippet_match.group(1).strip()
                elif "<p>" in desc:
                    abstract = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)
                    
                articles.append({
                    "title": title,
                    "link": link,
                    "doi": "",
                    "guid": link,
                    "authors": authors,
                    "date": dt,
                    "status": default_status,
                    "abstract": clean_jats_abstract(abstract),
                    "source": "ScienceDirect RSS"
                })
            logger.info(f"Parsed {len(articles)} items from ScienceDirect RSS.")
    except Exception as e:
        logger.warning(f"ScienceDirect RSS error: {e}")
    return articles


def merge_and_deduplicate(primary_list: list, secondary_list: list, max_count: int = 60) -> list:
    """
    Merge multiple article lists, deduplicating by DOI or normalized title,
    keeping richer metadata and newest verified dates.
    """
    merged_dict = {}
    title_to_key = {}
    
    for item in secondary_list + primary_list:
        doi = item.get("doi", "").lower().strip()
        norm_title = normalize_title(item.get("title", ""))
        
        key = doi if doi else (title_to_key.get(norm_title) or item.get("link", "").lower().strip())
        if not key:
            continue
            
        if norm_title and norm_title not in title_to_key:
            title_to_key[norm_title] = key
            
        if key not in merged_dict:
            existing_key = title_to_key.get(norm_title)
            if existing_key and existing_key in merged_dict:
                key = existing_key
            else:
                merged_dict[key] = dict(item)
                continue
                
        existing = merged_dict[key]
        for field in ["authors", "abstract", "doi", "status", "title", "link", "guid"]:
            val = item.get(field)
            if val and (not existing.get(field) or len(str(val)) > len(str(existing.get(field, "")))):
                existing[field] = val
        if item.get("doi") and not existing.get("doi"):
            existing["doi"] = item["doi"]
            existing["guid"] = item["doi"]
            existing["link"] = f"https://doi.org/{item['doi']}"
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
    """Construct standardized, strictly compliant RSS 2.0 XML with Zotero compatibility."""
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


def safe_write_feed(file_path: str, new_xml_content: str, article_count: int, min_threshold: int = MIN_FEED_ARTICLES) -> bool:
    """Ensure a valid feed is never replaced with empty or corrupted content."""
    if article_count < min_threshold:
        logger.error(
            f"Fetched only {article_count} articles for {file_path}. "
            f"Aborting write to preserve existing feed."
        )
        return False
    
    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(new_xml_content)
    os.replace(temp_path, file_path)
    logger.info(f"Successfully updated {file_path} with {article_count} articles.")
    return True


def generate_index_html(journal_stats: list) -> str:
    """Generate docs/index.html web dashboard for all 9 journals."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    cards_html = []
    for stat in journal_stats:
        j_id = stat["id"]
        short_name = stat["short_name"]
        full_name = stat["full_name"]
        publisher = stat["publisher"]
        stage = stat["stage"]
        count = stat["count"]
        latest_title = html.escape(stat["latest_title"])
        latest_date = stat["latest_date"]
        rss_url = f"{BASE_GITHUB_IO_URL}/{j_id}.xml"
        
        card = f"""      <!-- {short_name} Card -->
      <div class="card">
        <div>
          <div class="card-header">
            <span class="journal-tag">{stage}</span>
            <span style="font-size: 0.85rem; color: var(--text-muted);">{count} papers</span>
          </div>
          <h2 class="card-title">{full_name} ({short_name})</h2>
          <p class="publisher">Publisher: {publisher}</p>
          <div class="meta-box">
            <div class="meta-row">
              <span class="meta-label">Coverage:</span>
              <span class="meta-value">{stage}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Paper:</span>
              <span class="meta-value" style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{latest_title}">{latest_title}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">Latest Date:</span>
              <span class="meta-value">{latest_date}</span>
            </div>
          </div>
          <div class="rss-url-container">
            <input type="text" readonly class="rss-input" id="{j_id}-url" value="{rss_url}">
          </div>
        </div>
        <div class="btn-group">
          <button class="btn btn-secondary" onclick="navigator.clipboard.writeText(document.getElementById('{j_id}-url').value); alert('{short_name} RSS URL Copied!');">Copy URL</button>
          <a class="btn btn-primary" href="{j_id}.xml" target="_blank">View RSS XML</a>
        </div>
      </div>"""
        cards_html.append(card)

    cards_joined = "\n\n".join(cards_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Marketing Journal RSS Feeds</title>
  <meta name="description" content="Real-time RSS feeds for Advance Articles and Online First papers from 9 premier academic marketing journals: JCR, JAMS, JM, JMR, JCP, IJRM, JR, JSR, and MS.">
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
      max-width: 1080px;
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
      max-width: 750px;
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
    @media (min-width: 640px) {{
      .grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (min-width: 1024px) {{
      .grid {{ grid-template-columns: repeat(3, 1fr); }}
    }}
    .card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.5rem;
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
      margin-bottom: 0.75rem;
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
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 0.35rem;
      line-height: 1.35;
    }}
    .publisher {{
      color: var(--text-muted);
      font-size: 0.85rem;
      margin-bottom: 0.85rem;
    }}
    .meta-box {{
      background: #0f172a80;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.75rem;
      margin-bottom: 1rem;
      font-size: 0.82rem;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 0.25rem;
    }}
    .meta-row:last-child {{ margin-bottom: 0; }}
    .meta-label {{ color: var(--text-muted); }}
    .meta-value {{ font-weight: 500; text-align: right; }}
    .rss-url-container {{
      position: relative;
      margin-bottom: 0.85rem;
    }}
    .rss-input {{
      width: 100%;
      background-color: #0f172a;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 0.55rem 0.75rem;
      color: var(--text);
      font-size: 0.8rem;
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
      padding: 0.55rem 0.85rem;
      border-radius: 0.5rem;
      font-size: 0.85rem;
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
      padding: 0.55rem 0.75rem;
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
      <p class="subtitle">Automatic tracking of Advance Articles, Accepted Manuscripts & Online First papers from 9 premier marketing journals.</p>
      <div class="status-bar">
        <span class="status-dot"></span>
        <span>Auto-updated every 6h &bull; Last Generated: <strong>{now_utc}</strong></span>
      </div>
    </header>

    <div class="grid">
{cards_joined}
    </div>

    <div class="info-section">
      <h2>How to Subscribe in RSS Readers & Zotero</h2>
      <ul>
        <li><strong>Feedly / Inoreader / NetNewsWire:</strong> Click "Add Feed" / "Subscribe" and paste any of the RSS URLs above.</li>
        <li><strong>Zotero:</strong> In Zotero, click File &rarr; New Library &rarr; New Feed &rarr; From URL, and enter the RSS feed URL to auto-import newly accepted marketing research papers with full bibliographic citations.</li>
        <li><strong>Automated Updates:</strong> GitHub Actions runs every 6 hours automatically to fetch and publish new papers without manual intervention.</li>
      </ul>
    </div>

    <footer>
      <p>Maintained by <a href="https://github.com/qinhuanyu/marketing-journal-rss" target="_blank">qinhuanyu/marketing-journal-rss</a> &bull; Powered by GitHub Actions & Pages</p>
    </footer>
  </div>
</body>
</html>
"""


JOURNALS = [
    {
        "id": "jcr",
        "title": "Journal of Consumer Research - Advance Articles",
        "short_name": "JCR",
        "full_name": "Journal of Consumer Research",
        "publisher": "Oxford University Press (OUP)",
        "stage": "Advance Articles / Accepted Manuscripts",
        "link": "https://academic.oup.com/jcr/advance-articles",
        "primary_issn": "0093-5301",
        "secondary_issn": "1537-5277",
        "default_status": "Advance Article / Accepted Manuscript",
        "description": "Latest Advance Articles and Accepted Manuscripts from Journal of Consumer Research (JCR)",
        "adapter": "crossref_only"
    },
    {
        "id": "jams",
        "title": "Journal of the Academy of Marketing Science - Online First",
        "short_name": "JAMS",
        "full_name": "Journal of the Academy of Marketing Science",
        "publisher": "Springer Nature",
        "stage": "Online First Articles",
        "link": "https://link.springer.com/journal/11747/online-first",
        "primary_issn": "0092-0703",
        "secondary_issn": "1552-7824",
        "springer_id": "11747",
        "default_status": "Online First",
        "description": "Latest Online First articles from Journal of the Academy of Marketing Science (JAMS)",
        "adapter": "springer_multi"
    },
    {
        "id": "jm",
        "title": "Journal of Marketing - OnlineFirst",
        "short_name": "JM",
        "full_name": "Journal of Marketing",
        "publisher": "SAGE Publications / AMA",
        "stage": "OnlineFirst Articles",
        "link": "https://journals.sagepub.com/toc/jmxa/0/0",
        "primary_issn": "0022-2429",
        "secondary_issn": "1547-7185",
        "default_status": "OnlineFirst / Express Article",
        "description": "Latest OnlineFirst and Advance articles from Journal of Marketing (JM)",
        "adapter": "crossref_only"
    },
    {
        "id": "jmr",
        "title": "Journal of Marketing Research - OnlineFirst",
        "short_name": "JMR",
        "full_name": "Journal of Marketing Research",
        "publisher": "SAGE Publications / AMA",
        "stage": "OnlineFirst Articles",
        "link": "https://journals.sagepub.com/toc/mrqa/0/0",
        "primary_issn": "0022-2437",
        "secondary_issn": "1547-7193",
        "default_status": "OnlineFirst / Express Article",
        "description": "Latest OnlineFirst and Advance articles from Journal of Marketing Research (JMR)",
        "adapter": "crossref_only"
    },
    {
        "id": "jcp",
        "title": "Journal of Consumer Psychology - Early View",
        "short_name": "JCP",
        "full_name": "Journal of Consumer Psychology",
        "publisher": "Wiley / SCP",
        "stage": "Early View Articles",
        "link": "https://myscp.onlinelibrary.wiley.com/journal/15327663",
        "primary_issn": "1057-7408",
        "secondary_issn": "1532-7663",
        "wiley_feed": "https://onlinelibrary.wiley.com/feed/15327663/most-recent",
        "default_status": "Early View",
        "description": "Latest Early View and Advance articles from Journal of Consumer Psychology (JCP)",
        "adapter": "wiley_multi"
    },
    {
        "id": "ijrm",
        "title": "International Journal of Research in Marketing - Articles in Press",
        "short_name": "IJRM",
        "full_name": "International Journal of Research in Marketing",
        "publisher": "Elsevier / EMAC",
        "stage": "Articles in Press / Online First",
        "link": "https://www.sciencedirect.com/journal/international-journal-of-research-in-marketing/articles-in-press",
        "primary_issn": "0167-8116",
        "secondary_issn": "1873-8001",
        "sciencedirect_feed": "https://rss.sciencedirect.com/publication/science/01678116",
        "default_status": "Articles in Press / Online First",
        "description": "Latest Articles in Press and Online First papers from International Journal of Research in Marketing (IJRM)",
        "adapter": "elsevier_multi"
    },
    {
        "id": "jr",
        "title": "Journal of Retailing - Articles in Press",
        "short_name": "JR",
        "full_name": "Journal of Retailing",
        "publisher": "Elsevier",
        "stage": "Articles in Press / Online First",
        "link": "https://www.sciencedirect.com/journal/journal-of-retailing/articles-in-press",
        "primary_issn": "0022-4359",
        "secondary_issn": "1873-6572",
        "sciencedirect_feed": "https://rss.sciencedirect.com/publication/science/00224359",
        "default_status": "Articles in Press / Online First",
        "description": "Latest Articles in Press and Online First papers from Journal of Retailing (JR)",
        "adapter": "elsevier_multi"
    },
    {
        "id": "jsr",
        "title": "Journal of Service Research - OnlineFirst",
        "short_name": "JSR",
        "full_name": "Journal of Service Research",
        "publisher": "SAGE Publications",
        "stage": "OnlineFirst Articles",
        "link": "https://journals.sagepub.com/toc/jsra/0/0",
        "primary_issn": "1094-6705",
        "secondary_issn": "1552-7379",
        "default_status": "OnlineFirst / Express Article",
        "description": "Latest OnlineFirst and Advance articles from Journal of Service Research (JSR)",
        "adapter": "crossref_only"
    },
    {
        "id": "ms",
        "title": "Marketing Science - Articles in Advance",
        "short_name": "MS",
        "full_name": "Marketing Science",
        "publisher": "INFORMS",
        "stage": "Articles in Advance / Online First",
        "link": "https://pubsonline.informs.org/toc/mksc/0/0",
        "primary_issn": "0732-2399",
        "secondary_issn": "1526-548X",
        "default_status": "Articles in Advance / Online First",
        "description": "Latest Articles in Advance from Marketing Science (MS)",
        "adapter": "crossref_only"
    }
]


def process_journal(journal_cfg: dict) -> tuple:
    """Process single journal pipeline and write output XML."""
    j_id = journal_cfg["id"]
    short_name = journal_cfg["short_name"]
    full_name = journal_cfg["full_name"]
    adapter = journal_cfg["adapter"]
    default_status = journal_cfg["default_status"]
    
    logger.info(f"--- Processing {short_name} ({full_name}) ---")
    
    articles = []
    if adapter == "crossref_only":
        arts = fetch_crossref_articles(
            journal_cfg["primary_issn"],
            journal_cfg["secondary_issn"],
            full_name,
            default_status,
            max_rows=70
        )
        articles = merge_and_deduplicate(primary_list=arts, secondary_list=[], max_count=60)
        
    elif adapter == "springer_multi":
        cr = fetch_crossref_articles(
            journal_cfg["primary_issn"],
            journal_cfg["secondary_issn"],
            full_name,
            default_status,
            max_rows=70
        )
        rss = fetch_springer_rss(journal_cfg["springer_id"])
        web = fetch_springer_online_first_web(journal_cfg["springer_id"]) if len(cr) < 10 else []
        articles = merge_and_deduplicate(primary_list=cr, secondary_list=rss + web, max_count=60)
        
    elif adapter == "wiley_multi":
        cr = fetch_crossref_articles(
            journal_cfg["primary_issn"],
            journal_cfg["secondary_issn"],
            full_name,
            default_status,
            max_rows=70
        )
        rss = fetch_wiley_rss(journal_cfg["wiley_feed"], default_status)
        articles = merge_and_deduplicate(primary_list=cr, secondary_list=rss, max_count=60)
        
    elif adapter == "elsevier_multi":
        cr = fetch_crossref_articles(
            journal_cfg["primary_issn"],
            journal_cfg["secondary_issn"],
            full_name,
            default_status,
            max_rows=70
        )
        rss = fetch_sciencedirect_rss(journal_cfg["sciencedirect_feed"], default_status)
        articles = merge_and_deduplicate(primary_list=cr, secondary_list=rss, max_count=60)

    xml_path = f"docs/{j_id}.xml"
    feed_self_link = f"{BASE_GITHUB_IO_URL}/{j_id}.xml"
    
    if len(articles) >= MIN_FEED_ARTICLES:
        rss_xml = build_rss_xml(
            journal_title=journal_cfg["title"],
            journal_link=journal_cfg["link"],
            feed_self_link=feed_self_link,
            description=journal_cfg["description"],
            articles=articles
        )
        safe_write_feed(xml_path, rss_xml, len(articles))
    else:
        logger.error(f"Insufficient articles for {short_name} ({len(articles)} < {MIN_FEED_ARTICLES}). Preserving existing feed if present.")
        
    latest_art = articles[0] if articles else None
    stat = {
        "id": j_id,
        "short_name": short_name,
        "full_name": full_name,
        "publisher": journal_cfg["publisher"],
        "stage": journal_cfg["stage"],
        "count": len(articles),
        "latest_title": latest_art.get("title", "N/A") if latest_art else "N/A",
        "latest_date": latest_art["date"].strftime("%Y-%m-%d") if latest_art else "N/A"
    }
    return stat, articles


def main():
    logger.info("=== Starting Marketing Journal RSS Generation (9 Journals) ===")
    os.makedirs("docs", exist_ok=True)
    
    journal_stats = []
    for j_cfg in JOURNALS:
        try:
            stat, _ = process_journal(j_cfg)
            journal_stats.append(stat)
        except Exception as e:
            logger.error(f"Unexpected error processing journal {j_cfg['short_name']}: {e}", exc_info=True)
            # Add fallback stat
            journal_stats.append({
                "id": j_cfg["id"],
                "short_name": j_cfg["short_name"],
                "full_name": j_cfg["full_name"],
                "publisher": j_cfg["publisher"],
                "stage": j_cfg["stage"],
                "count": 0,
                "latest_title": "N/A",
                "latest_date": "N/A"
            })
            
    # Generate docs/index.html
    index_html = generate_index_html(journal_stats)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    logger.info("Successfully generated docs/index.html dashboard for 9 journals.")
    
    logger.info("=== All 9 journal feeds and dashboard generated successfully ===")


if __name__ == "__main__":
    main()
