"""
Grok Image Suggester - Uses Grok API to analyze an article JSON structure and suggest optimal image placement slots.

Function:
def generate_image_slots(input_path: str, output_path: str = "image_slots.json", api_key: Optional[str] = None, model: str = "grok-beta", max_slots: int = 10) -> Dict[str, Any]

Loads JSON article (title + sections/paragraphs with IDs), queries Grok API for image slot suggestions, saves JSON to output_path, returns the data dict.

Example:
    from grok_image_suggester import generate_image_slots
    slots_data = generate_image_slots("article_view.json")
    # Automatically loads XAI_API_KEY from env or .env

Requires:
- XAI_API_KEY env var (export XAI_API_KEY=your_key from console.x.ai) or pass api_key=...
- Deps: openai, httpx, python-dotenv

Grok suggests slots with section/paragraph positions, image types, search queries, alt/caption hints, priority scores, and recommended dimensions for site-suited embedding.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI


def _format_article_for_grok(article: Dict[str, Any]) -> str:
    """
    Format article structure as text for Grok analysis.
    Includes section IDs, headings, and paragraph IDs for reference.
    """
    lines = [f"Title: {article.get('title', 'Article')}\n"]
    
    for section in article.get('sections', []):
        section_id = section.get('id', '')
        heading = section.get('heading', '')
        level = section.get('level', 2)
        
        lines.append(f"\n{'#' * level} {heading} [Section ID: {section_id}]")
        
        for para in section.get('paragraphs', []):
            para_id = para.get('id', '')
            text = para.get('text', '')
            # Truncate very long paragraphs for token efficiency
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(f"[Paragraph ID: {para_id}] {text}")
    
    return '\n'.join(lines)


def generate_image_slots(
    input_path: Optional[str] = None,
    article: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = "image_slots.json",
    api_key: Optional[str] = None,
    model: str = "grok-4-1-fast-non-reasoning",
    max_slots: int = 10
) -> Dict[str, Any]:
    """
    Generate image slot suggestions from article JSON using Grok API.
    
    Loads the JSON file, formats for Grok, gets suggestions, saves to output JSON, returns data.
    
    Args:
        input_path: Optional[str] = None - Path to article JSON file. Mutually exclusive with 'article'.
        article: Optional[Dict[str, Any]] = None - Article dict to use directly. Mutually exclusive with 'input_path'. Format: {"title": str, "sections": [{"id": str, "level": int, "heading": str, "paragraphs": [{"id": str, "text": str}]}]}
        output_path: Optional[str] = "image_slots.json" - Path to save slots JSON. If None, skips saving to file.
        api_key: Optional[str] = None - XAI API key; loads from env if None
        model: str = "grok-4-1-fast-non-reasoning" - Grok model name
        max_slots: int = 10 - Max slots to suggest (Grok may suggest fewer)
    
    Returns:
        Dict[str, Any] with "slots": List[Dict[str, Any]], where each slot dict contains:
        - section_id: str
        - paragraph_id: str or None
        - position: str (e.g., "after", "after_heading")
        - image_type: str (e.g., "photo", "diagram")
        - search_query: str
        - alt_text_hint: str
        - caption_hint: str
        - priority: float (0.0-1.0)
        - recommended_dimensions: Dict[str, int] = {"width": int, "height": int}
    
    Raises:
        ValueError: Invalid input JSON or API response
        FileNotFoundError: Input file missing
        RuntimeError: API errors with details
    """
    load_dotenv()
    api_key = api_key or os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError(
            "XAI_API_KEY not found. Set environment variable (export XAI_API_KEY=sk-...) "
            "or pass api_key parameter."
        )
    
    # Load or validate article data
    if input_path is not None and article is not None:
        raise ValueError("Provide only one of 'input_path' or 'article', not both.")
    
    if article is None:
        if input_path is None:
            raise ValueError("Must provide either 'input_path' or 'article' parameter")
        
        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        content = input_path_obj.read_text(encoding="utf-8")
        
        try:
            article = json.loads(content)
            # Validate basic structure
            if "title" not in article or "sections" not in article:
                raise ValueError("JSON missing required 'title' or 'sections' keys")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {input_path}: {e}")
        except ValueError as e:
            raise ValueError(f"Article validation failed: {e}")
    else:
        # Validate provided article dict
        if "title" not in article or "sections" not in article:
            raise ValueError("Provided 'article' missing required 'title' or 'sections' keys")
    
    article_text = _format_article_for_grok(article)
    
    # Truncate for API limits
    max_chars = 50000
    if len(article_text) > max_chars:
        article_text = article_text[:max_chars] + "\n\n[Article truncated for API call]"
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
        timeout=httpx.Timeout(120.0),
    )
    
    messages = [
        {
            "role": "system",
            "content": """You are an expert content strategist specializing in article layout and visual content placement.

