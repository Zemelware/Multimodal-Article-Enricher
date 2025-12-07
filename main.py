"""
Workflow for enhancing Grokipedia articles with images and custom widgets:

1. Read HTML article file
2. Convert to structured Article View JSON and inject IDs into HTML (mutated_html)
3. Generate image slot suggestions using Grok API
4. For each image spec: search external images, use Grok vision to select best, build image slots
5. Generate widget slot suggestions using Grok API (e.g., timelines, fact panels)
6. For each widget spec: extract section context, use Grok to validate suitability and generate self-contained HTML component
7. Inject both image figures and widget divs into mutated HTML at suggested positions
8. Save enhanced HTML file

Requires XAI_API_KEY for Grok API calls (image selection, slot suggestions, widget generation).
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from src.article_processor import html_to_article_view, inject_slots_into_html
# Import local modules
from src.image_searcher import search_images
from src.image_suggester import generate_image_slots
from src.widget_suggester import generate_widget_slots
from src.widget_components import render_widget, WIDGET_TYPES


def select_best_image_with_grok(candidates, query, api_key=None, model="grok-4-1-fast-non-reasoning"):
    """
    Use Grok to analyze candidate images and select the best one.
    
    Args:
        candidates: List of image dicts with 'url', 'title', etc.
        query: The search query/context for what we're looking for
        api_key: Optional XAI API key
        model: Grok model to use
    
    Returns:
        Tuple of (index, caption) where index is the best candidate (0-based) and caption is a short description
    """
    if not candidates:
        return 0, ""
    
    api_key = api_key or os.getenv("XAI_API_KEY")
    if not api_key:
        print("    Warning: No API key, using first candidate")
        return 0, candidates[0].get("title", "")
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
        timeout=httpx.Timeout(120.0),
    )
    
    # Build message with all candidate images
    # Unused code block removed for cleanliness. The actual logic is in the retry loop below.
    # (Original code built 'content' here but it was never used in API call)
    
    # Keep track of which candidates we've tried
    excluded_indices = set()
    max_retries = len(candidates)
    
    for attempt in range(max_retries):
        # Build content with only non-excluded candidates
        available_candidates = [(i, c) for i, c in enumerate(candidates) if i not in excluded_indices]
        
        if not available_candidates:
            print(f"    All candidates failed to fetch. Skipping this image slot.")
            return None, None
        
        # Rebuild content for this attempt
        attempt_content = [
            {
                "type": "text",
                "text": f"""You are analyzing {len(available_candidates)} candidate images for the following context:

Search Query: "{query}"

Please carefully analyze each candidate image using your vision capabilities along with the provided metadata (title, dimensions). Select the SINGLE BEST image for the search query "{query}" by evaluating these criteria in order:

- RELEVANCE: Directly represents the query concept accurately and informatively
- AUTHENTICITY: Real or professionally created; AVOID AI-generated images identifiable by watermarks (Midjourney, DALL-E, etc.), artifacts (anatomical errors, unnatural elements), or stock model poses
- ORIENTATION: Prefer landscape (width > height); strongly deprioritize portrait (height > width) unless uniquely suitable
- QUALITY: High resolution, sharp focus, good lighting; reject blurry, low-res, or distorted
- CLEANLINESS: Free of watermarks, text overlays, logos, ads, or extraneous elements
- APPROPRIATENESS: Suitable for educational article - professional, non-offensive, contextually fitting
- COMPOSITION: Well-balanced, engaging, enhances article readability

Even if options are limited, choose the highest-scoring image overall.

The images are numbered 0 to {len(available_candidates)-1} in the order they appear below.

IMPORTANT: Respond with ONLY valid JSON matching this exact schema. No other text. Ensure:
- selected_index is an integer between 0 and {len(available_candidates)-1} inclusive
- caption is a concise (under 100 words), descriptive caption suitable for article use and SEO/alt text

