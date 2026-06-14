import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

import requests


KREA_API_KEY = os.environ["KREA_API_KEY"]
AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]

VISUAL_TABLE_NAME = os.environ.get("AIRTABLE_VISUAL_TABLE_NAME", "Visual Jobs")

KREA_API_BASE = "https://api.krea.ai"
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_SLIDES_TO_RENDER = 3


def airtable_table_url(table_name: str) -> str:
    table_encoded = quote(table_name, safe="")
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_encoded}"


def airtable_headers() -> dict:
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


def krea_headers() -> dict:
    return {
        "Authorization": f"Bearer {KREA_API_KEY}",
        "Content-Type": "application/json",
    }


def fetch_cover_approved_job() -> dict | None:
    url = airtable_table_url(VISUAL_TABLE_NAME)

    params = {
        "pageSize": 1,
        "filterByFormula": "{Visual Status} = 'Cover Approved'",
    }

    response = requests.get(
        url,
        headers=airtable_headers(),
        params=params,
        timeout=30,
    )

    print("Read Visual Jobs status:", response.status_code)
    print("Read Visual Jobs preview:", response.text[:1000])

    if response.status_code != 200:
        raise RuntimeError("Could not read Visual Jobs")

    records = response.json().get("records", [])

    if not records:
        print("No Cover Approved Visual Jobs found.")
        return None

    return records[0]


def extract_block(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    if not text:
        return ""

    upper = text.upper()

    start_index = -1
    for pattern in start_patterns:
        idx = upper.find(pattern.upper())
        if idx != -1:
            start_index = idx
            break

    if start_index == -1:
        return ""

    end_index = len(text)

    for pattern in end_patterns:
        idx = upper.find(pattern.upper(), start_index + 1)
        if idx != -1:
            end_index = min(end_index, idx)

    return text[start_index:end_index].strip()


def extract_style_rules(prompt_pack: str) -> str:
    return extract_block(
        prompt_pack,
        ["STYLE RULES", "Style rules"],
        ["NEGATIVE PROMPTS", "COVER IMAGE", "CAROUSEL", "REEL SCENES"],
    )


def extract_negative_prompts(prompt_pack: str) -> str:
    return extract_block(
        prompt_pack,
        ["NEGATIVE PROMPTS", "Negative prompts"],
        ["COVER IMAGE", "CAROUSEL", "REEL SCENES"],
    )


def extract_carousel_block(prompt_pack: str) -> str:
    return extract_block(
        prompt_pack,
        ["CAROUSEL IMAGES", "CAROUSEL SLIDE IMAGES", "Carousel images"],
        ["REEL SCENES", "--- REEL", "REEL", "VIDEO", "STYLE RULES"],
    )


def parse_slide_prompts(carousel_block: str) -> list[dict]:
    """
    Ищет промпты вида:
    Slide 2: ...
    — Slide 3: ...
    Слайд 4: ...
    """
    if not carousel_block:
        return []

    text = carousel_block.replace("—", "\n—")
    pattern = r"(?:Slide|Слайд)\s*(\d+)\s*[:\-]\s*(.*?)(?=\n\s*[—-]?\s*(?:Slide|Слайд)\s*\d+\s*[:\-]|\Z)"

    matches = re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL)

    slide_prompts = []

    for number, prompt in matches:
        clean_prompt = prompt.strip()
        clean_prompt = re.sub(r"\s+", " ", clean_prompt)

        if len(clean_prompt) < 20:
            continue

        slide_prompts.append(
            {
                "slide_number": int(number),
                "prompt": clean_prompt,
            }
        )

    return slide_prompts


def fallback_slide_prompts(fields: dict) -> list[dict]:
    source_title = fields.get("Source Post Title", "")
    visual_concept = fields.get("Visual Concept", "")
    visual_hook = fields.get("Visual Hook", "")

    return [
        {
            "slide_number": 2,
            "prompt": f"A premium fashion editorial image for the topic '{source_title}'. Visual hook: {visual_hook}. Concept: {visual_concept}. A single fashion object placed with large negative space, cold editorial lighting, matte textures, no text, no logos.",
        },
        {
            "slide_number": 3,
            "prompt": f"A visual contrast image for '{source_title}': one side suggests mass fashion speed and visual noise, the other side shows restrained luxury silence and distance. Editorial, minimal, no text, no logos.",
        },
        {
            "slide_number": 4,
            "prompt": f"A close-up fashion editorial still life for '{source_title}': fabric, box, glove, tag or object arranged with deliberate distance between elements. Cold light, matte surface, restrained luxury, no text.",
        },
    ]


def build_final_prompt(base_prompt: str, style_rules: str, negative_prompts: str, slide_number: int) -> str:
    final_prompt = f"""
CAROUSEL SLIDE {slide_number} BACKGROUND IMAGE:

{base_prompt}

{style_rules}

{negative_prompts}

Additional production rules:
Create a visual background for an Instagram carousel slide, not a finished poster.
Do not put any text inside the image.
No logos. No fake brand names. No random letters.
Leave clean negative space where typography can be added later.
The image must feel like intelligent fashion media, not stock photography.
The subject must look deliberate and symbolic.
Vertical 4:5 composition.
Premium editorial lighting. Matte textures. Controlled palette.
""".strip()

    return final_prompt[:4000]


