import msal, requests, os, sys
from dotenv import load_dotenv
load_dotenv()

TENANT_ID = os.getenv("ENTRA_TENANT_ID")

ROLE_NAMES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
}

app = msal.PublicClientApplication(
    "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
)

flow = app.initiate_device_flow(scopes=["https://management.azure.com/user_impersonation"])
print(flow["message"])
sys.stdout.flush()

result = app.acquire_token_by_device_flow(flow)
if "access_token" not in result:
    print("Auth failed:", result.get("error_description"))
    sys.exit(1)

claims = result.get("id_token_claims", {})
print("\nLogged in as:", claims.get("preferred_username", "unknown"))

token = result["access_token"]
headers = {"Authorization": f"Bearer {token}"}

r = requests.get("https://management.azure.com/subscriptions?api-version=2022-12-01", headers=headers)
subs = r.json().get("value", [])
print(f"Subscriptions accessible: {len(subs)}")

for s in subs:
    sub_id = s["subscriptionId"]
    name = s["displayName"]
    state = s["state"]
    print(f"\n  Subscription: {name} ({sub_id}) — {state}")

    r2 = requests.get(
        f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Authorization/roleAssignments"
        f"?api-version=2022-04-01&$filter=assignedTo()",
        headers=headers,
    )
    if r2.ok:
        roles = r2.json().get("value", [])
        if roles:
            for role in roles:
                role_def_id = role["properties"]["roleDefinitionId"].split("/")[-1]
                role_name = ROLE_NAMES.get(role_def_id, role_def_id)
                scope = role["properties"]["scope"]
                print(f"    Role: {role_name} — scope: {scope}")
        else:
            print("    No role assignments found for this user.")
    else:
        print(f"    Role check error: {r2.status_code} {r2.text[:200]}")