{{
  "selected_index": 0,
  "caption": "Description of the selected image content, highlighting key visual elements relevant to the query."
}}"""
            }
        ]
        
        # Add each available candidate image
        for idx, (original_idx, candidate) in enumerate(available_candidates):
            attempt_content.append({
                "type": "text",
                "text": f"\nImage {idx}: '{candidate.get('title', 'Untitled')}' | Dimensions: {candidate.get('width', '?')}x{candidate.get('height', '?')}px | MIME: {candidate.get('mime_type', '?')} | Source: {candidate.get('source_page', 'N/A')[:60]}..."
            })
            attempt_content.append({
                "type": "image_url",
                "image_url": {
                    "url": candidate["url"],
                    "detail": "high"
                }
            })
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert image analyst and curator for Grokipedia educational articles. Your task is to select the SINGLE MOST SUITABLE image from the candidates based on strict criteria.

CRITERIA FOR SELECTION (in order of priority):
1. RELEVANCE: Must directly illustrate the search query without misleading elements.
2. AUTHENTICITY: Prefer real photos or diagrams. AVOID AI-generated images - reject those with watermarks (e.g., Midjourney, DALL-E, Stable Diffusion logos/text), artifacts (unnatural hands, symmetry errors, blurry details), or generic 'model' appearances.
3. ORIENTATION: Strongly prefer landscape (width > height). Ignore or deprioritize portrait (height > width) images unless exceptionally relevant.
4. QUALITY: High resolution, sharp, clear. Avoid blurry, pixelated, low-res images.
5. CLEANLINESS: No visible watermarks, text overlays, logos, ads, or frames. Clean composition preferred.
6. APPROPRIATENESS: Suitable for professional, educational content - no violence, explicit content, or poor taste.
7. ENGAGEMENT: Well-composed, informative, visually appealing.

If multiple images score similarly, choose the one with the best overall balance. ALWAYS select exactly one image, even if imperfect.

Output ONLY a valid JSON object with no additional text:
{
  "selected_index": <integer 0 to n-1>,
  "caption": "<1-2 sentence concise, accurate description of the image content, suitable for article caption and alt text>"
}"""
                    },
                    {
                        "role": "user",
                        "content": attempt_content
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=3000,
                temperature=0.3,
            )
            
            raw_content = response.choices[0].message.content
            
            # Parse JSON manually
            result = json.loads(raw_content)
            
            selected_index = result["selected_index"]
            caption = result["caption"]
            
            # Map back to original candidate index
            original_selected_index = available_candidates[selected_index][0]
            
            print(f"    Grok selected image {original_selected_index}: {caption}\n")
            return original_selected_index, caption
                
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a retryable image fetch error
            retryable_errors = [
                "Unrecoverable data loss or corruption",
                "Unsupported content-type",
                "Fetching image failed",
                "Fetching images over plain http://",
                "Error code: 412",
                "Error code: 403",
                "Error code: 404"
            ]
            
            if any(err in error_msg for err in retryable_errors):
                print(f"    Error fetching image: {error_msg}")
                
                # Try to identify which image failed by checking all current candidates
                # Since we don't know which one failed, exclude the last one tried
                # This is a heuristic - we'll exclude candidates one by one until we find working ones
                if available_candidates:
                    failed_idx = available_candidates[-1][0]
                    failed_url = candidates[failed_idx]["url"]
                    excluded_indices.add(failed_idx)
                    print(f"    Failed image URL: {failed_url}")
                    print(f"    Excluding image {failed_idx} and retrying with remaining candidates...")
                    continue
            
            # For other errors, fail immediately
            print(f"    Error calling Grok API: {error_msg}")
            return None, None
    
    # If we've exhausted all retries
    print(f"    All candidates failed. Skipping this image slot.")
    return None, None


