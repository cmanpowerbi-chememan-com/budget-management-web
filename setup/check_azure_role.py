import msal, requests, os
from dotenv import load_dotenv
load_dotenv()

TENANT_ID = os.getenv("ENTRA_TENANT_ID")
SUB_ID = "b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21"

ROLE_NAMES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
}

app = msal.PublicClientApplication(
    "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
)

# Try silent first
accounts = app.get_accounts()
result = None
if accounts:
    result = app.acquire_token_silent(["https://management.azure.com/user_impersonation"], account=accounts[0])

if not result or "access_token" not in result:
    flow = app.initiate_device_flow(scopes=["https://management.azure.com/user_impersonation"])
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

if "access_token" not in result:
    print("Auth failed:", result.get("error_description"))
    exit(1)

token = result["access_token"]
claims = result.get("id_token_claims", {})
upn = claims.get("preferred_username", "")
oid = claims.get("oid", "")
print(f"User      : {upn}")
print(f"Object ID : {oid}")

headers = {"Authorization": f"Bearer {token}"}

url = (
    f"https://management.azure.com/subscriptions/{SUB_ID}"
    f"/providers/Microsoft.Authorization/roleAssignments"
    f"?api-version=2022-04-01&$filter=principalId eq '{oid}'"
)
r = requests.get(url, headers=headers)
print(f"Role query: {r.status_code}")

if r.ok:
    roles = r.json().get("value", [])
    print(f"Role assignments: {len(roles)}")
    for role in roles:
        role_def_id = role["properties"]["roleDefinitionId"].split("/")[-1]
        role_name = ROLE_NAMES.get(role_def_id, f"Unknown({role_def_id})")
        scope = role["properties"]["scope"]
        print(f"  {role_name}  |  {scope}")
    if not roles:
        print("  → No direct role assignments on this subscription.")
else:
    print("Error:", r.text[:400])
