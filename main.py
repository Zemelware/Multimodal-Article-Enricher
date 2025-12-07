"""
1. Take an article and convert to JSON
2. Generate image slots JSON
3. Search for 1 image per query using the queries in image slots and convert to image slots with URLs
4. Use inject_images_into_html to insert image slots back into HTML
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from src.article_processor import html_to_article_view, inject_images_into_html
# Import local modules
from src.image_searcher import search_images
from src.image_suggester import generate_image_slots


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

    # Step 4: Search for images and build final slots
    print("\n4. Searching for images...")
    suggested_slots = slots_data.get("slots", [])
    if not suggested_slots:
        print("No slots suggested.")
        return

    final_slots = build_image_slots_from_specs(suggested_slots)
    
    # Step 5: Inject images
    print("\n5. Injecting images into HTML...")
    enhanced_html = inject_images_into_html(mutated_html, final_slots)
    
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
