# Make Afrakala WhatsApp Sender reachable to everyone on the LAN

MODE: Investigate first, then fix only what's actually needed — do not guess or
reconfigure something that's already correct. Run everything from PowerShell on this
Windows machine (the one running claudegreenapi). No app code changes; this is
infrastructure/networking only. No login/auth page is being added right now (explicit
user decision) — do not add one.

## STEP 1 — Investigate current state (report before changing anything)

1. **Docker port bindings:** show the actual port mappings docker compose is using for the
   frontend and backend services right now (`docker ps` and/or the relevant
   `docker-compose.yml` `ports:` lines). Confirm whether they publish as `0.0.0.0:3002->...`
   / `0.0.0.0:8002->...` (reachable from other machines) or `127.0.0.1:3002->...` (loopback
   only, NOT reachable from the network). Report the exact current binding for both.

2. **Windows Firewall:** list the current inbound rules for TCP ports 3002 and 8002
   (`Get-NetFirewallRule` + `Get-NetFirewallPortFilter` or equivalent). For each rule found,
   report: is it Enabled, what Direction (must be Inbound), and which Profile(s) it applies
   to (Domain / Private / Public — a rule scoped only to "Public" often does NOT apply on a
   typical office/home network profile, which is usually "Private" or "Domain", so a rule
   that looks like it exists could still fail to actually allow the traffic on this
   network). Also check: are there any OTHER ports this app currently needs that a normal
   viewer's browser would hit directly (inspect the actual `docker-compose.yml` for every
   published port across all services, and check if the frontend's built JS references any
   additional port besides 8002 for API calls) — list every port that must be open, not
   just 3002/8002 if more exist.

3. **Is 192.168.170.8 a stable address?** Check whether this machine's IP is statically
   assigned or DHCP-leased (`ipconfig /all` — look at "DHCP Enabled" for the relevant
   adapter). If DHCP, flag clearly that the IP could change after a reboot or lease
   renewal, which would silently break access for everyone else who bookmarked it — this
   matters a lot for a "let the whole office use it" use case.

4. **Quick reachability sanity check from this machine:** confirm the app responds on
   `http://192.168.170.8:3002` and `http://192.168.170.8:8002` (curl/Invoke-WebRequest) —
   this proves the app itself is up, though it doesn't prove another machine on the LAN can
   reach it (that requires testing from a second device, which the user will do after this
   report).

Report all of the above clearly before making any changes.

## STEP 2 — Fix only what's confirmed broken

Based on STEP 1's findings:
- If a Docker port is bound to `127.0.0.1` instead of `0.0.0.0`: fix the `docker-compose.yml`
  port mapping (remove the `127.0.0.1:` prefix so it binds all interfaces) and recreate the
  affected container(s) so the change takes effect.
- If a Windows Firewall inbound rule is missing, disabled, or scoped to the wrong profile
  for ports 3002/8002 (or any other port found necessary in STEP 1.2): create/fix the rule
  so it's Enabled, Direction=Inbound, Protocol=TCP, and applies to whichever profile(s) this
  network's connection actually uses (check with `Get-NetConnectionProfile` to see the
  current profile — Domain/Private/Public — and scope the rule to include it; Private is
  the typical case for an office LAN that isn't domain-joined).
- If the IP is DHCP-assigned (not static): do NOT change network adapter settings without
  being asked (that's a bigger decision involving the router/DHCP scope) — just report this
  clearly as something the user should decide on separately (e.g. setting a static IP or a
  DHCP reservation on the router), since it affects whether "192.168.170.8" stays valid
  long-term for everyone else.
- If everything in STEP 1 was already correct: report that clearly — no changes needed, and
  the app should already be reachable from other devices on the same LAN/WiFi.

## STEP 3 — Final report

- A clear yes/no: is the app now (or already) reachable at `http://192.168.170.8:3002` from
  ANY device on this LAN, based on everything checked/fixed?
- List exactly what was changed (if anything) — the specific docker-compose lines and/or
  the specific firewall rule(s) created/modified.
- Tell the user PLAINLY how to actually verify it works: open a browser on a DIFFERENT
  device connected to the same WiFi/network and go to `http://192.168.170.8:3002` — this is
  the one thing that must be tested from a second device, not from this machine.
- Flag the DHCP/static-IP finding clearly if relevant, as a follow-up decision for the user.
- Note (briefly, once): there is currently no login/password on this app, so anyone who can
  reach this address on the network can view and change everything — this was flagged and
  the user chose to proceed without auth for now; mention that adding a simple login later
  is possible whenever they want it.

Do not touch application code, do not add authentication, do not change anything unrelated
to network reachability.