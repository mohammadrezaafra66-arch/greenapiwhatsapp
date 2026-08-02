// V60 STEP 1 (PART C-3) — turn the per-account daily cap into a sentence the operator can act on.
//
// The cap that actually governs a campaign is per ACCOUNT, not per campaign: an account under
// 10 days old is hard-capped at 5 messages/day regardless of the 50 shown in its settings. That
// surprises people — they set `daily_limit = 50`, see 5 messages go out, and assume something
// broke. Worse, they under-estimate how long a list will take and start adding accounts, which is
// exactly the pattern that got a number suspended.
//
// Pure functions so the arithmetic is unit-tested and the page stays a thin renderer.

// Mirrors app/models/account.py::computed_daily_limit — the young-account hard cap.
export const YOUNG_ACCOUNT_DAYS = 10;
export const YOUNG_ACCOUNT_CAP = 5;

/** The real per-day ceiling for one account row from /accounts/overview. */
/** Coerce to a finite number, keeping 0 as 0 (`|| fallback` would swallow it). */
function num(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function accountDailyCap(row) {
  if (!row) return 0;
  // GET /accounts/ already returns the authoritative value as `daily_limit`
  // (it is `Account.computed_daily_limit`). Prefer it so the page can never disagree with the
  // backend; the local formula below is only a fallback for payloads that omit it.
  if (row.daily_limit !== undefined && row.daily_limit !== null) {
    return Math.max(0, num(row.daily_limit, 0));
  }
  // A configured maximum of 0 means "this account sends nothing" and must survive as 0.
  const absolute = num(row.max_daily_absolute ?? 200, 200);
  const days = num(row.days_active ?? 0, 0);
  if (days < YOUNG_ACCOUNT_DAYS) return Math.min(YOUNG_ACCOUNT_CAP, absolute);
  const base = Math.min(days, 10);
  const incoming = Math.min(
    Math.floor(num(row.received_yesterday ?? 0, 0) * num(row.incoming_ratio_multiplier ?? 0.5, 0.5)),
    20);
  const replies = Math.min(num(row.quick_replies_yesterday ?? 0, 0) * 5, 50);
  return Math.min(base + incoming + replies, absolute);
}

/**
 * Capacity for a chosen set of accounts against a contact count.
 * Returns { accounts, perAccount:[{id,name,cap,young}], perDay, days, anyYoung }.
 * `days` is null when perDay is 0 — "never at this rate" must not render as Infinity.
 */
export function campaignCapacity(rows, contactCount) {
  const list = (rows || []).map((r) => ({
    id: r.instance_id || r.account_id || r.id,
    name: r.phone || r.name || r.instance_id,
    cap: accountDailyCap(r),
    young: num(r.days_active ?? 0, 0) < YOUNG_ACCOUNT_DAYS,
  }));
  const perDay = list.reduce((s, a) => s + a.cap, 0);
  const n = Math.max(0, num(contactCount, 0));
  return {
    accounts: list.length,
    perAccount: list,
    perDay,
    days: perDay > 0 && n > 0 ? Math.ceil(n / perDay) : null,
    anyYoung: list.some((a) => a.young),
  };
}

/** The Persian sentence shown under the account picker. */
export function capacitySentence(cap, contactCount) {
  if (!cap || cap.accounts === 0) return "هنوز حسابی انتخاب نشده است.";
  const n = Number(contactCount) || 0;
  const head = `با ${cap.accounts} حساب، حداکثر ${cap.perDay} پیام در روز`;
  if (!n) return `${head}.`;
  if (cap.days === null) return `${head} — با این وضعیت ارسال انجام نمی‌شود.`;
  return `${head} — ${n} مخاطب در حدود ${cap.days} روز تمام می‌شود.`;
}

/**
 * V60 STEP 2 — an account that is ALSO an active Team Collaboration sender does not get a
 * fresh allowance for the campaign: both roles draw on the SAME per-account daily cap. Showing
 * the raw cap here would over-promise, and the operator would plan a list that quietly starves
 * the warm-up (or the other way round).
 *
 * `tcReserved` is how many of that account's daily messages the warm-up is expected to take.
 * Returns the same shape as campaignCapacity, with `perDay` reduced to what is genuinely left.
 */
export function capacityWithTeamCollab(rows, contactCount, tcSenderIds = [], tcReserved = 1) {
  const reserved = new Set((tcSenderIds || []).map(String));
  const list = (rows || []).map((r) => {
    const id = r.instance_id || r.account_id || r.id;
    const cap = accountDailyCap(r);
    const isTc = reserved.has(String(id)) || reserved.has(String(r.instance_id));
    const taken = isTc ? Math.min(cap, Math.max(0, num(tcReserved, 1))) : 0;
    return {
      id,
      name: r.phone || r.name || r.instance_id,
      cap,
      remaining: Math.max(0, cap - taken),
      young: num(r.days_active ?? 0, 0) < YOUNG_ACCOUNT_DAYS,
      teamCollab: isTc,
    };
  });
  const perDay = list.reduce((s, a) => s + a.remaining, 0);
  const n = Math.max(0, num(contactCount, 0));
  return {
    accounts: list.length,
    perAccount: list,
    perDay,
    days: perDay > 0 && n > 0 ? Math.ceil(n / perDay) : null,
    anyYoung: list.some((a) => a.young),
    anyTeamCollab: list.some((a) => a.teamCollab),
  };
}

/** Warning naming the accounts whose daily capacity is shared with Team Collaboration. */
export function teamCollabNotice(cap) {
  if (!cap || !cap.anyTeamCollab) return "";
  const shared = cap.perAccount.filter((a) => a.teamCollab);
  const detail = shared.map((a) => `${a.name} (${a.remaining} از ${a.cap})`).join(" · ");
  return `${shared.length} حساب هم‌زمان در «همکاری تیمی» فعال است و ظرفیت روزانه‌اش بین `
    + `کمپین و گرم‌سازی تقسیم می‌شود. ظرفیت باقی‌مانده برای کمپین: ${detail}`;
}

/** Warning shown when any chosen account is still inside its 10-day high-risk window. */
export function youngAccountNotice(cap) {
  if (!cap || !cap.anyYoung) return "";
  const young = cap.perAccount.filter((a) => a.young).length;
  return `${young} حساب هنوز زیر ${YOUNG_ACCOUNT_DAYS} روز است و به‌طور خودکار به `
    + `${YOUNG_ACCOUNT_CAP} پیام در روز محدود می‌شود — این محدودیت ایمنی است و با تغییر `
    + `«سقف روزانه» برداشته نمی‌شود.`;
}