def build_image_slots_from_specs(slot_specs):
    image_slots = []

    print(f"Processing {len(slot_specs)} image slots...")
    for spec in slot_specs:
        query = spec["search_query"]
        print(f"  Searching for: {query}")
        try:
            candidates = search_images(query, num_results=7)  # Google/Bing/Wikimedia/etc.
        except Exception as e:
            print(f"    Error searching for '{query}': {e}")
            continue

        if not candidates:
            print(f"    No images found for '{query}'")
            continue

        # Use Grok to select the best image from candidates
        print(f"    Selecting best image with Grok...")
        best_index, caption = select_best_image_with_grok(candidates, query)
        
        # Skip this slot if no valid image was found
        if best_index is None or caption is None:
            print(f"    Skipping slot - no valid image available")
            continue
        
        top = candidates[best_index]

        alt_text = spec.get("alt_text_hint") or top.get("title") or ""

        image_slots.append({
            "section_id": spec["section_id"],
            "paragraph_id": spec.get("paragraph_id"),
            "position": spec.get("position", "after"),
            "image_url": top["url"],
            "alt_text": alt_text,
            "caption": caption,
        })

    return image_slots


def assess_and_extract_data(context_text, content_hint, widget_type, api_key=None, model="grok-4-1-fast-non-reasoning"):
    """
    Use Grok to assess suitability of widget type for context and extract structured data if suitable.
    Returns tuple: (score, reason, extracted_data)
    - score: float 0.0-1.0 suitability score
    - reason: str explanation
    - extracted_data: data structure matching widget schema or None if unsuitable/insufficient
    Render with render_widget(widget_type, extracted_data) if data not None.
    On error, returns (0.0, error_msg, None)
    """
    api_key = api_key or os.getenv("XAI_API_KEY")
    if not api_key:
        print("    No XAI_API_KEY, skipping widget generation")
        return 0.0, "No API key provided", None

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
        timeout=httpx.Timeout(120.0),
    )

    # Get schema hint for this type
    schema_hint = WIDGET_TYPES.get(widget_type, {}).get("data_schema", "JSON object with relevant structured data (e.g., list of items, events, or rows).")

    # Example data for prompt based on widget type
    if widget_type == "timeline":
        example_data = '[ {{"date": "1971", "title": "Birth", "description": "Born in Pretoria, South Africa."}}, {{"date": "1989", "title": "Move to Canada", "description": "Emigrated at age 17."}}, {{"date": "2002", "title": "SpaceX Founded", "description": "Established SpaceX with $100M from PayPal sale."}} ]'
    elif widget_type == "key_facts":
        example_data = '[ "Born June 28, 1971, in Pretoria, South Africa.", "Co-founder of PayPal, sold for $1.5B in 2002.", "CEO and product architect of Tesla since 2008.", "Founder and CEO of SpaceX since 2002.", "Net worth estimated at $250B+ as of 2024.", "South African, Canadian, and US citizen." ]'
    elif widget_type == "key_locations":
        example_data = '[ {{"name": "Pretoria, South Africa", "lat": -25.7461, "lng": 28.1881, "description": "Birthplace and early childhood home."}}, {{"name": "Toronto, Canada", "lat": 43.6532, "lng": -79.3832, "description": "Lived after moving from South Africa in 1989."}}, {{"name": "Hawthorne, California, USA", "lat": 33.9162, "lng": -118.3361, "description": "SpaceX headquarters location."}} ]'
    else:
        example_data = 'null  # No example for unknown type'

    system_prompt = f"""You are an expert content analyst extracting structured data for custom widget components in educational articles.

TASK:
1. Assess suitability of '{widget_type}' widget for the context_text and content_hint.
   - Criteria: Does content have fitting elements? (timeline: chronology/events; key_facts: stats/highlights; comparison_table: comparable items; quote_block: quotes; etc.)
   - Score 0.0-1.0: High if data-rich for type and adds unique value; low if mismatched or redundant.
2. If score >= 0.5, extract 'extracted_data' as structured JSON matching this schema: {schema_hint}
   - Derive from context_text and content_hint: Be accurate, concise, relevant. Limit items (4-10).
   - Examples:
     - Timeline: Extract chronological events with date/title/desc.
     - Key facts: 5-10 short bullet facts.
     - Use context to infer/complete data logically.
   - If insufficient data, score lower or set extracted_data to []/null.

Output ONLY valid JSON, no other text:
{{
  "suitable_score": 0.85,
  "reason": "1-2 sentence explanation of score and fit.",
  "extracted_data": {example_data}  # Example; replace with actual extracted data matching schema {schema_hint} or null if unsuitable
}}
Ensure extracted_data is valid JSON-parseable and directly usable for rendering. Always provide structured data if score >=0.7, even if approximate."""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": f"""Context text from article section/paragraph:
{context_text}

