# Monitoring & Maintenance Checklist

**Established:** 2026-07-31
**Review frequency:** Weekly
**Escalation:** Act on RED items first

> **Baselines below are dated.** An undated count is not a baseline — this session found the V51
> commit's "1394 passing" claim to be unreproducible five days later. Re-measure and update the
> date whenever the expected value legitimately changes.

---

## Daily

### Test suite

```powershell
docker-compose exec -T backend python -m pytest tests/ -q --tb=no
```

| | |
|---|---|
| Expected (as of 2026-07-31, after the V45/V49 fix) | `1403 passed, 0 failed` |
| Known failures | **None.** `main` is green |
| Alert if | Any failure at all, **or** the collected count changes |

`main` is now a valid deployment gate. It was not before: until 2026-07-31 the suite reported
`1401 passed / 2 failed`, and those 2 failures were data-dependent — they could have flipped to
passing on their own without anything being fixed. Both are now genuinely fixed; see
`V45_V49_ROOT_CAUSE_AND_FIX.md`.

**Verify a green run more than once.** Both failures were tie-break dependent, so a single green
run does not distinguish a healthy suite from a lucky one. The fix was accepted only after three
consecutive clean runs.

### Container health

```powershell
docker ps --filter "name=claudegreenapi" --format "{{.Names}}  {{.Status}}"
```

Expected: 7 containers up — `backend`, `frontend`, `db`, `redis`, `worker-general`,
`worker-webhooks`, `beat`. Alert on any restart loop.

### Frontend availability

```powershell
(Invoke-WebRequest -Uri "http://192.168.170.8:3002" -UseBasicParsing).StatusCode
```

Expected: `200`.

⚠️ **HTTP 200 does not prove the deployed code is current.** The frontend container has **no volume
mount** — it serves whatever was baked into its image. This session found it serving a build 20
hours older than the rebrand commit while returning a healthy 200. To verify content:

```powershell
$wc = New-Object System.Net.WebClient; $wc.Encoding = [System.Text.Encoding]::UTF8
[regex]::Match($wc.DownloadString("http://localhost:3002"), '<title>(.*?)</title>').Groups[1].Value
```

Compare against `git show HEAD:frontend/index.html`. After any frontend change:
`docker compose up -d --build frontend`.

### Scheduled story fetch

```powershell
docker logs claudegreenapi-beat-1 --tail 200 | Select-String "fetch-incoming-stories"
```

Expected: dispatched every 1800s, and `succeeded` in the worker log. Alert on repeated failures.

---

## Weekly

- Branch sync — `git rev-list --left-right --count origin/main...main` should be `0 0`
- **`git fetch` before any remote operation.** This repo saw concurrent pushes from another process
  three times in a single session
- Database backup exists (`backups/`)
- Green API token validity
- `.env` completeness — `GEMINI_API_KEY` and `DEEPSEEK_API_KEY` are currently **empty**, so V42's
  self-healing model discovery has no provider to fail over to
- Untracked file review — `git status --porcelain | Select-String "^\?\?"`. Anything irreplaceable
  should be committed, not left loose

---

## Monthly

- Dependency updates
- Log rotation
- Security audit
- Re-run `python deep_audit.py --output audit.md` and check whether new versions shipped without a
  spec

---

## Escalation matrix

| Issue | Severity | Respond within |
|---|---|---|
| Frontend down (non-200) | RED | 15 min |
| Container restart loop | RED | 30 min |
| A *different* test fails than the 2 known | RED | 1 h |
| Story fetch failing repeatedly | ORANGE | 2 h |
| Green API token expired | ORANGE | 2 h |
| Backup missing | YELLOW | 24 h |
| Untracked irreplaceable file found | YELLOW | 24 h |

---

## Before running any destructive command

- **`git clean -fd`** — run `git clean -nd` first and read the list. It deletes untracked files
  with no reflog and no recovery. It was proposed this session while 13 irreplaceable specs were
  untracked.
- **`git push --force`** — use `--force-with-lease`. Bare `--force` silently discards an unseen push.
- **`git add -A`** — stage by path. An `-A` sweep produced a 50-file commit here whose message
  described a single one-line fix.
- **Any master prompt** — check its declared baseline against HEAD before executing.
  `V16_MASTER_PROMPT.md` declares "V15, 237 tests"; the project is at V52 with 1403.
