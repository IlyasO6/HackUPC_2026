from fastapi.testclient import TestClient
from main import app

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

    print("\n3. Testing /api/v1/optimise")
    optimise_resp = client.post("/api/v1/optimise", json=data)
    print("Status:", optimise_resp.status_code)
    if optimise_resp.status_code == 200:
        result = optimise_resp.json()
        print("Session:", result["session_id"])
        print("Q:", result["Q"])
        print("Bay count:", result["bay_count"])
else:
    print("Failed to load testcase:", response.text)