Your task is to analyze an article and suggest optimal locations for images. For each suggested image slot, provide:
- The exact section_id and paragraph_id (or null for paragraph_id if placing after a heading)
- The position relative to the content (e.g., "after", "after_heading", "before")
- The type of image that would be most appropriate (e.g., "photo", "diagram", "infographic", "chart", "illustration")
- A search query that could be used to find a suitable image
- Alt text hint for accessibility
- A priority score (0.0 to 1.0) indicating how important/valuable this image placement would be
- Recommended image dimensions ({"width": integer, "height": integer} in pixels) that best suit the Grokipedia site layout and the suggested image's role in the article

CRITICAL: Return ONLY valid JSON in this exact format (no markdown, no extra text):

{
  "slots": [
    {
      "section_id": "sec_1",
      "paragraph_id": "p_2",
      "position": "after",
      "image_type": "photo",
      "search_query": "young elon musk childhood photo",
      "alt_text_hint": "Elon Musk as a child.",
      "priority": 0.9,
      "recommended_dimensions": {"width": 600, "height": 400}
    },
    {
      "section_id": "sec_3",
      "paragraph_id": null,
      "position": "after_heading",
      "image_type": "diagram",
      "search_query": "falcon 9 reusable rocket diagram",
      "alt_text_hint": "Diagram of a SpaceX Falcon 9 reusable rocket.",
      "priority": 0.8,
      "recommended_dimensions": {"width": 800, "height": 600}
    }
  ]
}

GUIDELINES:
- Suggest images that enhance understanding, break up long text, or illustrate key concepts
- Prioritize images for:
  * Key people mentioned (photos)
  * Important events or locations (photos)
  * Complex concepts that benefit from visual explanation (diagrams, charts)
  * Historical moments or significant milestones (photos)
- Use section_id and paragraph_id exactly as provided in the article structure
- Set paragraph_id to null if placing after a section heading
- Position values: "after" (after paragraph), "after_heading" (after section heading), "before" (before paragraph/heading)
- Image types: "photo", "diagram", "chart", "infographic", "illustration", "screenshot"
- Priority: 0.9-1.0 for critical images, 0.7-0.8 for important, 0.5-0.6 for nice-to-have, below 0.5 for optional
- Search queries should be specific and descriptive
- Alt text hints should be concise and descriptive
- Recommended dimensions: Provide {"width": px, "height": px} suitable for embedding in Grokipedia articles. The site features a modern, responsive layout with Tailwind CSS. Tailor sizes to:
  * Hero or lead images (e.g., after title or key sections): 1200x675 or similar wide aspect
  * Inline images within paragraphs: 600x400 to 800x600 for readability without overwhelming text
  * Diagrams, charts, infographics: 800x600 or square for clarity
  * Small thumbnails or icons: 300x300 or less
  Base on image_type and placement to ensure visual balance and fast loading."""
        },
        {
            "role": "user",
            "content": f"""Analyze this article and suggest optimal image placement slots.

Article Structure:
{article_text}

Provide {max_slots} or fewer image slot suggestions. Focus on the most valuable placements that would enhance the article's visual appeal and reader understanding.

Return ONLY the JSON object with the slots array, no additional text or markdown formatting."""
        },
    ]
    
    response_text = None
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        try:
            slots_data = json.loads(response_text)
        except json.JSONDecodeError:
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                parts = response_text.split("```")
                response_text = parts[1 if len(parts) > 1 else 0].strip()
            
            slots_data = json.loads(response_text)
        
        if "slots" not in slots_data:
            raise ValueError("Response missing 'slots' key")
        
        # Optional: Validate each slot has required fields
        required_fields = {"section_id", "position", "image_type", "search_query", "alt_text_hint", "caption_hint", "priority", "recommended_dimensions"}
        for i, slot in enumerate(slots_data["slots"]):
            missing = required_fields - set(slot.keys())
            if missing:
                raise ValueError(f"Slot {i} missing fields: {missing}")
        
        if output_path is not None:
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            output_path_obj.write_text(json.dumps(slots_data, indent=2), encoding="utf-8")
        
        return slots_data
        
    except json.JSONDecodeError as je:
        raise ValueError(
            f"Failed to parse JSON from Grok response: {je}. "
            f"Response preview: {response_text[:500] if response_text else 'No response'}"
        )
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            raise RuntimeError(
                f"Model '{model}' not available (404). "
                f"Check access or try alternatives like 'grok-beta'. Full error: {e}"
            )
        elif "401" in error_str or "unauthorized" in error_str.lower():
            raise RuntimeError(
                f"Authentication failed (401). Verify API key is valid and has quota. Full error: {e}"
            )
        elif any(kw in error_str.lower() for kw in ["response_format", "json_object"]):
            raise RuntimeError(
                f"Model '{model}' may not support structured JSON output. "
                f"Try another model. Full error: {e}"
            )
        else:
            raise RuntimeError(f"Grok API call failed: {e}")


if __name__ == "__main__":
    import sys

    # Default to article_view.json and image_slots.json
    input_file = "article_view.json"
    output_file = "image_slots.json"
    
    # Allow command line arguments to override
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    print(f"Generating image slots from {input_file} to {output_file}...")
    try:
        slots_data = generate_image_slots(input_file, output_file)
        print(f"✓ Successfully generated {len(slots_data.get('slots', []))} image slot suggestions")
        print(f"✓ Saved to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
