import os
from urllib.parse import quote
from datetime import datetime, timezone

import requests


AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]

VISUAL_TABLE_NAME = "Visual Jobs"


def main():
    table_encoded = quote(VISUAL_TABLE_NAME, safe="")
    base_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_encoded}"

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    params = {
        "pageSize": 1,
        "filterByFormula": "{Visual Status} = 'Queued'",
    }

    read_response = requests.get(
        base_url,
        headers=headers,
        params=params,
        timeout=30,
    )

    print("Read status:", read_response.status_code)
    print("Read response preview:", read_response.text[:1000])

    if read_response.status_code != 200:
        raise RuntimeError("Could not read Visual Jobs")

    records = read_response.json().get("records", [])

    if not records:
        print("No Queued Visual Jobs found.")
        return

    record = records[0]
    record_id = record["id"]
    fields = record.get("fields", {})

    print("Updating record:", record_id)
    print("Job Title:", fields.get("Job Title"))

    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "fields": {
            "Render Notes": f"GitHub update test OK at {now}"
        }
    }

    update_url = f"{base_url}/{record_id}"

    update_response = requests.patch(
        update_url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    print("Update status:", update_response.status_code)
    print("Update response preview:", update_response.text[:1000])

    if update_response.status_code not in [200, 201, 202]:
        raise RuntimeError("Could not update Visual Job")

    print("Done. Visual Job update test completed.")


if __name__ == "__main__":
    main()
