# Marketing Journal RSS Feeds

Automated, real-time RSS feeds for Advance Articles, Accepted Manuscripts, and Online First papers from 9 premier academic marketing journals:
- **JCR** — *Journal of Consumer Research* (Oxford University Press)
- **JAMS** — *Journal of the Academy of Marketing Science* (Springer Nature)
- **JM** — *Journal of Marketing* (SAGE Publications / AMA)
- **JMR** — *Journal of Marketing Research* (SAGE Publications / AMA)
- **JCP** — *Journal of Consumer Psychology* (Wiley / SCP)
- **IJRM** — *International Journal of Research in Marketing* (Elsevier / EMAC)
- **JR** — *Journal of Retailing* (Elsevier)
- **JSR** — *Journal of Service Research* (SAGE Publications)
- **MS** — *Marketing Science* (INFORMS)

Hosted on GitHub Pages and automatically updated every 6 hours via GitHub Actions.

---

## 📡 RSS Feed URLs

| Journal | Publisher | Stage | RSS Feed URL | Direct XML |
| :--- | :--- | :--- | :--- | :--- |
| **Journal of Consumer Research (JCR)** | Oxford University Press | Advance Articles / Accepted Manuscripts | `https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml` | [jcr.xml](https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml) |
| **Journal of the Academy of Marketing Science (JAMS)** | Springer Nature | Online First Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jams.xml` | [jams.xml](https://qinhuanyu.github.io/marketing-journal-rss/jams.xml) |
| **Journal of Marketing (JM)** | SAGE / AMA | OnlineFirst / Express Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jm.xml` | [jm.xml](https://qinhuanyu.github.io/marketing-journal-rss/jm.xml) |
| **Journal of Marketing Research (JMR)** | SAGE / AMA | OnlineFirst / Express Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jmr.xml` | [jmr.xml](https://qinhuanyu.github.io/marketing-journal-rss/jmr.xml) |
| **Journal of Consumer Psychology (JCP)** | Wiley / SCP | Early View Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jcp.xml` | [jcp.xml](https://qinhuanyu.github.io/marketing-journal-rss/jcp.xml) |
| **International Journal of Research in Marketing (IJRM)** | Elsevier / EMAC | Articles in Press / Online First | `https://qinhuanyu.github.io/marketing-journal-rss/ijrm.xml` | [ijrm.xml](https://qinhuanyu.github.io/marketing-journal-rss/ijrm.xml) |
| **Journal of Retailing (JR)** | Elsevier | Articles in Press / Online First | `https://qinhuanyu.github.io/marketing-journal-rss/jr.xml` | [jr.xml](https://qinhuanyu.github.io/marketing-journal-rss/jr.xml) |
| **Journal of Service Research (JSR)** | SAGE Publications | OnlineFirst Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jsr.xml` | [jsr.xml](https://qinhuanyu.github.io/marketing-journal-rss/jsr.xml) |
| **Marketing Science (MS)** | INFORMS | Articles in Advance | `https://qinhuanyu.github.io/marketing-journal-rss/ms.xml` | [ms.xml](https://qinhuanyu.github.io/marketing-journal-rss/ms.xml) |

Web Dashboard: [https://qinhuanyu.github.io/marketing-journal-rss/](https://qinhuanyu.github.io/marketing-journal-rss/)

---

## ✨ Features & Metadata Quality

- **Early Publication Stage Tracking**: Captures newly accepted and online-published articles immediately (Accepted Manuscripts, OnlineFirst, Early View, Articles in Press), without waiting for issue or volume assignment.
- **Rich Bibliographic Metadata**:
  - Full paper title
  - Complete author lists (`dc:creator` tags formatted for Zotero recognition)
  - Permanent DOI resolution links and raw DOIs in `<guid>`
  - RFC 822 UTC standardized publication timestamps (`pubDate`)
  - Clean formatted abstracts (JATS XML tags stripped)
  - Clear publication stage status tags
- **Standard RSS 2.0 Compliant**: Fully compatible with Zotero, Feedly, Inoreader, NetNewsWire, and standard RSS aggregators.
- **Automated Updates**: Powered by GitHub Actions scheduled every 6 hours (`0 */6 * * *`) with manual trigger (`workflow_dispatch`) support.
- **Multi-Source Resilience**: Integrates Crossref REST API, publisher search RSS, and web scrapers with atomic fail-safe overwrite protection.

---

## 📖 How to Subscribe

### In RSS Readers (Feedly, Inoreader, NetNewsWire, etc.)
1. Open your RSS reader.
2. Click **Add Feed** / **Subscribe**.
3. Paste any of the RSS URLs listed above.

### In Zotero
1. In Zotero, click **File** → **New Library** → **New Feed** → **From URL**.
2. Paste the journal RSS URL (e.g. `https://qinhuanyu.github.io/marketing-journal-rss/jm.xml`).
3. Newly published marketing research articles will automatically appear with complete citation metadata in your Zotero feed.

---

## ⚙️ Repository Setup & GitHub Pages Configuration

To ensure GitHub Pages serves the feeds:

1. In your GitHub repository:
   - Navigate to **Settings** → **Pages** (in the left sidebar).
   - Under **Build and deployment** → **Source**, select **Deploy from a branch**.
   - Under **Branch**, select `main` branch and folder `/docs`.
   - Click **Save**.
2. GitHub Pages will be published at: `https://qinhuanyu.github.io/marketing-journal-rss/`

---

## 🛠️ Project Structure

```
marketing-journal-rss/
├── .github/
│   └── workflows/
│       └── update-rss.yml     # GitHub Actions workflow (runs every 6h)
├── src/
│   └── generate_feeds.py      # Core feed generator script (9 journals)
├── docs/
│   ├── index.html             # Web dashboard
│   ├── jcr.xml                # Journal of Consumer Research
│   ├── jams.xml               # Journal of the Academy of Marketing Science
│   ├── jm.xml                 # Journal of Marketing
│   ├── jmr.xml                # Journal of Marketing Research
│   ├── jcp.xml                # Journal of Consumer Psychology
│   ├── ijrm.xml               # International Journal of Research in Marketing
│   ├── jr.xml                 # Journal of Retailing
│   ├── jsr.xml                # Journal of Service Research
│   └── ms.xml                 # Marketing Science
├── requirements.txt           # Python dependencies
├── .gitignore
└── README.md
```

---

## 💻 Local Execution & Testing

```bash
# Clone the repository
git clone https://github.com/qinhuanyu/marketing-journal-rss.git
cd marketing-journal-rss

# Create virtual environment & install requirements
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the generator
python src/generate_feeds.py
```
