from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app)

print("1. Testing /api/v1/health")
response = client.get("/api/v1/health")
print("Status:", response.status_code)
print("Response:", response.json())
print("-" * 40)

print("2. Testing /api/v1/testcases/Case0")
response = client.get("/api/v1/testcases/Case0")
print("Status:", response.status_code)
if response.status_code == 200:
    data = response.json()
    print("Warehouse keys:", data.keys())
    print("Successfully loaded testcase!")
    
    print("\n3. Testing /api/v1/solve/json")
    # Submit the testcase to the solver
    solve_resp = client.post("/api/v1/solve/json", json=data)
    print("Status:", solve_resp.status_code)
    print("Response:", solve_resp.json())
else:
    print("Failed to load testcase:", response.text)
