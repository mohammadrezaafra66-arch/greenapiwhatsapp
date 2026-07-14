"""V16 PART 1 — Supabase connectivity diagnostic CLI.

Run:  docker exec claudegreenapi-backend-1 python /app/scripts/check_supabase.py
Prints PASS/FAIL for TCP reachability, gateway health, and an authenticated REST probe,
with the exact HTTP status + a one-line human explanation. Reuses the project's configured
Supabase URL + anon key (never hardcodes a key).
"""
import asyncio
from app.services.supabase_health import check_supabase


def _pf(ok) -> str:
    return "PASS ✅" if ok else "FAIL ❌"


async def main():
    r = await check_supabase()
    print(f"Supabase URL: {r['url']}")
    print(f"1) TCP reachability     : {_pf(r['tcp']['ok'])}  — {r['tcp']['detail']}")
    ah = r["auth_health"]
    print(f"2) /auth/v1/health      : {_pf(ah['ok'])}  HTTP={ah['http']}  — {ah['detail']}")
    rp = r["rest_products"]
    extra = f" rows={rp['count']}" if rp["count"] is not None else ""
    print(f"3) REST products probe  : {_pf(rp['ok'])}  HTTP={rp['http']}{extra}  — {rp['detail']}")
    print(f"\nOVERALL STATUS: {r['status'].upper()}  (reachable={r['reachable']})")
    if r["status"] == "disconnected":
        print("→ اقدام: لپ‌تاپ Supabase (۱۹۲.۱۶۸.۱۷۰.۱۰) را روشن کنید یا آدرس/کلید آن را بررسی کنید.")


if __name__ == "__main__":
    asyncio.run(main())
