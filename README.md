# Marketing Journal RSS Feeds (JCR & JAMS)

Automated, real-time RSS feeds for Advance Articles and Online First papers from premier academic marketing journals:
- **Journal of Consumer Research (JCR)**
- **Journal of the Academy of Marketing Science (JAMS)**

Hosted on GitHub Pages and automatically updated every 6 hours via GitHub Actions.

---

## 📡 RSS Feed URLs

| Journal | Stage | RSS Feed URL | Direct XML |
| :--- | :--- | :--- | :--- |
| **Journal of Consumer Research (JCR)** | Advance Articles / Accepted Manuscripts | `https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml` | [jcr.xml](https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml) |
| **Journal of the Academy of Marketing Science (JAMS)** | Online First Articles | `https://qinhuanyu.github.io/marketing-journal-rss/jams.xml` | [jams.xml](https://qinhuanyu.github.io/marketing-journal-rss/jams.xml) |

Web Dashboard: [https://qinhuanyu.github.io/marketing-journal-rss/](https://qinhuanyu.github.io/marketing-journal-rss/)

---

## ✨ Features

- **Accepted Manuscript / Advance Tracking**: Captures newly accepted and online-published articles immediately, without waiting for issue or volume assignment.
- **Rich Bibliographic Metadata**:
  - Full paper title
  - Complete author lists
  - Official DOI & permanent article links
  - Exact online publication dates
  - Clean formatted abstracts (JATS tags stripped)
  - Publication status tags
- **Standard RSS 2.0 Compliant**: Fully compatible with Feedly, Inoreader, NetNewsWire, Zotero, and other standard RSS readers.
- **Automated Updates**: Powered by GitHub Actions scheduled every 6 hours (`0 */6 * * *`) with manual trigger (`workflow_dispatch`) support.
- **Zero Maintenance**: Self-contained Python script using Crossref REST API and Springer RSS feeds with automated fallback mechanisms.

---

## 📖 How to Subscribe

### In RSS Readers (Feedly, Inoreader, NetNewsWire, etc.)
1. Open your RSS reader.
2. Click **Add Feed** / **Subscribe**.
3. Paste either of the URLs:
   - JCR: `https://qinhuanyu.github.io/marketing-journal-rss/jcr.xml`
   - JAMS: `https://qinhuanyu.github.io/marketing-journal-rss/jams.xml`

### In Zotero
1. In Zotero, click **File** → **New Library** → **New Feed** → **From URL**.
2. Paste the RSS URL and set your update preferences.
3. Newly accepted marketing research papers will automatically appear in your Zotero feed.

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
│   └── generate_feeds.py      # Core feed generator script
├── docs/
│   ├── index.html             # Web dashboard
│   ├── jcr.xml                # JCR RSS Feed
│   └── jams.xml               # JAMS RSS Feed
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
