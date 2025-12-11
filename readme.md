# Grokipedia Image and Widget Enhancement Workflow

This README outlines the end-to-end workflow for scraping Grokipedia articles, suggesting and generating both image placements and custom widget components (e.g., timelines, fact panels) via Grok API, searching for images, validating widget suitability, and inserting everything into HTML for an enhanced, interactive article. 

The process focuses on preserving original styling (inlined CSS) and using structured IDs for precise placements. The workflow is now fully implemented and chained via main.py for end-to-end processing.

## Prerequisites
- Python 3.11+ : \`pip install -r requirements.txt\` (includes beautifulsoup4, openai, httpx, requests, python-dotenv, etc.).
- API Keys:
  - \`export XAI_API_KEY=sk-...\` (from console.x.ai for Grok).
  - \`export GOOGLE_CUSTOM_SEARCH_KEY=your_key\` (Google Custom Search API for image search; get from console.cloud.google.com. Optionally update hardcoded CX_ID in src/image_searcher.py).
- \`.env\` file for keys (loaded automatically where needed).

## Quick Start (Minimum Workflow)

Use `main.py` for the full automated pipeline on scraped HTML:

- **Prep**: `pip install -r requirements.txt` and set API keys in `.env`.
- **Scrape** (if needed): Create `urls.txt` (one URL per line, e.g., https://grokipedia.com/page/Elon_Musk), run `python html_scraper.py --input-file urls.txt` → creates `data/pages/*.html` (default).
- **Enhance**: `python main.py data/pages/article.html` → generates `data/output/{article_name}.html` with:
  - Images: Grok-suggested slots, searched via Google Custom Search, best selected via Grok vision analysis, inserted as <figure> with captions.
  - Widgets: Grok-suggested slots (e.g., timeline, key_facts), suitability validated per section via Grok, generated as self-contained HTML/CSS components, inserted as <div class="widget-slot">.
  All positioned precisely using injected IDs.
- **View**: `open data/enhanced/article_enhanced.html` or serve locally.

**Notes**: 
- Requires XAI_API_KEY (Grok) and GOOGLE_CUSTOM_SEARCH_KEY (images).
- Images use top search result; customize `main.py` for better selection.
- Preserves original styles; inserts <img> with alt/caption; supports recommended_dimensions for sizes (future: add width/height attrs).


**Demo here**:
- https://www.youtube.com/watch?v=U1GzlYcGK3I
