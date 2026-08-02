// V62 — helpers for adding members to a contact group.
//
// The bug this exists to prevent: GET /contacts/ returns an OBJECT
// ({total, skip, limit, contacts: [...]}), not a bare array. The members dialog stored the whole
// response and then branched on `results.length`, which is `undefined` on an object — so
// `undefined === 0` and `undefined > 0` were BOTH false and the dialog rendered nothing at all:
// no results, and not even the "not found" line. Searching looked like it silently did nothing,
// which is why both contact groups ended up with zero members.
//
// Pure functions so the shape handling is unit-tested and can't regress the same way.

/**
 * Pull the contact array out of whatever GET /contacts/ returned.
 * Accepts the paginated object, a bare array, or junk — always returns an array.
 */
export function extractContacts(response) {
  if (Array.isArray(response)) return response;
  if (response && Array.isArray(response.contacts)) return response.contacts;
  return [];
}

/** Total match count when the API reports one, else the length of what we got. */
export function totalMatches(response) {
  if (response && typeof response.total === "number") return response.total;
  return extractContacts(response).length;
}

/**
 * Drop contacts that are already in the group — re-adding them is a no-op server-side, so
 * showing them just makes the operator wonder whether the click worked.
 */
export function excludeExisting(results, members) {
  const have = new Set((members || []).map((m) => String(m.id)));
  return extractContacts(results).filter((c) => !have.has(String(c.id)));
}

/** Toggle one id in a Set-like selection, returning a NEW Set (React state must not mutate). */
export function toggleSelected(selected, id) {
  const next = new Set(selected || []);
  if (next.has(id)) next.delete(id); else next.add(id);
  return next;
}

/** Persian summary under the search box: how many are shown, and how many are already in. */
export function resultsSummary(results, members) {
  const all = extractContacts(results);
  if (all.length === 0) return "مخاطبی یافت نشد.";
  const fresh = excludeExisting(results, members);
  const already = all.length - fresh.length;
  const total = totalMatches(results);
  const head = total > all.length
    ? `${all.length} از ${total} نتیجه`
    : `${all.length} نتیجه`;
  if (fresh.length === 0) return `${head} — همه از قبل عضو این گروه هستند.`;
  return already > 0
    ? `${head} (${already} مورد از قبل عضو است و نمایش داده نمی‌شود)`
    : head;
}
