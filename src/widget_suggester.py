"""
Grok Widget Suggester - Uses Grok API to analyze an article JSON structure and suggest optimal widget placement slots.

Function:
def generate_widget_slots(input_path: str, output_path: str = "widget_slots.json", api_key: Optional[str] = None, model: str = "grok-4-1-fast-non-reasoning", max_slots: int = 5) -> Dict[str, Any]

Loads JSON article (title + sections/paragraphs with IDs), queries Grok API for widget slot suggestions, saves JSON to output_path, returns the data dict.

Example:
    from widget_suggester import generate_widget_slots
    slots_data = generate_widget_slots("article_view.json")

Requires:
- XAI_API_KEY env var or pass api_key=...
- Deps: openai, httpx, python-dotenv

Grok suggests slots with section/paragraph positions, widget types (timeline, key_facts, etc.), content hints for generation, priority scores, and recommended dimensions.
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


def generate_widget_slots(
    input_path: Optional[str] = None,
    article: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = "widget_slots.json",
    api_key: Optional[str] = None,
    model: str = "grok-4-1-fast-non-reasoning",
    max_slots: int = 5
) -> Dict[str, Any]:
    """
    Generate widget slot suggestions from article JSON using Grok API.
    
    Loads the JSON file or uses provided article, formats for Grok, gets suggestions, saves to output JSON, returns data.
    
    Args:
        input_path: Optional path to article JSON file. Mutually exclusive with 'article'.
        article: Optional article dict. Format: {"title": str, "sections": [{"id": str, "level": int, "heading": str, "paragraphs": [{"id": str, "text": str}]}]}
        output_path: Path to save slots JSON. If None, skips saving.
        api_key: XAI API key; loads from env if None
        model: Grok model name
        max_slots: Max slots to suggest
        
    Returns:
        Dict with "slots": List[Dict], each slot:
        - section_id: str
        - paragraph_id: str or null
        - position: str (e.g., "after", "after_heading")
        - widget_type: str (e.g., "timeline", "key_facts")
        - content_hint: str (guidance for generating widget content)
        - priority: float (0.0-1.0)
        - recommended_dimensions: Dict[str, int] = {"width": int, "height": int}
    """
    load_dotenv()
    api_key = api_key or os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError(
            "XAI_API_KEY not found. Set environment variable or pass api_key parameter."
        )
    
    # Load or validate article data
    if input_path is not None and article is not None:
        raise ValueError("Provide only one of 'input_path' or 'article', not both.")
    
    if article is None:
        if input_path is None:
            raise ValueError("Must provide either 'input_path' or 'article'")
        
        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        content = input_path_obj.read_text(encoding="utf-8")
        
        try:
            article = json.loads(content)
            if "title" not in article or "sections" not in article:
                raise ValueError("JSON missing required 'title' or 'sections' keys")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {input_path}: {e}")
        except ValueError as e:
            raise ValueError(f"Article validation failed: {e}")
    else:
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
            "content": """You are an expert content strategist specializing in enhancing articles with interactive widgets and custom visual components to improve engagement and readability.

Your task is to analyze an article and suggest optimal locations for custom widgets. Use ONLY these three widget types (no others, do not suggest images as widgets—images are handled separately):
- "timeline": For chronological sequences of events, milestones, or history. Data schema: List of dicts with 'date', 'title', 'description'.
- "key_facts": Sidebar panel with bullet points of important facts, stats, or highlights. Data schema: List of concise fact strings (5-10).
- "key_locations": Static list of important places with descriptions and coords. Data schema: List of dicts with 'name', 'description', 'lat', 'lng' (approx if needed).

For each suggested widget slot, provide:
- The exact section_id and paragraph_id (or null if placing after heading or section-wide)
- The position relative to the content (e.g., "after", "after_heading", "before")
- The widget_type from the list above
- A content_hint: detailed description of what data or elements to include in the widget (e.g., specific events, facts, comparisons from the section)
- A priority score (0.0 to 1.0) indicating how valuable this widget would be
- Recommended widget dimensions ({"width": integer, "height": integer} in pixels) suitable for the site's responsive layout

