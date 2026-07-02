// Standalone OFFLINE verifier for the "On the Record" receipt chain.
// Pure Node ESM. ZERO SDK. ZERO network. Built-in crypto only.
//
// Reads an export JSON file:
//   { salt: <utf8 string>, rows: [ {seq, ts, caller_did, action, outcome, masked_secret, reason, prev_hash, hash}, ... ] }
//
// HASH RULE:
//   hash = hex( SHA256( utf8(salt) || prev_hash_bytes(hexdecoded) || canonical_json(record WITHOUT hash) ) )
//   - canonical_json = deterministic, sorted-keys serialization.
//   - prev_hash for genesis (row 0) = 64 hex zeros.
//   - salt is a PUBLIC per-tenant domain-separation string (not secret), shipped
//     verbatim in the export. The contract hashes its ASCII bytes; we match with
//     Buffer.from(salt, 'utf8') — no hex round-trip.

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const GENESIS_PREV = '0'.repeat(64);

// Deterministic, sorted-keys JSON serialization.
// Recurses into nested objects so key order never affects the hash.
export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalJson).join(',') + ']';
  }
  const keys = Object.keys(value).sort();
  const parts = keys.map((k) => JSON.stringify(k) + ':' + canonicalJson(value[k]));
  return '{' + parts.join(',') + '}';
}

// Recompute the hash for a single row given its prev_hash.
export function computeHash(salt, prevHashHex, row) {
  const { hash, ...recordWithoutHash } = row; // strip hash field
  const h = createHash('sha256');
  h.update(Buffer.from(salt, 'utf8'));
  h.update(Buffer.from(prevHashHex, 'hex'));
  h.update(Buffer.from(canonicalJson(recordWithoutHash), 'utf8'));
  return h.digest('hex');
}

// Verify a chain. Returns { ok: true, n } or { ok: false, brokenSeq }.
export function verifyChain(exportObj) {
  const salt = exportObj.salt;
  const rows = [...exportObj.rows].sort((a, b) => a.seq - b.seq);

  let prevHash = GENESIS_PREV;
  for (const row of rows) {
    // prev_hash must link to the prior row's hash (genesis = 64 zeros).
    if (row.prev_hash !== prevHash) {
      return { ok: false, brokenSeq: row.seq };
    }
    const expected = computeHash(salt, row.prev_hash, row);
    if (expected !== row.hash) {
      return { ok: false, brokenSeq: row.seq };
    }
    prevHash = row.hash;
  }
  return { ok: true, n: rows.length };
}

// Return the chain head (the hash of the max-seq row), or 64 zeros if empty.
export function chainHead(exportObj) {
  const rows = [...exportObj.rows].sort((a, b) => a.seq - b.seq);
  return rows.length === 0 ? GENESIS_PREV : rows[rows.length - 1].hash;
}

// Parse a row's action into a seal descriptor, or null if it isn't a seal.
// A seal row's `action` is the canonical JSON string
// {"type":"seal","peer_did":...,"peer_head":...} and its outcome is "allowed".
export function parseSeal(row) {
  if (row.outcome !== 'allowed') return null;
  let a;
  try { a = JSON.parse(row.action); } catch { return null; }
  if (a && a.type === 'seal' && typeof a.peer_did === 'string' && typeof a.peer_head === 'string') {
    return { peer_did: a.peer_did, peer_head: a.peer_head, row };
  }
  return null;
}

// Parse a row's action into an AUTHORITY-mandate descriptor, or null if it
// isn't one. An authority row's `action` is the canonical JSON string with
// TERSE keys (kept under the contract's ~185-char action cap):
//   {"t":"authority","fn":...,"amt":<amount_cents>,"cap":<cap_cents>,
//    "fns":[...functions],"c":"<16-byte sha256-prefix credential commitment>"}.
// NOTE: this is the ZERO-DEPENDENCY authority LOGIC check — pure JSON parse +
// number/array comparison, NO crypto. The cryptographic SIGNATURE
// re-verification (re-recover the EIP-191 user signer, re-verify the agent
// invocation sig) lives in the SEPARATE authority-verify.mjs, which MAY import
// the SDK's own offline crypto. The core verifier here stays zero-dependency.
export function parseAuthority(row) {
  let a;
  try { a = JSON.parse(row.action); } catch { return null; }
  if (!a || a.t !== 'authority') return null;
  if (typeof a.fn !== 'string') return null;
  if (typeof a.amt !== 'number') return null;
  if (typeof a.cap !== 'number') return null;
  if (!Array.isArray(a.fns)) return null;
  return {
    fn: a.fn,
    amount_cents: a.amt,
    cap_cents: a.cap,
    functions: a.fns,
    commit: typeof a.c === 'string' ? a.c : null,
    row,
  };
}

