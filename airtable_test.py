import os
import requests
from urllib.parse import quote
from datetime import datetime

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE_NAME = os.environ["AIRTABLE_TABLE_NAME"]

table_name_encoded = quote(AIRTABLE_TABLE_NAME, safe="")
url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name_encoded}"

headers = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "fields": {
        "Title": "TEST: GitHub пишет в Airtable",
        "Status": "Needs Review",
        "Rubric": "Fashion Context",
        "Format": "Single Post",
        "Hook": "Тестовая карточка из GitHub.",
        "Visual Headline": "Airtable Test",
        "Raw Text": f"Тест создан автоматически: {datetime.now().isoformat()}",
        "Final Caption": "Это тестовая карточка. Если она появилась в Alex Review, значит связь GitHub → Airtable работает.",
    }
}

response = requests.post(url, headers=headers, json=payload)

print("Status code:", response.status_code)
print("Response:", response.text)

if response.status_code not in [200, 201]:
    raise Exception("Airtable record was not created")
