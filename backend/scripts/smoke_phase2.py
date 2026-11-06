"""Live smoke test of the Phase 2 connectivity and intelligence flow.

Run against a live API:  .venv/bin/python scripts/smoke_phase2.py [base_url]

Creates a throwaway account, links the sandbox institution, syncs twice, reviews a
categorisation suggestion, detects recurring items, reads the intelligence
endpoints, asks the assistant, then disconnects and deletes the imported data.
"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010") + "/api/v1"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}{(' -> ' + detail) if detail else ''}")


def main() -> int:
    stamp = uuid.uuid4().hex[:8]
    email = f"smoke-{stamp}@example.com"
    client = httpx.Client(base_url=BASE, timeout=30, follow_redirects=True)

    print("1. account + session")
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "SmokeTestPass123", "display_name": "Smoke Test"},
    )
    check("register", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")
    # Bearer auth is the path the Android client uses and is independent of
    # Secure-cookie behaviour on plain HTTP, so the smoke drives it directly.
    r = client.post("/auth/login", json={"email": email, "password": "SmokeTestPass123"})
    check("login", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    r = client.get("/auth/me")
    check("authenticated session", r.status_code == 200, r.text[:200])

    print("2. providers")
    r = client.get("/connectivity/providers")
    check("providers listed", r.status_code == 200, r.text[:200])
    providers = [p["name"] for p in r.json().get("providers", [])]
    check("sandbox available", "sandbox" in providers, str(providers))

    print("3. link sandbox institution")
    r = client.post("/connectivity/link-token", json={"provider": "sandbox"})
    check("link token", r.status_code == 200, r.text[:200])
    r = client.post(
        "/connectivity/exchange",
        json={"provider": "sandbox", "public_token": "sbx-link-smoke", "consent": True},
    )
    check("exchange", r.status_code == 201, f"{r.status_code} {r.text[:300]}")
    body = r.json()
    link_id = body["link"]["id"]
    imported_accounts = body["accounts"]
    check("accounts imported", len(imported_accounts) >= 2, str(len(imported_accounts)))
    first_sync = body["sync"]
    check("first sync imported", first_sync["added"] > 0, str(first_sync))

    print("4. consent required")
    r = client.post(
        "/connectivity/exchange",
        json={"provider": "sandbox", "public_token": "sbx-link-other", "consent": False},
    )
    check("exchange without consent rejected", r.status_code == 422, str(r.status_code))

    print("5. idempotent re-sync")
    ledger_before = client.get("/transactions", params={"limit": 200}).json()
    count_before = ledger_before["total"]
    r = client.post(f"/connectivity/links/{link_id}/sync")
    check("second sync ok", r.status_code == 200, r.text[:200])
    second = r.json()["sync"]
    check("second sync imported no duplicates", second["added"] == 0, str(second))
    count_after = client.get("/transactions", params={"limit": 200}).json()["total"]
    check("ledger unchanged", count_before == count_after, f"{count_before} -> {count_after}")

    r = client.get("/connectivity/sync-runs")
    check("sync history visible", r.status_code == 200 and len(r.json()["runs"]) >= 2, r.text[:200])

    print("6. pending -> posted reconciliation")
    r = client.get("/transactions", params={"limit": 200, "status": "pending"})
    pending = r.json() if r.status_code == 200 else {}
    check("pending rows exposed", r.status_code == 200, r.text[:300])
    if pending:
        print(f"       pending visible: {pending.get('total')}")

    print("7. categorisation review")
    r = client.get("/suggestions", params={"status": "suggested"})
    check("suggestions listed", r.status_code == 200, r.text[:300])
    suggestions = r.json().get("items", [])
    check("suggestions produced", len(suggestions) > 0, str(len(suggestions)))
    if suggestions:
        target = suggestions[0]
        r = client.post(f"/suggestions/{target['id']}/accept")
        check("accept suggestion", r.status_code == 200, r.text[:300])
        txn = client.get(f"/transactions/{target['transaction_id']}").json()
        check("category written back", txn.get("category_id") == target["category_id"], str(txn.get("category_id")))

    print("8. recurring detection")
    r = client.post("/recurring/detect")
    check("recurring detect runs", r.status_code == 200, r.text[:300])
    r = client.get("/recurring")
    check("recurring listed", r.status_code == 200, r.text[:300])
    series = r.json().get("items", [])
    check("recurring payload has subscription total", "subscription_monthly_total" in r.json(), r.text[:200])
    print(f"       recurring candidates: {len(series)}")

    print("9. personal insights + forecast + shopping")
    r = client.get("/insights/personal")
    check("personal insights", r.status_code == 200, r.text[:300])
    r = client.get("/forecast")
    check("forecast", r.status_code == 200, r.text[:300])
    r = client.get("/shopping/context")
    check("shopping context", r.status_code == 200, r.text[:300])
    categories = client.get("/categories").json()
    expense = next((c for c in categories if c["kind"] == "expense"), None)
    if expense:
        r = client.post(
            "/shopping/check",
            json={"store_name": "Target", "category_id": expense["id"], "expected_amount": "25.00"},
        )
        check("shopping check", r.status_code == 200, r.text[:300])

    print("10. assistant")
    r = client.get("/assistant/status")
    check("assistant status", r.status_code == 200, r.text[:300])
    configured = r.json().get("configured", False)
    r = client.post("/assistant/ask", json={"question": "How much can I safely spend today?"})
    check("assistant responds without crashing", r.status_code in (200, 422, 503), f"{r.status_code} {r.text[:200]}")
    if not configured:
        check(
            "assistant degrades gracefully when unconfigured",
            r.status_code in (200, 422, 503),
            str(r.status_code),
        )
        print(f"       AI configured: {configured}")

    print("11. cross-user isolation")
    other = httpx.Client(base_url=BASE, timeout=30)
    r = other.post(
        "/auth/register",
        json={
            "email": f"smoke-other-{stamp}@example.com",
            "password": "SmokeTestPass123",
            "display_name": "Other User",
        },
    )
    csrf = other.cookies.get("pfc_csrf")
    if csrf:
        other.headers["X-CSRF-Token"] = csrf
    r = other.post("/auth/login", json={"email": f"smoke-other-{stamp}@example.com", "password": "SmokeTestPass123"})
    other.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    r = other.post(f"/connectivity/links/{link_id}/sync")
    check("foreign link not syncable", r.status_code == 404, str(r.status_code))
    r = other.delete(f"/connectivity/links/{link_id}")
    check("foreign link not deletable", r.status_code == 404, str(r.status_code))
    r = other.get("/transactions", params={"limit": 200})
    check("other user has empty ledger", r.json().get("total") == 0, r.text[:200])

    print("12. disconnect + data deletion")
    r = client.delete(f"/connectivity/links/{link_id}", params={"delete_data": True})
    check("disconnect", r.status_code == 200, r.text[:300])
    remaining = client.get("/transactions", params={"limit": 200}).json()
    check("imported transactions removed", remaining["total"] == 0, str(remaining["total"]))
    r = client.get("/connectivity/links")
    links = r.json()["links"]
    check(
        "link retained as disconnected history",
        len(links) == 1 and links[0]["status"] == "disconnected",
        r.text[:200],
    )

    print()
    print(f"{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("failed: " + ", ".join(failures))
        return 1
    print("PHASE 2 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
