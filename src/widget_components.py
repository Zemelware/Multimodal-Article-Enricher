"""
Custom widget component renderers for Grokipedia articles.

These functions take extracted data (from Grok) and generate consistent, Tailwind-styled HTML snippets.
Assumes site's Tailwind CSS is available (inlined in scraped HTML); self-contained with classes for theme matching.
"""

from typing import Dict, Any, List


def render_timeline(events: List[Dict[str, str]]) -> str:
    """
    Render a vertical timeline widget.
    events: [{"date": "1971", "title": "Birth", "description": "Born in Pretoria..."}, ...]
    """
    if not events:
        return ""
    
    html = '''
<div class="widget-timeline mb-8 p-6 bg-white rounded-lg shadow-sm border border-gray-200 border-l-4 border-[#1d9bf0] dark:bg-black dark:border-[#1d9bf0] dark:text-white">
  <h3 class="text-xl font-bold mb-6 text-center text-gray-900 dark:text-white">Timeline of Key Events</h3>
  <ol class="relative border-l border-gray-300 dark:border-gray-800 ml-4">
'''
    for event in events[:8]:  # Limit to 8
        html += f'''
    <li class="mb-10 ml-6">
      <span class="absolute flex items-center justify-center w-3 h-3 bg-[#1d9bf0]/10 rounded-full -left-1.5 border border-white dark:border-black dark:bg-[#1d9bf0]/20"></span>
      <time class="mb-1 text-sm font-semibold leading-none text-gray-900 dark:text-white bg-[#1d9bf0]/5 px-2 py-1 rounded-full dark:bg-[#1d9bf0]/10">{event.get("date", "")}</time>
      <h4 class="flex items-center mb-2 text-lg font-semibold text-gray-900 dark:text-white">{event.get("title", "")}</h4>
      <p class="text-base font-normal text-gray-500 dark:text-gray-300 mb-4">{event.get("description", "")}</p>
    </li>
'''
    html += '  </ol>\n</div>'
    return html


def render_key_facts(facts: List[str]) -> str:
    """
    Render a sidebar key facts panel.
    facts: ["Fact 1...", "Fact 2..."]
    """
    if not facts:
        return ""
    
    facts_html = ""
    for fact in facts[:10]:  # Limit
        facts_html += f'<li class="mb-2 text-gray-700 dark:text-white pl-2 border-l-2 border-[#1d9bf0]/20 dark:border-[#1d9bf0]/40">{fact}</li>'
    
    html = f'''
<aside class="widget-key-facts w-full md:w-1/3 float-right ml-6 mb-6 p-4 bg-white rounded-lg border border-gray-200 border-l-4 border-[#1d9bf0] dark:bg-black dark:border-gray-900 dark:border-l-4 dark:border-[#1d9bf0] dark:text-white">
  <h3 class="text-lg font-semibold mb-3 text-gray-900 dark:text-white">Key Facts</h3>
  <ul class="space-y-1 text-sm">
    {facts_html}
  </ul>
</aside>
'''
    return html








# Map type to renderer and data schema hint for Grok prompts
def render_key_locations(locations: List[Dict[str, Any]]) -> str:
    """
    Render a static list of key locations.
    locations: [{"name": str, "lat": str or float, "lng": str or float, "description": str}, ...] Up to 6.
    """
    if not locations:
        return ""
    
    html = '''
<div class="widget-key-locations mb-8 p-4 bg-white dark:bg-black rounded-lg shadow-md border border-[#1d9bf0]/20 dark:border-[#1d9bf0]/40">
  <h3 class="text-xl font-bold mb-6 text-center text-gray-900 dark:text-white">Key Locations</h3>
  <div class="space-y-4">
'''
    for loc in locations[:6]:
        name = loc.get("name", "")
        lat = loc.get("lat", "")
        lng = loc.get("lng", "")
        desc = loc.get("description", "")
        coords = f"Lat: {lat}, Lng: {lng}" if lat and lng else "Coordinates unavailable"
        html += f'''
    <div class="p-3 bg-gray-50 dark:bg-gray-900/50 rounded border-l-4 border-[#1d9bf0]/30 dark:border-[#1d9bf0]/50">
      <h4 class="font-semibold text-gray-900 dark:text-white mb-1">{name}</h4>
      <p class="text-sm text-gray-600 dark:text-gray-400">{desc}</p>
      <p class="text-xs text-gray-500 dark:text-gray-500">{coords}</p>
    </div>
'''
    html += '  </div>\n</div>'
    return html



WIDGET_TYPES = {
    "timeline": {
        "renderer": render_timeline,
        "data_schema": "List of dicts: [{'date': str (e.g. '1971'), 'title': str, 'description': str}, ...] Extract 4-8 chronological events from context.",
    },
    "key_facts": {
        "renderer": render_key_facts,
        "data_schema": "List of strings: key facts, stats, or highlights (5-10 bullet points, concise).",
    },


    "key_locations": {
        "renderer": render_key_locations,
        "data_schema": "List of dicts: [{'name': str (e.g. 'Pretoria'), 'lat': str or float (e.g. -25.75), 'lng': str or float (e.g. 28.23), 'description': str}, ...] Extract 3-6 key locations from context; include approx coords if exact unknown.",
    },
    # Add more widget types as needed
}

def render_widget(widget_type: str, extracted_data: Any) -> str:
    """
    Generic renderer: lookup and call specific function.
    """
    config = WIDGET_TYPES.get(widget_type)
    if config and config["renderer"]:
        return config["renderer"](extracted_data)
    else:
        print(f"Warning: No renderer for {widget_type}")
        return f'<div class="widget-unknown p-4 bg-yellow-100">Unsupported widget: {widget_type}</div>'
