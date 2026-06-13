import os
import sys
import json
import requests
from urllib.parse import quote
from datetime import datetime

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME")

headers = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

def print_response(label, response):
    print(f"\n--- {label} ---")
    print("Status code:", response.status_code)
    try:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2)[:5000])
    except Exception:
        print(response.text[:5000])

def request_get(label, url):
    response = requests.get(url, headers=headers)
    print_response(label, response)
    return response

def request_post(label, url, payload):
    print(f"\nRequest URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)[:1000]}")
    response = requests.post(url, headers=headers, json=payload)
    print_response(label, response)
    return response

print("\n=== Airtable full diagnostic ===")
print("AIRTABLE_API_KEY present:", bool(AIRTABLE_API_KEY))
print("AIRTABLE_BASE_ID present:", bool(AIRTABLE_BASE_ID))
print("AIRTABLE_TABLE_NAME present:", bool(AIRTABLE_TABLE_NAME))
print("BASE_ID starts with app:", AIRTABLE_BASE_ID.startswith("app") if AIRTABLE_BASE_ID else False)
print("TABLE starts with tbl:", AIRTABLE_TABLE_NAME.startswith("tbl") if AIRTABLE_TABLE_NAME else False)
print("BASE_ID length:", len(AIRTABLE_BASE_ID) if AIRTABLE_BASE_ID else 0)
print("TABLE length:", len(AIRTABLE_TABLE_NAME) if AIRTABLE_TABLE_NAME else 0)

# 1. Metadata: can token see bases?
bases_url = "https://api.airtable.com/v0/meta/bases"
bases_response = request_get("1. LIST ACCESSIBLE BASES", bases_url)

# 2. Metadata: can token see target base schema?
schema_url = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"
schema_response = request_get("2. READ TARGET BASE SCHEMA", schema_url)

target_table_name = None
target_table_id = AIRTABLE_TABLE_NAME

if schema_response.status_code == 200:
    schema = schema_response.json()
    print("\n--- TABLES FOUND IN TARGET BASE ---")
    for table in schema.get("tables", []):
        print(f"Table name: {table.get('name')} | Table id: {table.get('id')}")
        if table.get("id") == AIRTABLE_TABLE_NAME:
            target_table_name = table.get("name")

print("\nTarget table id:", target_table_id)
print("Target table name from schema:", target_table_name)

# 3. Data read test with table id
table_id_encoded = quote(target_table_id, safe="")
records_url_by_id = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id_encoded}?maxRecords=1"
read_by_id_response = request_get("3. READ RECORDS BY TABLE ID", records_url_by_id)

# 4. Data read test with table name, if found
if target_table_name:
    table_name_encoded = quote(target_table_name, safe="")
    records_url_by_name = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name_encoded}?maxRecords=1"
    read_by_name_response = request_get("4. READ RECORDS BY TABLE NAME", records_url_by_name)
else:
    records_url_by_name = None

timestamp = datetime.now().isoformat()

# 5. Create test: old/single-record payload by table id
single_payload = {
    "fields": {
        "Title": f"DIAG SINGLE: {timestamp}"
    }
}

create_single_by_id = request_post(
    "5. CREATE SINGLE PAYLOAD BY TABLE ID",
    f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id_encoded}",
    single_payload
)

if create_single_by_id.status_code in [200, 201]:
    print("\n✅ SUCCESS with single payload by table ID")
    sys.exit(0)

# 6. Create test: batch records payload by table id
batch_payload = {
    "records": [
        {
            "fields": {
                "Title": f"DIAG BATCH: {timestamp}"
            }
        }
    ]
}

create_batch_by_id = request_post(
    "6. CREATE BATCH PAYLOAD BY TABLE ID",
    f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id_encoded}",
    batch_payload
)

if create_batch_by_id.status_code in [200, 201]:
    print("\n✅ SUCCESS with batch payload by table ID")
    sys.exit(0)

# 7. Create test by table name, if schema revealed name
if target_table_name:
    table_name_encoded = quote(target_table_name, safe="")
    create_single_by_name = request_post(
        "7. CREATE SINGLE PAYLOAD BY TABLE NAME",
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name_encoded}",
        single_payload
    )

    if create_single_by_name.status_code in [200, 201]:
        print("\n✅ SUCCESS with single payload by table name")
        sys.exit(0)

    create_batch_by_name = request_post(
        "8. CREATE BATCH PAYLOAD BY TABLE NAME",
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name_encoded}",
        batch_payload
    )

    if create_batch_by_name.status_code in [200, 201]:
        print("\n✅ SUCCESS with batch payload by table name")
        sys.exit(0)

print("\n❌ FAILED: all Airtable write tests failed.")
print("Interpretation:")
print("- If READ RECORDS failed with 403: token lacks data.records:read access.")
print("- If READ RECORDS succeeded but all CREATE tests failed with 403: token lacks data.records:write access or Airtable blocks API record creation.")
print("- If table name works but table ID fails: use table name in AIRTABLE_TABLE_NAME.")
sys.exit(1)
