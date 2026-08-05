# V67.1 — Observation Card Visibility Remediation

**Mode:** Frontend-only Owner Change remediation. Not Phase 8. Not Master Phase 11.

## Root cause (visibility)

The card was correctly mounted in `Dashboard.jsx` but invisible to the owner because:

1. Early card commits were briefly local-only before push.
2. Running `claudegreenapi-frontend-1` was a production nginx image without source bind mount.
3. Active bundle lacked observation card strings until Frontend rebuild.

Route was correct: index `/` renders `Dashboard.jsx`.

## Follow-on Persian owner guide

After visibility was restored, card copy was fully Persianized and daily owner guidance was added. See:

- `docs/v67/113-observation-card-persian-owner-guide.md`
- `docs/v67/111-readonly-observation-card.md`

## Fixes retained

| Fix | Behavior |
|-----|----------|
| Cutover fail-closed | missing/malformed API → `نامشخص` |
| Count label | `تعداد حساب‌های ناوگان` |
| Calendar disclaimer | Persian disclaimer on card |
| Deploy | Frontend-only rebuild/recreate |

## Deployment

```bash
docker compose build frontend
docker compose up -d frontend
```

Do not restart backend, PostgreSQL, Redis, Celery, or Green API for this change.

## Owner access

1. Open `http://<host>:3002/`
2. Menu `داشبورد`
3. Card at top before `داشبورد زنده`
4. Hard refresh (`Ctrl+F5`) if an old bundle remains cached