CRITICAL: Your response must consist SOLELY of valid JSON object. NO additional text, markdown, or explanations. Ensure:
- All strings in double quotes
- Numbers unquoted
- Null for paragraph_id as null (not "null")
- Every slot has exactly: section_id (str), paragraph_id (str or null), position (str), widget_type (str), content_hint (str), priority (float), recommended_dimensions (obj)
- Suggest up to {max_slots} slots, prioritize highest impact
- Use section_id and paragraph_id exactly as in article

{
  "slots": [
    {{
      "section_id": "sec_1",
      "paragraph_id": null,
      "position": "after_heading",
      "widget_type": "timeline",
      "content_hint": "Timeline of Elon Musk's early life: birth in 1971, move to Canada 1989, university education, first companies.",
      "priority": 0.9,
      "recommended_dimensions": {{"width": 800, "height": 600}}
    }},
    {{
      "section_id": "sec_5",
      "paragraph_id": "p_3",
      "position": "after",
      "widget_type": "key_facts",
      "content_hint": "Key facts about SpaceX achievements: first private company to send spacecraft to ISS, Falcon 1 launches, etc.",
      "priority": 0.8,
      "recommended_dimensions": {{"width": 400, "height": 500}}
    }}
  ]
}

GUIDELINES:
- Suggest widgets that add interactivity or visual interest: timelines for history, tables for data comparison, facts for summaries
- Place after headings for section-wide widgets, after specific paragraphs for targeted
- Content hints should reference specific article elements to extract/generate from
- Priority: 0.9-1.0 essential, 0.6-0.8 valuable, lower optional
- Dimensions: Tailor to type - timelines wider, facts narrower sidebars; consider responsive design with Tailwind classes in mind
- Avoid over-suggestion; focus on 3-5 high-impact placements per article"""
        },
        {
            "role": "user",
            "content": f"""Analyze this article and suggest optimal widget placement slots.

Article Structure:
{article_text}

Provide up to {max_slots} widget slot suggestions. Focus on placements that would significantly enhance reader engagement and understanding.

Return ONLY the JSON object with the slots array, no additional text."""
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
        
        # Validate each slot has required fields
        required_fields = {"section_id", "position", "widget_type", "content_hint", "priority", "recommended_dimensions"}
        for i, slot in enumerate(slots_data["slots"]):
            # paragraph_id optional
            slot_fields = set(slot.keys())
            missing = required_fields - slot_fields
            if missing:
                raise ValueError(f"Slot {i} missing fields: {missing}")
            if not isinstance(slot.get("priority"), (int, float)) or not 0 <= slot["priority"] <= 1:
                raise ValueError(f"Slot {i} priority must be float 0.0-1.0")
            dims = slot.get("recommended_dimensions")
            if not isinstance(dims, dict) or "width" not in dims or "height" not in dims:
                raise ValueError(f"Slot {i} recommended_dimensions invalid")
        
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
                f"Model '{model}' not available (404). Try alternatives. Full error: {e}"
            )
        elif "401" in error_str or "unauthorized" in error_str.lower():
            raise RuntimeError(
                f"Authentication failed (401). Verify API key. Full error: {e}"
            )
        elif any(kw in error_str.lower() for kw in ["response_format", "json_object"]):
            raise RuntimeError(
                f"Model '{model}' may not support JSON output. Try another. Full error: {e}"
            )
        else:
            raise RuntimeError(f"Grok API call failed: {e}")


if __name__ == "__main__":
    import sys

    input_file = "article_view.json"
    output_file = "widget_slots.json"
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    print(f"Generating widget slots from {input_file} to {output_file}...")
    try:
        slots_data = generate_widget_slots(input_file, output_file)
        print(f"✓ Successfully generated {len(slots_data.get('slots', []))} widget slot suggestions")
        print(f"✓ Saved to {output_file}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)