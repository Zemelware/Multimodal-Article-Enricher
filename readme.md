# Grokipedia Image Enhancement Workflow

This README outlines the end-to-end workflow for scraping Grokipedia articles, suggesting image placements via Grok API, searching for images, and inserting them into HTML for a visually enhanced article. 

The process focuses on preserving original styling (inlined CSS) and using structured IDs for precise placements. Some steps are implemented; others are TODOs marked with checkboxes.

## Prerequisites
- Python 3.11+ with deps: \`pip install requests beautifulsoup4 openai httpx python-dotenv google-api-python-client\` (or per-file: see below).
- API Keys:
  - \`export XAI_API_KEY=sk-...\` (from console.x.ai for Grok).
  - \`export GOOGLE_CUSTOM_SEARCH_KEY=your_key\` (for image search via image_search.py).
- \`.env\` file for keys (loaded automatically where needed).

## Workflow Steps

### 1. [x] Scrape HTML Articles with Persistent Styling
Use \`html_scraper.py\` to fetch full HTML from Grokipedia URLs, inline CSS (Tailwind/styles) for self-contained files.

- **Input**: \`urls.txt\` (one URL per line, e.g., https://grokipedia.com/page/Acquisition_of_Twitter_by_Elon_Musk) or CLI args.
- **Command**:
  \`\`\`
  python html_scraper.py --input-file urls.txt
  # Or single/multiple: python html_scraper.py "https://grokipedia.com/page/Elon_Musk"
  \`\`\`
- **Output**: \`pages/*.html\` (e.g., \`pages/Acquisition_of_Twitter_by_Elon_Musk.html\`).
- **Notes**: Parallel fetching, error handling. Requires \`requests\`, \`beautifulsoup4\` for inlining.
- **Alternative**: \`grokipedia_crawler.py\` for raw text extraction (CLI: \`python grokipedia_crawler.py <url>\`), but use scraper for styled HTML.

### 2. [ ] TODO: Encode HTML to Structured JSON (article_view.json)
Parse scraped HTML into JSON format: \`{"title": str, "sections": [{"id": str, "level": int, "heading": str, "paragraphs": [{"id": str, "text": str}]}]}\`.

- Embed matching IDs into HTML too (for later backfilling).
- **Status**: Not implemented. Revive/create \`html_to_json.py\` using BeautifulSoup to extract title, headings (H1-H6 as sections with slug IDs), paragraphs. Similar to old parser in \`grok_image_suggester.py\`.
- **Command**: (TBD) \`python html_to_json.py --html pages/article.html --output article_view.json\`
- **Output**: \`article_view.json\` + updated HTML with IDs (e.g., \`<section id="sec-acquisition">\` or data-ids on elements).
- **Deps**: \`beautifulsoup4\`.
- **Next**: Implement to generate IDs consistently for slots matching.

### 3. [x] Generate Image Slots JSON via Grok API
Feed structured JSON to \`grok_image_suggester.py\` (callable function) for Grok to suggest slots.

- **Input**: \`article_view.json\` from step 2.
- **Command/Example**:
  \`\`\`
  # Via python -c (no CLI; function-based)
  python -c "from grok_image_suggester import generate_image_slots; generate_image_slots('article_view.json', output_path='image_slots.json')"
  
  # Or in script/import:
  from grok_image_suggester import generate_image_slots
  slots = generate_image_slots("article_view.json", api_key=os.getenv("XAI_API_KEY"))
  \`\`\`
- **Output**: \`image_slots.json\` \`{"slots": [{"section_id": "sec_1", "paragraph_id": "p_2"|"null", "position": "after", "image_type": "...", "search_query": "...", "alt_text_hint": "...", "caption_hint": "...", "priority": 0.9}, ...]}\`.
- **Notes**: Max 10 slots default; requires XAI_API_KEY. Removed HTML support; JSON-only now.
- **Deps**: \`openai\`, \`httpx\`, \`python-dotenv\`.

### 4. [ ] TODO: Search Images for Slots (Using image_search.py)
Use \`image_search.py\` to resolve each slot's \`search_query\` to actual image URLs via Google Custom Search API.

- **Status**: Module implemented but integration needed for batch processing.
- **Manual Command/Example**:
  \`\`\`
  python image_search.py "elon musk acquisition twitter"  # Returns list of image dicts with URLs
  \`\`\`
- **Integration**: In backfill step or separate script: Load \`image_slots.json\`, for each slot call \`search_images(query)\`, select/filter best URL (e.g., relevant, high-res, licensed), add to slots (output \`slots_with_images.json\` with "image_url": "...").
- **Output**: Augmented slots JSON with resolved image URLs.
- **Deps**: \`requests\`; set \`GOOGLE_CUSTOM_SEARCH_KEY\` env var, update CX_ID in file if needed.
- **Notes**: API has quotas/costs; handle errors/fallbacks (e.g., default images).

### 5. [ ] TODO: Backfill JSON Slots into HTML (Insert Images via image_search Results)
Combine slots.json + image search results to insert images into HTML at suggested positions using IDs.

- **Key**: Use \`image_search.py\` (from step 4) to get URLs for queries, then backfill: Embed images at slot positions in HTML.
- **Status**: Partial support via \`grok_image_placer.py\` for single images (Grok vision decides spot, but we can adapt for ID-based multi-insert).
  - Single Command: \`python grok_image_placer.py --html-file pages/article.html --image-url "https://example.com/img.jpg" --output updated.html\`
- **Approach**:
  1. Load slots + images.
  2. Parse HTML (BeautifulSoup).
  3. For each slot: Find element by \`section_id\`/\`paragraph_id\`, insert \`<img src="\${image_url}" alt="\${alt_hint}" title="\${caption_hint}" />\` at \`position\` (e.g., after paragraph).
  4. Prioritize high-score slots; optional: Use placer's vision for fine-tuning if IDs mismatch.
- **Command**: (TBD, new/modified script) \`python backfill_images.py --html pages/article.html --slots image_slots.json --output updated.html\`
  - Internally calls image_search.py for any unresolved queries.
- **Output**: \`updated.html\` with images inserted, IDs preserved, styling intact.
- **Deps**: \`beautifulsoup4\`, \`openai/httpx\` (for optional vision), integrates \`image_search.py\`.
- **Next**: Implement \`backfill_images.py\` (or extend placer) for loop: search -> insert by ID. Handle multiple images per slot, validation.

### 6. [x] Display Final Result to User
- Open \`updated.html\` in browser (self-contained with styles/images).
- **Command**: \`open updated.html\` (macOS) or serve: \`python -m http.server 8000\` then visit localhost:8000/updated.html.
- **Notes**: Images loaded via URLs; ensure public/HTTPS for embedding.

## Full Pipeline (Future)
- Chain steps in \`workflow.py\`: scrape -> encode -> suggest -> search -> backfill -> display.
- Batch for multiple articles from \`urls.txt\`.
- Error handling, parallelism, caching (e.g., skip if files exist).

## Existing Tools & Status
- [x] \`html_scraper.py\`: HTML fetch/inline.
- [ ] \`html_to_json.py\`: Structure extractor (implement).
- [x] \`grok_image_suggester.py\`: Slots generator (function; JSON-only).
- [x] \`image_search.py\`: Query-to-URLs (integrate).
- [x] \`grok_image_placer.py\`: Single image placer (adapt for multi).
- [ ] Backfill script.
- Support: \`grokipedia_crawler.py\` (text extract), \`urls.txt\` (input).

## Troubleshooting
- API Errors: Check keys, quotas (Grok/Google).
- Missing Deps: Install per step (e.g., \`pip install beautifulsoup4\` for parsing).
- IDs Mismatch: Ensure step 2 embeds consistent IDs in HTML/JSON.
- Run in venv: \`python -m venv venv; source venv/bin/activate; pip install ...\`

## Future Enhancements
- Automate JSON encoder.
- Vision-based placement fallback (extend placer).
- Image validation/resizing.
- GitHub Actions for CI/CD.

See file docs for details. Contribute by implementing TODOs!
