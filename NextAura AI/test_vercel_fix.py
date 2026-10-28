import os
import json
import sqlite3
import database
from app import app

client = app.test_client()

print("=== TEST 1: Standard local execution of /api/diagnose ===")
res1 = client.post("/api/diagnose", json={
    "appliance_type": "Air Conditioners",
    "brand_model": "Daikin 1.5T",
    "symptoms": "AC is blowing warm air and compressor clicks",
    "error_code": ""
})
assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
data1 = res1.get_json()
assert data1["diagnostic_log_id"] is not None, "Expected valid diagnostic_log_id"
assert "safe_checks" in data1, "Expected safe_checks in response"
assert "indicative_cost" in data1, "Expected indicative_cost in response"
print(f"Test 1 passed! Log ID: {data1['diagnostic_log_id']}")

print("\n=== TEST 2: Simulated Vercel / AWS Lambda Serverless environment ===")
# Set Vercel environment variables
os.environ["VERCEL"] = "1"
os.environ["VERCEL_ENV"] = "production"
os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "nextaura-prod-api"

# Verify serverless detection
assert database.is_serverless() == True, "Serverless detection failed"
serverless_path = database.get_db_path()
print(f"Serverless DB path resolved to: {serverless_path}")
assert ("temp" in serverless_path.lower() or "tmp" in serverless_path.lower()), "Should resolve to temp/tmp directory"

# Call /api/diagnose in Vercel simulation mode
res2 = client.post("/api/diagnose", json={
    "appliance_type": "Washing Machines",
    "brand_model": "LG 7kg Front Load",
    "symptoms": "Water not draining, error code OE on display",
    "error_code": "OE"
})
assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
data2 = res2.get_json()
log_id2 = data2.get("diagnostic_log_id")
print(f"Test 2 passed! Serverless log ID: {log_id2}")
assert log_id2 is not None, "Serverless diagnostic log should have been written to /tmp database"

# Verify the row was actually inserted into the serverless database
conn = database.get_db()
row = conn.execute("SELECT * FROM diagnostic_logs WHERE id = ?", (log_id2,)).fetchone()
conn.close()
assert row is not None, "Row must exist in the database"
assert row["appliance_type"] == "Washing Machines"
assert "OE" in row["error_code"]
print(f"Confirmed: Row {log_id2} successfully persisted in {serverless_path}!")

print("\n=== TEST 3: Graceful fallback when DB is artificially locked/read-only ===")
orig_get_db = database.get_db
def mock_readonly_db():
    raise sqlite3.OperationalError("attempt to write a readonly database")

app.view_functions["api_diagnose"].__globals__["get_db"] = mock_readonly_db
res3 = client.post("/api/diagnose", json={
    "appliance_type": "Refrigerators",
    "brand_model": "Samsung 250L",
    "symptoms": "Freezer works but lower fridge is warm",
    "error_code": ""
})
app.view_functions["api_diagnose"].__globals__["get_db"] = orig_get_db

assert res3.status_code == 200, f"Expected 200 with fallback, got {res3.status_code}"
data3 = res3.get_json()
assert data3["diagnostic_log_id"] is None, "Should gracefully return None on read-only failure"
assert len(data3["safe_checks"]) > 0, "Should still return diagnostic safe checks to customer"
print("Test 3 passed! Graceful fallback logged error without 500 crash.")

print("\nALL 3 TESTS PASSED SUCCESSFULLY!")
