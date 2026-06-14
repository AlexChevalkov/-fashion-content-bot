import os
import time
from pathlib import Path

import requests


KREA_API_KEY = os.environ["KREA_API_KEY"]

API_BASE = "https://api.krea.ai"
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

PROMPT = """
A single luxury object — a closed black box or a folded cashmere piece — placed on a vast empty cold stone surface.
Extreme negative space. The object is small in the frame, surrounded by silence.
Cold natural side light. No people. No branding. No text.
Editorial fashion photography aesthetic, ultra-minimal composition, intelligent fashion media mood.
Palette: ivory white, cold grey, deep black, dusty bordeaux accent.
No glossy surfaces, no smiling models, no stock photo feeling.
"""


def headers():
    return {
        "Authorization": f"Bearer {KREA_API_KEY}",
        "Content-Type": "application/json",
    }


def create_image_job():
    url = f"{API_BASE}/generate/image/krea/krea-2/medium"

    payload = {
        "prompt": PROMPT,
        "aspect_ratio": "4:5",
        "resolution": "1K",
        "creativity": "low",
    }

    response = requests.post(
        url,
        headers=headers(),
        json=payload,
        timeout=60,
    )

    print("Create job status:", response.status_code)
    print("Create job response:", response.text[:1000])

    if response.status_code not in [200, 201, 202]:
        raise RuntimeError("Krea image job creation failed")

    data = response.json()
    job_id = data.get("job_id")

    if not job_id:
        raise RuntimeError("No job_id returned from Krea")

    return job_id


def wait_for_job(job_id: str, max_wait_seconds: int = 240):
    url = f"{API_BASE}/jobs/{job_id}"

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


def download_first_image(job_data):
    result = job_data.get("result") or {}
    urls = result.get("urls") or []

    if not urls:
        raise RuntimeError("No image URLs found in completed Krea job")

    image_url = urls[0]
    print("Krea image URL:", image_url)

    response = requests.get(image_url, timeout=120)

    if response.status_code != 200:
        raise RuntimeError("Could not download generated image")

    output_path = OUTPUT_DIR / "krea_cover_test.png"
    output_path.write_bytes(response.content)

    print("Saved image to:", output_path)


def main():
    print("Starting Krea image API test...")

    job_id = create_image_job()
    print("Krea job_id:", job_id)

    completed_job = wait_for_job(job_id)
    download_first_image(completed_job)

    print("Done. Krea image test completed.")


if __name__ == "__main__":
    main()