// ZERO-DEP authority-logic check over an export. For every authority row:
//   in_mandate  <=>  fn IN functions[]  AND  amount_cents <= cap_cents
// We then cross-check the row's recorded outcome against the mandate:
//   - in-mandate row that was DENIED  -> flagged (allowed-but-refused mismatch)
//   - out-of-mandate row that was ALLOWED -> flagged (escaped the mandate!)
// Returns { ok, rows: [{seq, fn, amount_cents, cap_cents, in_mandate,
//   in_functions, within_cap, outcome, consistent}], flagged: [...] }.
// `ok` is true iff every authority row is consistent (no out-of-mandate ALLOW,
// and no in-mandate row that was refused for a non-mandate reason isn't itself
// a contradiction — a refused in-mandate row is allowed: refusal may come from
// an unrelated grant revocation, so we only HARD-flag out-of-mandate ALLOWs).
export function verifyAuthority(exportObj) {
  const rows = [...exportObj.rows].sort((a, b) => a.seq - b.seq);
  const out = [];
  const flagged = [];
  for (const row of rows) {
    const a = parseAuthority(row);
    if (!a) continue;
    const inFunctions = a.functions.includes(a.fn);
    const withinCap = a.amount_cents <= a.cap_cents;
    const inMandate = inFunctions && withinCap;
    // The hard soundness invariant: an OUT-of-mandate action must NOT be
    // recorded as allowed. (An in-mandate action recorded as denied is fine —
    // refusal can come from an orthogonal on-chain grant revocation.)
    const consistent = inMandate || row.outcome !== 'allowed';
    const entry = {
      seq: row.seq, fn: a.fn,
      amount_cents: a.amount_cents, cap_cents: a.cap_cents,
      in_functions: inFunctions, within_cap: withinCap,
      in_mandate: inMandate, outcome: row.outcome, consistent,
    };
    out.push(entry);
    if (!consistent) flagged.push(entry);
  }
  return { ok: flagged.length === 0, rows: out, flagged };
}

// ALL "allowed" seal rows in `exportObj` that anchor `peerDid`, oldest-first.
// We deliberately return EVERY seal, not just the newest: a later weaker or
// forged seal must NOT be allowed to shadow an earlier honest binding.
export function findSealByPeer(exportObj, peerDid) {
  return [...exportObj.rows]
    .sort((a, b) => a.seq - b.seq)
    .map(parseSeal)
    .filter((s) => s && s.peer_did === peerDid);
}

// Find a "seal" receipt anchoring a specific (peerDid, peerHead) pair.
export function findSealForHead(exportObj, peerDid, peerHead) {
  for (const row of exportObj.rows) {
    const s = parseSeal(row);
    if (s && s.peer_did === peerDid && s.peer_head === peerHead) return row;
  }
  return null;
}

// Extract this tenant's own DID from its public salt ("on-the-record:v1:<tidhex>").
export function tenantDidFromSalt(exportObj) {
  const m = /:v1:([0-9a-f]+)$/.exec(exportObj.salt_string || exportObj.salt || '');
  return m ? `did:t3n:${m[1]}` : null;
}

// The set of EVERY hash actually present in `exportObj`'s rows. These are the
// only peer_head values a counter-chain could honestly have sealed: a seal must
// reference a hash that physically exists in the peer's verified chain.
export function sealableHeads(exportObj) {
  return new Set(exportObj.rows.map((r) => r.hash));
}

