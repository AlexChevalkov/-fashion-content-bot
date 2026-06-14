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


def fetch_brief_ready_job() -> dict | None:
    url = airtable_table_url(VISUAL_TABLE_NAME)

    params = {
        "pageSize": 1,
        "filterByFormula": "{Visual Status} = 'Brief Ready'",
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
        print("No Brief Ready Visual Jobs found.")
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


def extract_cover_prompt(fields: dict) -> str:
    prompt_pack = fields.get("Krea Prompt Pack", "")
    visual_concept = fields.get("Visual Concept", "")
    visual_hook = fields.get("Visual Hook", "")
    carousel_cover = fields.get("Carousel Cover", "")
    source_title = fields.get("Source Post Title", "")

    style_rules = extract_block(
        prompt_pack,
        ["STYLE RULES", "Style rules"],
        ["NEGATIVE PROMPTS", "COVER IMAGE", "CAROUSEL", "REEL SCENES"],
    )

    negative_prompts = extract_block(
        prompt_pack,
        ["NEGATIVE PROMPTS", "Negative prompts"],
        ["COVER IMAGE", "CAROUSEL", "REEL SCENES"],
    )

    cover_block = extract_block(
        prompt_pack,
        ["COVER IMAGE", "Cover image"],
        ["CAROUSEL", "CAROUSEL IMAGES", "REEL SCENES", "REEL", "--- REEL"],
    )

    if not cover_block:
        cover_block = (
            f"Create a premium fashion-media cover image for this topic: {source_title}. "
            f"Visual hook: {visual_hook}. Visual concept: {visual_concept}."
        )

    final_prompt = f"""
{cover_block}

{style_rules}

{negative_prompts}

Additional art-direction rules:
The object must look like a deliberate fashion editorial symbol, not a random product still life.
Composition should feel like a magazine cover background, with clear negative space reserved for typography.
No text inside the image. No logos. No fake brand names.
The mood should be intelligent, restrained, premium, editorial, not commercial stock photography.
Vertical 4:5 composition for Instagram carousel cover.
""".strip()

    # ограничиваем, чтобы не отправлять слишком длинный prompt
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
        print("Poll response preview:", response.text[:1000])

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


def update_visual_job(record_id: str, fields: dict, image_url: str, job_id: str, prompt: str) -> None:
    url = f"{airtable_table_url(VISUAL_TABLE_NAME)}/{record_id}"

    existing_output_links = fields.get("Output Links", "")
    existing_render_notes = fields.get("Render Notes", "")

    now = datetime.now(timezone.utc).isoformat()

    new_output_entry = f"""
Krea cover image generated:
{image_url}

Krea job_id:
{job_id}

Generated at:
{now}
""".strip()

    new_render_note = f"""
{existing_render_notes}

---

Krea Render Bot v1:
Cover image generated automatically.
Status moved to Needs Visual Review.
Prompt used:
{prompt[:1200]}
""".strip()

    payload = {
        "fields": {
            "Visual Status": "Needs Visual Review",
            "Output Links": f"{existing_output_links}\n\n{new_output_entry}".strip(),
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
    print("Krea Render Bot started:", datetime.now(timezone.utc).isoformat())

    job = fetch_brief_ready_job()

    if not job:
        return

    record_id = job["id"]
    fields = job.get("fields", {})

    print("\n=== Visual Job ===")
    print("Record ID:", record_id)
    print("Job Title:", fields.get("Job Title"))
    print("Source Post Title:", fields.get("Source Post Title"))
    print("Visual Status:", fields.get("Visual Status"))

    prompt = extract_cover_prompt(fields)

    print("\n=== Cover prompt sent to Krea ===")
    print(prompt)

    job_id = create_krea_image_job(prompt)
    print("Krea job_id:", job_id)

    completed_job = wait_for_krea_job(job_id)
    image_url = get_image_url(completed_job)

    print("Krea image URL:", image_url)

    download_image(image_url, "krea_visual_job_cover.png")

    update_visual_job(record_id, fields, image_url, job_id, prompt)

    print("Done. Krea cover image generated and Visual Job moved to Needs Visual Review.")


if __name__ == "__main__":
    main()
