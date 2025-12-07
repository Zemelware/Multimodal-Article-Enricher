from bs4 import BeautifulSoup

HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def html_to_article_view(html: str) -> tuple[str, dict]:
    """Parse Grokipedia-style HTML into a JSON-able article view and inject IDs."""

    soup = BeautifulSoup(html, "html.parser")

    # 1. Find the main article element.
    article = soup.find("article", attrs={"itemtype": "https://schema.org/Article"})
    if article is None:
        article = soup.find("article")
    if article is None:
        raise ValueError("No <article> tag found in HTML.")

    # 2. Extract title from first h1 inside article (if present)
    title_tag = article.find("h1")
    title_text = title_tag.get_text(strip=True) if title_tag else ""

    sections: list[dict] = []
    current_section: dict | None = None
    section_counter = 0
    paragraph_counter = 0

    # 3. Walk headings + paragraphs inside the article, in document order
    # Note: We also look for 'span' because some Grokipedia pages use styled spans instead of <p> tags.
    for tag in article.find_all(HEADING_TAGS + ["p", "span"], recursive=True):
        if tag.name in HEADING_TAGS:
            level = int(tag.name[1])

            # Skip the title <h1> (it's the article title, not a section)
            if tag is title_tag:
                continue

            section_counter += 1
            section_id = tag.get("id") or f"sec_{section_counter}"
            tag["id"] = section_id

            current_section = {
                "id": section_id,
                "level": level,
                "heading": tag.get_text(strip=True),
                "paragraphs": [],
            }
            sections.append(current_section)

        elif tag.name == "p" or (
            tag.name == "span"
            and "mb-4" in tag.get("class", [])
            and "block" in tag.get("class", [])
        ):
            paragraph_counter += 1
            p_id = tag.get("id") or f"p_{paragraph_counter}"
            tag["id"] = p_id

            paragraph_text = tag.get_text(strip=True)

            # Paragraph before any heading → synthetic "Introduction" section
            if current_section is None:
                section_counter += 1
                sec_id = f"sec_{section_counter}"

                # Inject a hidden anchor for the synthetic section so images can target it
                section_anchor = soup.new_tag("div", id=sec_id)
                tag.insert_before(section_anchor)

                current_section = {
                    "id": sec_id,
                    "level": 2,
                    "heading": "Introduction",
                    "paragraphs": [],
                }
                sections.append(current_section)

            current_section["paragraphs"].append({"id": p_id, "text": paragraph_text})

    article_view = {"title": title_text, "sections": sections}

    mutated_html = str(soup)
    return mutated_html, article_view


def inject_images_into_html(html: str, image_slots: list[dict]) -> str:
    """Insert <figure> elements into mutated HTML according to image slots."""

    soup = BeautifulSoup(html, "html.parser")

    for slot in image_slots:
        section_id = slot.get("section_id")
        paragraph_id = slot.get("paragraph_id")
        position = slot.get("position", "after")
        image_url = slot.get("image_url")
        alt_text = slot.get("alt_text", "")
        caption = slot.get("caption", "")

        if not image_url:
            continue

        # 1. Find anchor element
        anchor = None
        if paragraph_id is not None:
            anchor = soup.find(id=paragraph_id)
        if anchor is None and section_id is not None:
            anchor = soup.find(id=section_id)
        if anchor is None:
            continue  # nowhere to attach

        # 2. Build <figure> element
        figure = soup.new_tag("figure", **{"class": "mm-slot"})
        img = soup.new_tag("img", src=image_url, alt=alt_text)
        figcaption = soup.new_tag("figcaption", style="font-size: 0.875rem; font-style: italic; text-align: center; color: #6b7280; margin-top: 0.5rem; padding: 0 1rem; line-height: 1.5;")
        figcaption.string = caption
        figure.append(img)
        figure.append(figcaption)

        # 3. Insert figure relative to anchor
        if position == "before":
            anchor.insert_before(figure)
        elif position == "before_heading":
            heading_anchor = soup.find(id=section_id) if section_id else None
            if heading_anchor:
                heading_anchor.insert_before(figure)
            else:
                anchor.insert_before(figure)
        elif position == "after_heading":
            heading_anchor = soup.find(id=section_id) if section_id else None
            if heading_anchor:
                heading_anchor.insert_after(figure)
            else:
                anchor.insert_after(figure)
        else:  # default "after"
            anchor.insert_after(figure)

    enhanced_html = str(soup)
    return enhanced_html

if __name__ == "__main__":
    # load Elon_Musk.html
    from pathlib import Path
    html_path = Path("test_stuff/Elon_Musk.html")
    html_content = html_path.read_text(encoding="utf-8")
    mutated_html, article_view = html_to_article_view(html_content)
    # save mutated_html to file
    output_path = Path("test_stuff/mutated_article.html")
    output_path.write_text(mutated_html, encoding="utf-8")
    # save article_view to json file
    import json
    json_path = Path("test_stuff/article_view.json")
    json_path.write_text(json.dumps(article_view, indent=2), encoding="utf-8")

    from pathlib import Path
    html_path = Path("test_stuff/mutated_article.html")
    mutated_article = html_path.read_text(encoding="utf-8")

    image_slots = [
        {
            "section_id": "sec_1",              # Early Life (first real section)
            "paragraph_id": None,
            "position": "after_heading",
            "image_url": "https://nmspacemuseum.org/wp-content/uploads/2019/03/Elon_Musk.jpg",
            "alt_text": "Elon Musk in 2018 at the Royal Society.",
            "caption": "Elon Musk photographed in 2018."
        },
        {
            "section_id": "twitters-pre-acquisition-challenges",              # Early Entrepreneurial Ventures
            "paragraph_id": "p_4",              # first paragraph in that section
            "position": "after",
            "image_url": "https://image.cnbcfm.com/api/v1/image/107293744-1693398435735-elon.jpg?v=1738327797",
            "alt_text": "Logo of Zip2 Corporation.",
            "caption": "Zip2, one of Musk's earliest software ventures."
        },
        {
            "section_id": "the-buyout-process",              # SpaceX
            "paragraph_id": None,
            "position": "before_heading",
            "image_url": "https://www.spacex.com/assets/images/vehicles/starship/mobile/starship_carousel2_card4_v2_m.jpg",
            "alt_text": "Falcon 9 first stage landing during Flight 20.",
            "caption": "The historic first successful landing of a Falcon 9 booster."
        },
        {
            "section_id": "public-statements-and-termination-efforts-july-2022",              # Tesla
            "paragraph_id": "p_28",             # pick any paragraph from Tesla
            "position": "after",
            "image_url": "https://www.rollingstone.com/wp-content/uploads/2023/12/elon-musk-tesla.jpg?w=1581&h=1054&crop=1",
            "alt_text": "Tesla Model 3 parked.",
            "caption": "The Tesla Model 3, one of the company’s most successful vehicles."
        },
    ]

    enhanced_html = inject_images_into_html(mutated_article, image_slots)
    # save enhanced_html to file
    output_path = Path("test_stuff/enhanced_article.html")
    output_path.write_text(enhanced_html, encoding="utf-8")