// Evaluate ONE direction: SEALER's chain sealing the PEER's chain.
//   sealerExport : the chain that holds the seal rows
//   peerExport   : the chain being sealed (already verified CHAIN OK upstream)
//   peerDid      : the DID of the peer chain
// Per-direction state machine (see verifyCrossAnchor doc):
//   - collect ALL seals in sealer naming peer (not just the newest);
//   - for each seal's peer_head:
//       not in peer's real hashes AND not genesis  -> forgery   -> MISMATCH
//       == genesis (64 zeros)                       -> no binding (weak signal)
//       in peer's real hashes, non-genesis          -> real binding
//   - verdict: MISMATCH if any forged head; else OK if >=1 real binding;
//     else WEAK (only genesis seals, or no seals at all).
// Returns { state: 'OK'|'WEAK'|'MISMATCH', reason?, boundHeads:[...] }.
function verifyDirection(sealerExport, peerExport, peerDid) {
  const seals = findSealByPeer(sealerExport, peerDid);
  const realPeerHashes = sealableHeads(peerExport);

  const boundHeads = [];
  for (const seal of seals) {
    const head = seal.peer_head;
    if (head === GENESIS_PREV) {
      continue; // genesis anchor: real seal, but binds nothing
    }
    if (!realPeerHashes.has(head)) {
      // Sealed a non-genesis head that does NOT exist in the peer's verified
      // chain = fabricated or rewritten peer history. This is the forgery catch.
      return {
        state: 'MISMATCH',
        reason: `sealed a peer head not present in the peer chain: peer_head=${head}`,
      };
    }
    boundHeads.push(head); // a real, non-genesis binding
  }

  if (boundHeads.length > 0) return { state: 'OK', boundHeads };
  // No real bindings: either we only saw genesis seals, or no seals at all.
  return {
    state: 'WEAK',
    reason: seals.length === 0
      ? 'no seal anchoring the peer'
      : 'anchored at genesis — no binding',
    boundHeads,
  };
}

// CROSS-ANCHOR check — PROVABLY SOUND 3-state semantics. For EACH direction
// (A's chain sealing B, and B's chain sealing A) we run the per-direction state
// machine above. A direction is:
//   MISMATCH if it sealed a non-genesis peer head that does not exist in the
//            peer's verified chain (fabricated/rewritten history), OR if the
//            peer chain itself is BROKEN (cannot anchor against fiction);
//   OK       if at least one seal binds a REAL non-genesis peer head;
//   WEAK     if every seal anchored only genesis (or there are no seals) —
//            i.e. no cryptographic binding to the peer's content yet.
// Overall:
//   MISMATCH if either direction MISMATCH;
//   else WEAK if either direction WEAK (and neither MISMATCH);
//   else OK (both directions bind real non-genesis peer heads).
// To forge either chain you must also forge the peer's chain (whose real head
// is bound inside yours) — no single tenant can rewrite cross-anchored history.
// Returns { state, reason?, aHead, bHead, aDid, bDid, aDir, bDir }.
export function verifyCrossAnchor(exportA, exportB) {
  const aDid = tenantDidFromSalt(exportA);
  const bDid = tenantDidFromSalt(exportB);

  // Each chain must independently verify CHAIN OK. A BROKEN peer chain means a
  // seal can only ever reference fiction -> MISMATCH for that direction.
  const ca = verifyChain(exportA);
  const cb = verifyChain(exportB);

  const aHead = ca.ok ? chainHead(exportA) : null;
  const bHead = cb.ok ? chainHead(exportB) : null;

  // Direction A->B: A's chain seals B. Requires B to be a verified chain.
  const aDir = cb.ok
    ? verifyDirection(exportA, exportB, bDid)
    : { state: 'MISMATCH', reason: `peer chain B is BROKEN AT seq=${cb.brokenSeq}` };

  // Direction B->A: B's chain seals A. Requires A to be a verified chain.
  const bDir = ca.ok
    ? verifyDirection(exportB, exportA, aDid)
    : { state: 'MISMATCH', reason: `peer chain A is BROKEN AT seq=${ca.brokenSeq}` };

  const base = { aHead, bHead, aDid, bDid, aDir, bDir };

  if (aDir.state === 'MISMATCH') {
    return { state: 'MISMATCH', reason: `A->B ${aDir.reason}`, ...base };
  }
  if (bDir.state === 'MISMATCH') {
    return { state: 'MISMATCH', reason: `B->A ${bDir.reason}`, ...base };
  }
  if (aDir.state === 'WEAK') {
    return { state: 'WEAK', which: 'A->B', reason: `A->B ${aDir.reason}`, ...base };
  }
  if (bDir.state === 'WEAK') {
    return { state: 'WEAK', which: 'B->A', reason: `B->A ${bDir.reason}`, ...base };
  }
  return { state: 'OK', ...base };
}