def create_krea_image_job(prompt: str) -> str:
    url = f"{KREA_API_BASE}/generate/image/krea/krea-2/medium"

    payload = {
        "prompt": prompt,
        "aspect_ratio": "4:5",
        "resolution": "1K",
        "creativity": "low",
    }

    response = requests.post(
        url,
        headers=krea_headers(),
        json=payload,
        timeout=60,
    )

    print("Create Krea job status:", response.status_code)
    print("Create Krea job response:", response.text[:1200])

    if response.status_code not in [200, 201, 202]:
        raise RuntimeError("Krea image job creation failed")

    data = response.json()
    job_id = data.get("job_id")

    if not job_id:
        raise RuntimeError("No job_id returned from Krea")

    return job_id


def wait_for_krea_job(job_id: str, max_wait_seconds: int = 300) -> dict:
    url = f"{KREA_API_BASE}/jobs/{job_id}"
    started = time.time()

    while True:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {KREA_API_KEY}"},
            timeout=60,
        )

        print("Poll status:", response.status_code)
        print("Poll response preview:", response.text[:700])

        if response.status_code != 200:
            raise RuntimeError("Krea job polling failed")

        data = response.json()
        status = data.get("status")

        print("Krea job status:", status)

        if status == "completed":
            return data

        if status in ["failed", "cancelled", "canceled"]:
            raise RuntimeError(f"Krea job failed: {data}")

        if time.time() - started > max_wait_seconds:
            raise TimeoutError("Krea job timed out")

        time.sleep(5)


def get_image_url(job_data: dict) -> str:
    result = job_data.get("result") or {}
    urls = result.get("urls") or []

    if not urls:
        raise RuntimeError("No image URLs found in completed Krea job")

    return urls[0]


def download_image(image_url: str, filename: str) -> Path:
    response = requests.get(image_url, timeout=120)

    if response.status_code != 200:
        raise RuntimeError("Could not download generated image")

    output_path = OUTPUT_DIR / filename
    output_path.write_bytes(response.content)

    print("Saved image to:", output_path)

    return output_path


def update_visual_job(record_id: str, fields: dict, rendered_results: list[dict]) -> None:
    url = f"{airtable_table_url(VISUAL_TABLE_NAME)}/{record_id}"

    existing_output_links = fields.get("Output Links", "")
    existing_render_notes = fields.get("Render Notes", "")

    now = datetime.now(timezone.utc).isoformat()

    output_lines = [
        "",
        "",
        "Krea carousel slide images generated:",
    ]

    for result in rendered_results:
        output_lines.append(
            f"Slide {result['slide_number']}: {result['image_url']} | job_id: {result['job_id']}"
        )

    output_lines.append(f"Generated at: {now}")

    new_render_note = f"""
{existing_render_notes}

---

Krea Carousel Render Bot v1:
Generated {len(rendered_results)} carousel background images.
Text overlays are NOT baked into images.
Next step: review images and later assemble carousel slides with typography.
""".strip()

    payload = {
        "fields": {
            "Visual Status": "Needs Visual Review",
            "Output Links": f"{existing_output_links}{''.join([line + chr(10) for line in output_lines])}".strip(),
            "Render Notes": new_render_note,
        },
        "typecast": True,
    }

    response = requests.patch(
        url,
        headers=airtable_headers(),
        json=payload,
        timeout=30,
    )

    print("Update Visual Job status:", response.status_code)
    print("Update Visual Job response:", response.text[:1200])

    if response.status_code not in [200, 201, 202]:
        raise RuntimeError("Could not update Visual Job")


def main() -> None:
    print("Krea Carousel Render Bot started:", datetime.now(timezone.utc).isoformat())

    job = fetch_cover_approved_job()

    if not job:
        return

    record_id = job["id"]
    fields = job.get("fields", {})

    print("\n=== Visual Job ===")
    print("Record ID:", record_id)
    print("Job Title:", fields.get("Job Title"))
    print("Source Post Title:", fields.get("Source Post Title"))
    print("Visual Status:", fields.get("Visual Status"))

    prompt_pack = fields.get("Krea Prompt Pack", "")
    style_rules = extract_style_rules(prompt_pack)
    negative_prompts = extract_negative_prompts(prompt_pack)
    carousel_block = extract_carousel_block(prompt_pack)

    slide_prompts = parse_slide_prompts(carousel_block)

    if not slide_prompts:
        print("No slide prompts parsed. Using fallback slide prompts.")
        slide_prompts = fallback_slide_prompts(fields)

    slide_prompts = slide_prompts[:MAX_SLIDES_TO_RENDER]

    print(f"Slides to render: {len(slide_prompts)}")

    rendered_results = []

    for item in slide_prompts:
        slide_number = item["slide_number"]
        base_prompt = item["prompt"]
        final_prompt = build_final_prompt(
            base_prompt=base_prompt,
            style_rules=style_rules,
            negative_prompts=negative_prompts,
            slide_number=slide_number,
        )

        print(f"\n=== Prompt for slide {slide_number} ===")
        print(final_prompt)

        job_id = create_krea_image_job(final_prompt)
        print("Krea job_id:", job_id)

        completed_job = wait_for_krea_job(job_id)
        image_url = get_image_url(completed_job)

        print(f"Krea image URL for slide {slide_number}:", image_url)

        download_image(
            image_url,
            f"krea_carousel_slide_{slide_number}.png",
        )

        rendered_results.append(
            {
                "slide_number": slide_number,
                "image_url": image_url,
                "job_id": job_id,
            }
        )

    update_visual_job(record_id, fields, rendered_results)

    print("Done. Carousel slide images generated and Visual Job moved to Needs Visual Review.")


if __name__ == "__main__":
    main()
