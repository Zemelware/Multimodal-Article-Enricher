# Grokipedia Image Enhancement Workflow

This README outlines the end-to-end workflow for scraping Grokipedia articles, suggesting image placements via Grok API, searching for images, and inserting them into HTML for a visually enhanced article. 

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
- **Enhance**: `python main.py data/pages/article.html` → generates `data/enhanced/article_enhanced.html` with images suggested by Grok, searched via Google, and inserted using IDs.
- **View**: `open data/enhanced/article_enhanced.html` or serve locally.

**Notes**: 
- Requires XAI_API_KEY (Grok) and GOOGLE_CUSTOM_SEARCH_KEY (images).
- Images use top search result; customize `main.py` for better selection.
- Preserves original styles; inserts <img> with alt/caption; supports recommended_dimensions for sizes (future: add width/height attrs).

## Detailed Workflow Steps

### 1. [x] Scrape HTML Articles with Persistent Styling
Use \`html_scraper.py\` (root) to fetch full HTML from Grokipedia URLs, inline CSS (Tailwind/styles) for self-contained files.

- **Input**: \`urls.txt\` (root, one URL per line, e.g., https://grokipedia.com/page/Acquisition_of_Twitter_by_Elon_Musk) or CLI args for single/multiple URLs.
- **Command**:
  \`\`\`
  python html_scraper.py --input-file urls.txt
  # Or single/multiple: python html_scraper.py "https://grokipedia.com/page/Elon_Musk" "https://grokipedia.com/page/another"
  \`\`\`
- **Output**: \`data/pages/*.html\` (default dir; e.g., Acquisition_of_Twitter_by_Elon_Musk.html; override with --output-dir).
- **Notes**: Parallel fetching, error handling. Requires \`requests\`, \`beautifulsoup4\` for inlining.
- **Alternative**: \`src/grokipedia_crawler.py\` for raw text extraction (CLI: \`python src/grokipedia_crawler.py <url>\`), but use scraper for styled HTML.

### 2. [x] Encode HTML to Structured JSON (article_view.json)
Parse scraped HTML into JSON format: \`{"title": str, "sections": [{"id": str, "level": int, "heading": str, "paragraphs": [{"id": str, "text": str}]}]}\`.

- Also injects matching IDs into a mutated HTML string for later image insertion.
- **Status**: Implemented in \`src/article_processor.py\` as \`html_to_article_view(html: str) -> tuple[str, dict]\` using BeautifulSoup.
  - Extracts title, sections (headings H2-H6), paragraphs (p/span blocks).
  - Generates IDs: sec_1, p_1 etc. or uses existing.
  - Returns mutated_html (with IDs added) and article_view dict.
- **Usage** (function, no CLI):
  \`\`\`
  from src.article_processor import html_to_article_view
  mutated_html, article_view = html_to_article_view(html_content)
  # Save if needed: Path("data/article_view.json").write_text(json.dumps(article_view, indent=2))
  \`\`\`
- **Output**: In-memory dict and mutated HTML; save to \`data/article_view.json\` manually or via main.py.
- **Deps**: \`beautifulsoup4\`.

### 3. [x] Generate Image Slots JSON via Grok API
Feed structured JSON to \`src/image_suggester.py\` (importable function) for Grok to suggest optimal image placements, now including recommended dimensions.

- **Input**: \`article_view.json\` from step 2.
- **Command/Example**:
  \`\`\`
  # Via python -c (no CLI; function-based)
  python -c "from src.image_suggester import generate_image_slots; generate_image_slots('article_view.json', output_path='image_slots.json')"
  
  # Or in script/import:
  from src.image_suggester import generate_image_slots
  slots = generate_image_slots("article_view.json", api_key=os.getenv("XAI_API_KEY"))
  \`\`\`
- **Output**: \`image_slots.json\` with \`{"slots": [ {"section_id": str, "paragraph_id": str|null, "position": str, "image_type": str, "search_query": str, "alt_text_hint": str, "caption_hint": str, "priority": float, "recommended_dimensions": {"width": int, "height": int} }, ... ]}\`.
- **Notes**: Max 10 slots default; requires XAI_API_KEY. Removed HTML support; JSON-only now.
- **Deps**: \`openai\`, \`httpx\`, \`python-dotenv\`.

### 4. [x] Search Images for Slots (src/image_searcher.py)
Use Google Custom Search API to find image URLs matching slot \`search_query\`. Returns list of candidates; main.py takes the top result and adds "image_url", alt/caption to slots.

- **Status**: Fully implemented module with CLI and integrated in main.py for automatic batch processing per suggested slots.
- **Manual CLI**:
  \`\`\`
  python src/image_searcher.py  # Interactive: enter query, gets 10 results
  # Or in code:
  from src.image_searcher import search_images
  results = search_images("elon musk", num_results=5)
  \`\`\`
- **Output**: List[Dict] with "url", "title", etc. per image.
- **Deps**: requests (in requirements.txt); GOOGLE_CUSTOM_SEARCH_KEY env var required.
- **Notes**: Uses hardcoded CX_ID (update in file for your search engine). Quotas apply; top result used in pipeline for simplicity.

### 5. [x] Backfill Slots into HTML (Insert Images)
Integrate image search results into mutated HTML from step 2, inserting <img> tags at suggested positions using section/paragraph IDs. Implemented in src/article_processor.py as `inject_images_into_html(mutated_html, final_slots)` and called by main.py.

- **Key**: Loads final slots (with image_url from step 4), parses HTML, locates elements by IDs, inserts <figure><img src="{image_url}" alt="{alt_text}" style="max-width:100%; height:auto;" /><figcaption>{caption}</figcaption></figure> after/before as per position. Preserves layout.
- **Status**: Fully implemented and integrated in main.py (batch inserts high-priority slots).
- **Usage** (in code/main.py):
  \`\`\`
  from src.article_processor import inject_images_into_html
  enhanced_html = inject_images_into_html(mutated_html, final_slots)
  # Save enhanced_html to file
  \`\`\`
- **Output**: Enhanced HTML string/file with embedded images, ready for display.
- **Deps**: beautifulsoup4.
- **Notes**: Currently uses top image search result; sorts by priority descending. Future: Use recommended_dimensions for width/height attrs on <img>; add CSS classes for Tailwind styling; filter low-quality images.

### 6. [x] Display Final Result
- Open enhanced HTML from main.py output: \`data/enhanced/*.html\` in browser (self-contained with inlined styles and embedded images).
- **Command**: \`open data/enhanced/article_enhanced.html\` (macOS) or serve: \`python -m http.server 8000 -d data/enhanced\` then visit localhost:8000/article_enhanced.html.
- **Notes**: Images load from external URLs (Google-sourced); use HTTPS/public sources for security. Responsive design preserved; images sized responsively (future: fixed dimensions from suggestions).

## Full Pipeline
- Implemented in \`main.py\`: HTML input -> structure/IDs -> Grok suggestions -> image search -> insertion -> enhanced HTML output.
- For batch: Use html_scraper.py on urls.txt to get multiple pages/*.html, then run main.py on each (or extend main.py for loop).
- Features: Error handling for API calls, in-memory processing, preserves styling/IDs.

## Tools & Modules
All implemented:

- \`html_scraper.py\`: Scrapes Grokipedia URLs to self-contained HTML (inlines CSS/Tailwind).
- \`src/article_processor.py\`: Parses HTML to structured JSON (article_view) with ID injection; injects images back (inject_images_into_html).
- \`src/image_suggester.py\`: Uses Grok API to suggest image slots with positions, types, queries, hints, priority, and recommended dimensions.
- \`src/image_searcher.py\`: Searches Google Custom Search for images matching queries (CLI or function).
- \`src/grokipedia_crawler.py\`: Simple text extraction from URLs (alternative to full scrape).
- \`main.py\`: End-to-end pipeline: input HTML → enhanced HTML with images.
- Input: urls.txt (for scraper batch); Output dirs: pages/, data/enhanced/.

## Troubleshooting
- Missing API keys: Set XAI_API_KEY (.env) for Grok suggestions; GOOGLE_CUSTOM_SEARCH_KEY for images (main.py logs skips/errors).
- Deps: `pip install -r requirements.txt`; venv recommended: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`.
- No output files: Check scraper creates pages/; main.py needs valid HTML input.
- IDs/Insertion issues: Verify article_processor handles structure; debug with print statements.
- Quotas/Costs: Google Custom Search and xAI API have limits; monitor usage.

## Next Steps / Enhancements
- Enhance insertion: Use slot "recommended_dimensions" for <img width/height attrs to prevent layout shift.
- Better images: Filter/search multiple engines (Bing/Wikimedia); validate size/quality/license.
- Batch processing: Loop main.py over pages/ dir.
- Resizing: Server-side crop/resize images to suggested dims.
- Deployment: GitHub Actions for automation; host enhanced articles.

See individual file docstrings/comments for details. Contributions welcome!