Content hint: {content_hint}

1. Score suitability for '{widget_type}' widget.
2. If suitable (>=0.7), extract structured data as specified."""
        }
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.2,  # Lower for structured extraction
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean markdown code blocks
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            parts = content.split("```")
            content = parts[1].strip() if len(parts) > 1 and "json" in parts[0] else content
        
        result = json.loads(content)
        
        score = result.get("suitable_score", 0.0)
        reason = result.get("reason", "")
        extracted_data = result.get("extracted_data")
        
        if not isinstance(score, (int, float)):
            score = 0.0
            reason = "Invalid score format."
            extracted_data = None
        
        print(f"    Suitability for {widget_type}: score {score} - {reason[:80]}...")
        print(f"    Data extracted: { 'Yes ({len(extracted_data)} items)' if extracted_data else 'No' }")
        
        return score, reason, extracted_data
            
    except json.JSONDecodeError as je:
        print(f"    JSON parse error: {str(je)[:100]}")
        return 0.0, f"JSON parse error: {str(je)}", None
    except Exception as e:
        print(f"    Grok API error: {str(e)[:100]}")
        return 0.0, f"Grok API error: {str(e)}", None


def build_widget_slots_from_specs(widget_specs, article_view, api_key=None, model="grok-4-1-fast-non-reasoning"):
    """
    Process widget specs: extract context, assess suitability with Grok, generate HTML if suitable.
    """
    widget_slots = []
    candidates = []
    
    print(f"Processing {len(widget_specs)} widget specs...")
    for spec in widget_specs:
        section_id = spec["section_id"]
        paragraph_id = spec.get("paragraph_id")
        position = spec.get("position", "after")
        widget_type = spec["widget_type"]
        content_hint = spec["content_hint"]
        
        print(f"  Building {widget_type} for section {section_id} {f'(para {paragraph_id})' if paragraph_id else '(after heading)'}...")
        
        # Extract context text
        section = next((s for s in article_view["sections"] if s["id"] == section_id), None)
        if not section:
            print(f"    Section {section_id} not found, skipping.")
            continue
        
        context_parts = [section["heading"]]
        if paragraph_id:
            para_dict = next((p for p in section["paragraphs"] if p["id"] == paragraph_id), None)
            if para_dict:
                context_parts.append(para_dict["text"])
            else:
                context_parts.extend(p["text"] for p in section["paragraphs"])
                print(f"    Paragraph {paragraph_id} not found, using full section.")
        else:
            context_parts.extend(p["text"] for p in section["paragraphs"])
        
        context_text = "\n".join(context_parts)
        if len(context_text) > 4000:
            context_text = context_text[:4000] + "\n... (truncated for API)"
        
        # Assess and extract data
        score, reason, extracted_data = assess_and_extract_data(context_text, content_hint, widget_type, api_key, model)
        
        print(f"    Suitability score: {score:.2f} - {reason[:60]}...")
        
        candidate = None
        if extracted_data is not None:
            html = render_widget(widget_type, extracted_data)
            if html:
                if score >= 0.5:
                    widget_slots.append({
                        "type": "widget",
                        "section_id": section_id,
                        "paragraph_id": paragraph_id,
                        "position": position,
                        "widget_type": widget_type,
                        "widget_html": html,
                    })
                    print(f"    ✓ Added {widget_type} widget (score >=0.5)")
                else:
                    candidate = {
                        "html": html,
                        "score": score,
                        "spec": spec,
                        "section_id": section_id,
                        "paragraph_id": paragraph_id,
                        "position": position,
                        "widget_type": widget_type,
                    }
                    print(f"    Candidate {widget_type} (low score {score:.2f})")
            else:
                print(f"    ✗ Render failed for {widget_type}")
        else:
            print(f"    ✗ No data extracted")
        
        if candidate:
            candidates.append(candidate)
    
    # Fallback logic to ensure at least one widget
    if not widget_slots and candidates:
        best = max(candidates, key=lambda c: c["score"])
        best_score = best["score"]
        if best_score >= 0.3:
            widget_slots.append({
                "type": "widget",
                "section_id": best["section_id"],
                "paragraph_id": best["paragraph_id"],
                "position": best["position"],
                "widget_type": best["widget_type"],
                "widget_html": best["html"],
            })
            print(f"    ✓ Fallback: Added best {best['widget_type']} (score {best_score:.2f}) to ensure at least one widget per page.")
        else:
            print(f"    No fallback: best score {best_score:.2f} too low")
    
    print(f"Generated {len(widget_slots)} widget slots.")
    return widget_slots

def main(html_file_path):
    load_dotenv()
    
    # Step 1: Read HTML
    print(f"\n1. Reading article from {html_file_path}...")
    try:
        html_content = Path(html_file_path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Step 2: Convert to Article View JSON
    print("\n2. Converting to Article View JSON...")
    mutated_html, article_view = html_to_article_view(html_content)

    # Step 3: Generate image slots
    print("\n3. Generating image slot suggestions with Grok...")
    
    # Check for API key
    if not os.getenv("XAI_API_KEY"):
        print("Warning: XAI_API_KEY not found. Skipping Grok generation.")
        print("Please set XAI_API_KEY in .env file.")
        return

    # Generate image slots using article_view in memory
    try:
        slots_data = generate_image_slots(
            article=article_view,
            output_path=None  # Avoid writing intermediate file
        )
    except Exception as e:
        print(f"Error generating slots: {e}")
        return

    # Generate widget slot suggestions using article_view in memory
    print("\n3.5 Generating widget slot suggestions with Grok...")
    try:
        widget_data = generate_widget_slots(
            article=article_view,
            output_path=None,  # Avoid writing intermediate file
            max_slots=5
        )
        widget_specs = widget_data.get("slots", [])
    except Exception as e:
        print(f"Error generating widget specs: {e}")
        widget_specs = []
        widget_data = {"slots": []}

    # Step 4: Search for images and build final slots
    print("\n4. Building image slots...")
    suggested_slots = slots_data.get("slots", [])
    final_slots = build_image_slots_from_specs(suggested_slots)
    if not final_slots:
        print("No image slots generated.")

    print("\n4.5 Building widget slots...")
    widget_final_slots = build_widget_slots_from_specs(widget_specs, article_view)
    if not widget_final_slots:
        print("No widget slots generated.")

    if not final_slots and not widget_final_slots:
        print("No slots to inject. Saving mutated HTML as-is.")
        enhanced_html = mutated_html
        # Optionally return here, but proceed to save
    else:
        print("\n5. Injecting images and widgets into HTML...")
        all_slots = final_slots + widget_final_slots
        print(f"  Total slots: {len(final_slots)} images + {len(widget_final_slots)} widgets")
        enhanced_html = inject_slots_into_html(mutated_html, all_slots)
    
    # Step 5: Inject slots (images and widgets)
    print("\n5. Injecting images and widgets into HTML...")
    all_slots = final_slots + widget_final_slots
    print(f"  Total slots: {len(final_slots)} images + {len(widget_final_slots)} widgets")
    enhanced_html = inject_slots_into_html(mutated_html, all_slots)
    
    # Create output directory and save final file
    output_dir = Path("data/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    input_stem = Path(html_file_path).stem
    output_html_path = output_dir / f"{input_stem}_enhanced.html"
    output_html_path.write_text(enhanced_html, encoding="utf-8")
    
    print(f"\nDone! Enhanced article saved to {output_html_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        print("Usage: python main.py <path_to_html_file>")
        print("Example: python main.py data/pages/Acquisition_of_Twitter_by_Elon_Musk.html")
        sys.exit(1)