// CLI entrypoint:
//   node verifier.mjs <export.json>                       # single-chain check
//   node verifier.mjs --cross <export-a.json> <export-b.json>  # cross-anchor check
function main() {
  const argv = process.argv.slice(2);
  if (argv[0] === '--cross') {
    const [, pa, pb] = argv;
    if (!pa || !pb) {
      console.error('usage: node verifier.mjs --cross <export-a.json> <export-b.json>');
      process.exit(2);
    }
    const a = JSON.parse(readFileSync(pa, 'utf8'));
    const b = JSON.parse(readFileSync(pb, 'utf8'));
    const r = verifyCrossAnchor(a, b);
    if (r.state === 'OK') {
      console.log(`CROSS-ANCHOR OK (A head=${r.aHead} bound in B; B head=${r.bHead} bound in A)`);
      process.exit(0);
    } else if (r.state === 'WEAK') {
      // WEAK is an honest "no binding yet", NOT a failure: exit 0 but clearly labeled.
      // r.reason already carries the direction + cause ("A->B anchored at genesis — no binding").
      console.log(`CROSS-ANCHOR WEAK: ${r.reason}`);
      process.exit(0);
    } else {
      console.log(`CROSS-ANCHOR MISMATCH: ${r.reason}`);
      process.exit(1);
    }
  }

  if (argv[0] === '--authority') {
    // ZERO-DEP authority-logic check. Cryptographic sig re-verification is in
    // the SEPARATE authority-verify.mjs (which uses the SDK's own offline crypto).
    const p = argv[1];
    if (!p) {
      console.error('usage: node verifier.mjs --authority <export.json>');
      process.exit(2);
    }
    const exp = JSON.parse(readFileSync(p, 'utf8'));
    const chain = verifyChain(exp);
    if (!chain.ok) {
      console.log(`BROKEN AT seq=${chain.brokenSeq}`);
      process.exit(1);
    }
    const va = verifyAuthority(exp);
    for (const r of va.rows) {
      const tag = r.in_mandate ? 'IN-MANDATE' : 'OUT-OF-MANDATE';
      console.log(
        `seq=${r.seq} fn=${r.fn} amount=${r.amount_cents} cap=${r.cap_cents} ` +
        `[${tag}] outcome=${r.outcome} consistent=${r.consistent}`,
      );
    }
    if (va.ok) {
      console.log(`AUTHORITY OK (${va.rows.length} authority row(s); no out-of-mandate ALLOW)`);
      process.exit(0);
    }
    console.log(`AUTHORITY VIOLATION: ${va.flagged.length} out-of-mandate row(s) recorded as allowed`);
    process.exit(1);
  }

  const path = argv[0];
  if (!path) {
    console.error('usage: node verifier.mjs <export.json> | --cross <a.json> <b.json> | --authority <export.json>');
    process.exit(2);
  }
  const exportObj = JSON.parse(readFileSync(path, 'utf8'));
  const result = verifyChain(exportObj);
  if (result.ok) {
    console.log(`CHAIN OK ${result.n} rows`);
    process.exit(0);
  } else {
    console.log(`BROKEN AT seq=${result.brokenSeq}`);
    process.exit(1);
  }
}

// Run main() only when invoked directly, not when imported by the test.
// Use pathToFileURL so paths with spaces / special chars compare correctly.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
