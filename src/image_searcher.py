"""
Google Custom Search API - Image Search
Returns URLs for 10 images based on a search query
"""

import os
from typing import Dict, List

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration - Replace with your actual credentials
API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_KEY")
CX_ID = "c6de2bdfc0a0040c5"

def search_images(query: str, num_results: int = 10) -> List[Dict[str, str]]:
    """
    Search for images using Google Custom Search API
    
    Args:
        query: Search term (e.g., "cats", "mountain sunset")
        num_results: Number of results to return (1-10, default 10)
    
    Returns:
        List of dictionaries containing image data
    """
    # API endpoint
    url = "https://www.googleapis.com/customsearch/v1"
    
    # Request parameters
    params = {
        "key": API_KEY,
        "cx": CX_ID,
        "q": query,
        "searchType": "image",
        "num": num_results,
        "safeSearch": "active",
        "image_as_filetype": "jpg,png,webp"
    }
    
    try:
        # Make the request
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        # Extract image information
        images = []
        
        if "items" in data:
            for item in data["items"]:
                image_url = item.get("link", "")
                
                # Skip URLs with query parameters (often thumbnails/resized versions with wrong content-type)
                if "?" in image_url and not any(ext in image_url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    continue
                
                # Skip HTTP URLs (only HTTPS supported)
                if image_url.startswith("http://"):
                    continue
                
                image_info = {
                    "title": item.get("title", ""),
                    "url": image_url,
                    "thumbnail": item.get("image", {}).get("thumbnailLink", ""),
                    "width": item.get("image", {}).get("width", 0),
                    "height": item.get("image", {}).get("height", 0),
                    "mime_type": item.get("mime", ""),
                    "source_page": item.get("image", {}).get("contextLink", "")
                }
                images.append(image_info)
        
        return images
    
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {response.text}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def print_results(images: List[Dict[str, str]]):
    """Pretty print the search results"""
    if not images:
        print("No images found.")
        return
    
    print(f"\nFound {len(images)} images:\n")
    for i, img in enumerate(images, 1):
        print(f"{i}. {img['title']}")
        print(f"   URL: {img['url']}")
        print(f"   Size: {img['width']}x{img['height']}")
        print(f"   Thumbnail: {img['thumbnail']}")
        print()


if __name__ == "__main__":
    # Example usage
    query = input("Enter search query: ").strip() or "golden retriever"
    
    print(f"Searching for: {query}...")
    results = search_images(query, num_results=10)
    
    print_results(results)
    
    # Just the URLs
    print("\n" + "="*60)
    print("Image URLs only:")
    print("="*60)
    for i, img in enumerate(results, 1):
        print(f"{i}. {img['url']}")
