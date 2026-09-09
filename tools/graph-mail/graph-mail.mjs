#!/usr/bin/env node
/**
 * graph-mail — read the shared AI-agent test mailbox over Microsoft Graph.
 *
 * Purpose: let an agent (or a human) driving an app under test go and fetch the
 * verification / invite / password-reset email that the app just sent to one of
 * the agent00N@thecloudassist.com addresses, and pull the link out of it.
 *
 * Zero dependencies. Node >= 22 (fetch, process.loadEnvFile).
 *
 * Auth is the OAuth2 client-credentials flow (app-only, no user, no browser).
 * The credential carries Mail.Read only, so this tool can never send, move,
 * mark-read or delete — the mailbox accumulates test mail until an admin
 * applies a retention policy.
 *
 * Verbs:
 *   now                       print a UTC watermark to capture BEFORE triggering the send
 *   list   [--to A] [--since 30m|ISO] [--limit N]
 *   wait   --to A (--after ISO | --since DUR) [--subject S] [--from F]
 *          [--timeout 120] [--poll 5] [--must-contain X]
 *   show   <id|latest> [--to A]      full text body + ranked links (+ --headers)
 *   links  <id|latest> [--to A] [--must-contain X]
 *   check  [--probe other@mailbox]   acceptance checks: token, roles, read, blast radius
 *
 * Every verb accepts --json for machine-readable output and --exact to disable
 * plus-address normalisation (agent001+tag@ matching agent001@).
 *
 * Safe Links trap: Microsoft Defender rewrites URLs to *.safelinks.protection.outlook.com
 * (unwrapped here) and may PRE-VISIT them to scan. If a single-use token reports
 * "already used" on a link nobody opened, that is Defender, not the app under test.
 * The fix is a Safe Links policy exclusion for this mailbox (Exchange admin).
 */

import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const HERE = dirname(fileURLToPath(import.meta.url));
// Credential file, first hit wins: .env beside the script (dev convenience),
// then ~/.config/graph-mail/env (the carried location — same convention as
// ~/.config/ticket-panel/env, and outside the git checkout so a provisioned
// machine can restore it before this repo is cloned). Else ambient env.
const ENV_FILES = [
  join(HERE, '.env'),
  join(process.env.XDG_CONFIG_HOME || join(process.env.HOME || '', '.config'), 'graph-mail', 'env'),
];
for (const f of ENV_FILES) {
  try { process.loadEnvFile(f); break; } catch { /* try the next */ }
}

function requireEnv(name) {
  const v = process.env[name];
  if (!v) fail(`${name} is not set (put it in ${join(HERE, '.env')} or the environment)`);
  return v;
}

const TENANT = () => requireEnv('GRAPH_TENANT_ID');
const CLIENT_ID = () => requireEnv('GRAPH_CLIENT_ID');
const CLIENT_SECRET = () => requireEnv('GRAPH_CLIENT_SECRET');
const MAILBOX = () => process.env.GRAPH_MAILBOX || 'agents@thecloudassist.com';
const GRAPH = 'https://graph.microsoft.com/v1.0';

const LIST_SELECT =
  'id,internetMessageId,subject,receivedDateTime,from,toRecipients,ccRecipients,bodyPreview,webLink,parentFolderId';

// ---------------------------------------------------------------------------
// CLI plumbing
// ---------------------------------------------------------------------------

function fail(msg, code = 1) {
  process.stderr.write(`graph-mail: ${msg}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) flags[key] = true;
      else {
        flags[key] = next;
        i++;
      }
    } else positional.push(a);
  }
  return { flags, positional };
}

/** "30s" | "5m" | "2h" | "1d" -> milliseconds. */
function parseDuration(s) {
  const m = /^(\d+)([smhd])$/.exec(String(s).trim());
  if (!m) return null;
  const n = Number(m[1]);
  return n * { s: 1e3, m: 60e3, h: 3600e3, d: 86400e3 }[m[2]];
}

/** --since 30m | --since 2026-09-07T10:00:00Z | --after ISO  -> Date */
function resolveAfter(flags) {
  if (flags.after) {
    const d = new Date(flags.after);
    if (Number.isNaN(d.getTime())) fail(`--after must be an ISO-8601 timestamp, got "${flags.after}"`);
    return d;
  }
  if (flags.since) {
    const ms = parseDuration(flags.since);
    if (ms !== null) return new Date(Date.now() - ms);
    const d = new Date(flags.since);
    if (Number.isNaN(d.getTime())) fail(`--since must be like 30m / 2h or an ISO timestamp, got "${flags.since}"`);
    return d;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

let cachedToken = null; // { value, expiresAt }

async function getToken(force = false) {
  if (!force && cachedToken && cachedToken.expiresAt - Date.now() > 120e3) return cachedToken.value;
  const body = new URLSearchParams({
    client_id: CLIENT_ID(),
    client_secret: CLIENT_SECRET(),
    scope: 'https://graph.microsoft.com/.default',
    grant_type: 'client_credentials',
  });
  const res = await fetch(`https://login.microsoftonline.com/${TENANT()}/oauth2/v2.0/token`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || !json.access_token) {
    const first = String(json.error_description || '').split('\n')[0];
    const codes = (json.error_codes || []).join(',');
    let hint = '';
    if (codes.includes('7000215')) hint = ' — bad client secret (rotated?). Will not resolve by retrying.';
    if (codes.includes('700016')) hint = ' — app registration not found in this tenant.';
    fail(`token request failed: ${json.error || res.status} [${codes}] ${first}${hint}`);
  }
  cachedToken = { value: json.access_token, expiresAt: Date.now() + json.expires_in * 1000 };
  return json.access_token;
}

function decodeJwt(token) {
  const [, payload] = token.split('.');
  return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
}

// ---------------------------------------------------------------------------
// Graph
// ---------------------------------------------------------------------------

async function graphGet(path, { retried401 = false, attempt = 0 } = {}) {
  const token = await getToken();
  const url = path.startsWith('http') ? path : `${GRAPH}/${path}`;
  const res = await fetch(url, { headers: { authorization: `Bearer ${token}` } });

  if (res.status === 401 && !retried401) {
    await getToken(true);
    return graphGet(path, { retried401: true, attempt });
  }
  if (res.status === 429 && attempt < 5) {
    const retryAfter = Number(res.headers.get('retry-after')) || 3 * (attempt + 1);
    process.stderr.write(`graph-mail: throttled (429), waiting ${retryAfter}s\n`);
    await sleep(retryAfter * 1000);
    return graphGet(path, { retried401, attempt: attempt + 1 });
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const code = json.error?.code || res.status;
    const msg = json.error?.message || '';
    let hint = '';
    if (res.status === 403) {
      hint =
        '\n  403 usually means: (a) admin consent not granted (check `graph-mail check` roles), or' +
        '\n  (b) an ApplicationAccessPolicy excludes this mailbox, or (c) a grant made in the last ~2h' +
        '\n  has not propagated through Exchange’s permission cache yet — wait and retry.';
    }
    const err = new Error(`Graph ${res.status} ${code}: ${msg}${hint}`);
    err.status = res.status;
    err.code = code;
    throw err;
  }
  return json;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

async function listMessages({ after, limit = 50 }) {
  const params = new URLSearchParams({
    $top: String(Math.min(limit, 100)),
    $orderby: 'receivedDateTime desc',
    $select: LIST_SELECT,
  });
  if (after) params.set('$filter', `receivedDateTime ge ${after.toISOString().replace(/\.\d{3}Z$/, 'Z')}`);
  // /users/{mbx}/messages spans ALL folders — Junk Email included, deliberately.
  const json = await graphGet(`users/${encodeURIComponent(MAILBOX())}/messages?${params}`);
  return json.value || [];
}

async function fetchBody(id) {
  const json = await graphGet(
    `users/${encodeURIComponent(MAILBOX())}/messages/${encodeURIComponent(id)}?$select=${LIST_SELECT},body`,
  );
  return json;
}

async function fetchHeaders(id) {
  const json = await graphGet(
    `users/${encodeURIComponent(MAILBOX())}/messages/${encodeURIComponent(id)}?$select=internetMessageHeaders`,
  );
  return json.internetMessageHeaders || [];
}

/** Locate a message by Graph id, internetMessageId, or the literal "latest". */
async function resolveMessage(ref, flags) {
  if (!ref) fail('expected a message id, an <internetMessageId>, or "latest"');
  if (ref === 'latest') {
    const msgs = await listMessages({ after: resolveAfter(flags), limit: 50 });
    const filtered = flags.to ? msgs.filter((m) => recipientMatches(m, flags.to, !flags.exact)) : msgs;
    if (!filtered.length) fail('no messages found' + (flags.to ? ` addressed to ${flags.to}` : ''));
    return filtered[0];
  }
  if (ref.startsWith('<') && ref.endsWith('>')) {
    const msgs = await listMessages({ after: null, limit: 100 });
    const hit = msgs.find((m) => m.internetMessageId === ref);
    if (!hit) fail(`no message with internetMessageId ${ref} in the most recent 100`);
    return hit;
  }
  return { id: ref };
}

// ---------------------------------------------------------------------------
// Matching
// ---------------------------------------------------------------------------

/** agent001+run42@X -> agent001@x ; lower-cased. */
function normaliseAddress(addr, stripPlus = true) {
  const a = String(addr || '')
    .trim()
    .toLowerCase();
  if (!stripPlus) return a;
  const at = a.indexOf('@');
  if (at < 0) return a;
  const local = a.slice(0, at).replace(/\+.*$/, '');
  return `${local}${a.slice(at)}`;
}

function recipientAddresses(msg) {
  return [...(msg.toRecipients || []), ...(msg.ccRecipients || [])]
    .map((r) => r.emailAddress?.address)
    .filter(Boolean);
}

function recipientMatches(msg, to, stripPlus) {
  const want = normaliseAddress(to, stripPlus);
  return recipientAddresses(msg).some((a) => normaliseAddress(a, stripPlus) === want);
}

function textMatches(haystack, needle) {
  if (!needle) return true;
  return String(haystack || '')
    .toLowerCase()
    .includes(String(needle).toLowerCase());
}

// ---------------------------------------------------------------------------
// Body & links
// ---------------------------------------------------------------------------

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#39': "'" };
function htmlUnescape(s) {
  return String(s).replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    const k = e.toLowerCase();
    if (k in ENTITIES) return ENTITIES[k];
    if (k.startsWith('#x')) return String.fromCodePoint(parseInt(k.slice(2), 16));
    if (k.startsWith('#')) return String.fromCodePoint(parseInt(k.slice(1), 10));
    return m;
  });
}

function htmlToText(html) {
  return htmlUnescape(
    String(html)
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<head[\s\S]*?<\/head>/gi, '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|tr|li|h[1-6]|table)>/gi, '\n')
      .replace(/<a\s[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, (m, href, text) => {
        const t = text.replace(/<[^>]+>/g, '').trim();
        return t ? `${t} [${href}]` : `[${href}]`;
      })
      .replace(/<[^>]+>/g, ''),
  )
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function unwrapSafeLink(url) {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith('.safelinks.protection.outlook.com')) {
      const inner = u.searchParams.get('url');
      if (inner) return inner;
    }
  } catch {
    /* not a URL */
  }
  return url;
}

const DROP = /unsubscribe|privacy|terms|support|aka\.ms|facebook\.com|twitter\.com|x\.com|linkedin\.com|instagram\.com|youtube\.com|w3\.org|schemas\.microsoft\.com/i;
const BOOST = /verify|confirm|activate|activation|invite|accept|token|magic|reset|validate|set-password|setpassword/i;
const OPAQUE = /[A-Za-z0-9_-]{20,}/;

function extractLinks(html, { mustContain } = {}) {
  const raw = [];
  for (const m of String(html).matchAll(/href\s*=\s*["']([^"']+)["']/gi)) raw.push(m[1]);
  for (const m of String(html).matchAll(/https?:\/\/[^\s"'<>)]+/gi)) raw.push(m[0]);
  const seen = new Set();
  const out = [];
  for (const r of raw) {
    let url = unwrapSafeLink(htmlUnescape(r));
    url = url.replace(/[.,;:]+$/, '');
    if (!/^https?:\/\//i.test(url)) continue;
    if (seen.has(url)) continue;
    seen.add(url);
    let score = 0;
    let dropped = false;
    if (DROP.test(url)) {
      score -= 10;
      dropped = true;
    }
    if (BOOST.test(url)) score += 5;
    try {
      const u = new URL(url);
      if (OPAQUE.test(u.pathname + u.search)) score += 3;
    } catch {
      /* ignore */
    }
    if (mustContain) {
      if (url.toLowerCase().includes(String(mustContain).toLowerCase())) score += 100;
      else score -= 100;
    }
    out.push({ url, score, dropped });
  }
  return out.sort((a, b) => b.score - a.score);
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

function fmtSummary(m) {
  const from = m.from?.emailAddress?.address || '?';
  const to = recipientAddresses(m).join(', ');
  return [
    `id:        ${m.id}`,
    `msgid:     ${m.internetMessageId || ''}`,
    `received:  ${m.receivedDateTime}`,
    `from:      ${from}`,
    `to:        ${to}`,
    `subject:   ${m.subject}`,
  ].join('\n');
}

function printMessageFull(m, flags) {
  const html = m.body?.content || '';
  const isHtml = (m.body?.contentType || '').toLowerCase() === 'html';
  const text = isHtml ? htmlToText(html) : html;
  const links = extractLinks(html, { mustContain: flags['must-contain'] });
  if (flags.json) {
    console.log(JSON.stringify({ ...m, body: undefined, text, links }, null, 2));
    return;
  }
  console.log(fmtSummary(m));
  console.log('\n--- body (text) ---');
  console.log(text);
  console.log('\n--- links (ranked; * = best guess) ---');
  printLinks(links);
}

function printLinks(links) {
  if (!links.length) {
    console.log('(no links)');
    return;
  }
  links.forEach((l, i) => {
    const mark = i === 0 && l.score > 0 ? '*' : ' ';
    console.log(`${mark} [${String(l.score).padStart(4)}] ${l.url}${l.dropped ? '   (noise)' : ''}`);
  });
}

// ---------------------------------------------------------------------------
// Verbs
// ---------------------------------------------------------------------------

async function cmdNow() {
  // Subtract 5s for clock skew between this host and Exchange.
  console.log(new Date(Date.now() - 5000).toISOString().replace(/\.\d{3}Z$/, 'Z'));
}

async function cmdList(flags) {
  const after = resolveAfter(flags);
  const limit = Number(flags.limit || 20);
  let msgs = await listMessages({ after, limit: Math.max(limit, 50) });
  if (flags.to) msgs = msgs.filter((m) => recipientMatches(m, flags.to, !flags.exact));
  msgs = msgs.slice(0, limit);
  if (flags.json) return console.log(JSON.stringify(msgs, null, 2));
  if (!msgs.length) {
    console.log(
      `no messages in ${MAILBOX()}` +
        (after ? ` since ${after.toISOString()}` : '') +
        (flags.to ? ` addressed to ${flags.to}` : ''),
    );
    return;
  }
  for (const m of msgs) {
    console.log(fmtSummary(m));
    if (m.bodyPreview) console.log(`preview:   ${m.bodyPreview.replace(/\s+/g, ' ').slice(0, 160)}`);
    console.log('');
  }
}

async function cmdWait(flags) {
  if (!flags.to) fail('wait needs --to <address>');
  const after = resolveAfter(flags);
  if (!after) {
    fail(
      'wait needs a watermark: --after <ISO from `graph-mail now`> or --since <30s|5m>.\n' +
        '  Without one, a second run matches the previous run’s email and follows a dead link.',
    );
  }
  const timeoutMs = Number(flags.timeout || 120) * 1000;
  const pollMs = Math.max(3, Number(flags.poll || 5)) * 1000;
  const deadline = Date.now() + timeoutMs;
  const stripPlus = !flags.exact;

  process.stderr.write(
    `graph-mail: waiting up to ${timeoutMs / 1000}s for mail to ${flags.to} received after ${after.toISOString()}` +
      (flags.subject ? ` with subject containing "${flags.subject}"` : '') +
      (flags.from ? ` from "${flags.from}"` : '') +
      '\n',
  );

  let sawAny = 0;
  let sawToAddress = 0;
  while (true) {
    const msgs = await listMessages({ after, limit: 50 });
    sawAny = msgs.length;
    const toMatches = msgs.filter((m) => recipientMatches(m, flags.to, stripPlus));
    sawToAddress = toMatches.length;
    const hit = toMatches.find(
      (m) => textMatches(m.subject, flags.subject) && textMatches(m.from?.emailAddress?.address, flags.from),
    );
    if (hit) {
      const full = await fetchBody(hit.id);
      printMessageFull(full, flags);
      return;
    }
    if (Date.now() + pollMs > deadline) break;
    await sleep(pollMs);
  }

  // Distinguish the two failure modes — they point at different bugs.
  if (sawAny === 0) {
    fail(
      `timed out: NO mail at all arrived in ${MAILBOX()} after ${after.toISOString()}.\n` +
        '  → delivery problem (app never sent, wrong address, SES/Cognito sandbox, or Defender quarantine).',
    );
  }
  if (sawToAddress === 0) {
    fail(
      `timed out: ${sawAny} message(s) arrived after the watermark but NONE addressed to ${flags.to}.\n` +
        '  → recipient mismatch. Run `graph-mail list --since 10m` to see who they were for,' +
        '\n    or `graph-mail show latest --headers` to check Delivered-To (BCC / list delivery).',
    );
  }
  fail(
    `timed out: ${sawToAddress} message(s) to ${flags.to} arrived but none matched` +
      (flags.subject ? ` subject~"${flags.subject}"` : '') +
      (flags.from ? ` from~"${flags.from}"` : '') +
      '. Loosen the filter or `graph-mail list --to ...`.',
  );
}

async function cmdShow(ref, flags) {
  const m = await resolveMessage(ref, flags);
  const full = await fetchBody(m.id);
  printMessageFull(full, flags);
  if (flags.headers) {
    const headers = await fetchHeaders(m.id);
    console.log('\n--- internet headers ---');
    for (const h of headers) console.log(`${h.name}: ${h.value}`);
  }
}

async function cmdLinks(ref, flags) {
  const m = await resolveMessage(ref, flags);
  const full = await fetchBody(m.id);
  const links = extractLinks(full.body?.content || '', { mustContain: flags['must-contain'] });
  if (flags.json) return console.log(JSON.stringify(links, null, 2));
  if (flags.best) {
    if (!links.length || links[0].score <= 0) fail('no plausible action link found');
    console.log(links[0].url);
    return;
  }
  printLinks(links);
}

async function cmdCheck(flags) {
  const results = [];
  const ok = (name, detail) => results.push({ name, ok: true, detail });
  const bad = (name, detail) => results.push({ name, ok: false, detail });

  // 1. token
  let token;
  try {
    token = await getToken(true);
    ok('token issues', `expires_in ~${Math.round((cachedToken.expiresAt - Date.now()) / 1000)}s`);
  } catch (e) {
    bad('token issues', e.message);
    return report(results, flags);
  }

  // 2. roles
  const claims = decodeJwt(token);
  const roles = claims.roles || [];
  if (!roles.length) bad('roles', 'EMPTY — admin consent was never granted; every Graph call will 403');
  else if (roles.some((r) => /ReadWrite|Send|Full/i.test(r)))
    bad('roles', `${roles.join(', ')} — NOT read-only, contrary to expectation`);
  else ok('roles', `${roles.join(', ')} (app: ${claims.app_displayname || '?'})`);

  // 3. mailbox reads
  try {
    const msgs = await listMessages({ limit: 5 });
    ok('mailbox reads', `${MAILBOX()} → 200, ${msgs.length} message(s) in top 5`);
  } catch (e) {
    bad('mailbox reads', e.message);
  }

  // 4. blast radius
  const probe = flags.probe;
  if (probe) {
    try {
      await graphGet(`users/${encodeURIComponent(probe)}/messages?$top=1&$select=subject`);
      bad(
        'blast radius',
        `${probe} → 200. The credential can read OTHER mailboxes: no ApplicationAccessPolicy scopes it to ${MAILBOX()}. ` +
          'Ask an Exchange admin for New-ApplicationAccessPolicy -AccessRight RestrictAccess -AppId <client id> -PolicyScopeGroupId <mail-enabled group containing the mailbox>.',
      );
    } catch (e) {
      if (e.status === 403 || e.status === 404) ok('blast radius', `${probe} → ${e.status} (scoped correctly)`);
      else bad('blast radius', `${probe} → unexpected: ${e.message}`);
    }
  } else {
    results.push({ name: 'blast radius', ok: null, detail: 'skipped — pass --probe <other@mailbox> to test' });
  }

  return report(results, flags);
}

function report(results, flags) {
  if (flags.json) return console.log(JSON.stringify(results, null, 2));
  for (const r of results) {
    const mark = r.ok === null ? '·' : r.ok ? '✓' : '✗';
    console.log(`${mark} ${r.name.padEnd(16)} ${r.detail}`);
  }
  if (results.some((r) => r.ok === false)) process.exit(2);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const USAGE = `usage:
  graph-mail now
  graph-mail list  [--to ADDR] [--since 30m|ISO] [--limit N] [--json]
  graph-mail wait  --to ADDR (--after ISO | --since DUR) [--subject S] [--from F]
                   [--timeout 120] [--poll 5] [--must-contain X] [--json]
  graph-mail show  <id|latest> [--to ADDR] [--since DUR] [--headers] [--must-contain X] [--json]
  graph-mail links <id|latest> [--to ADDR] [--since DUR] [--must-contain X] [--best] [--json]
  graph-mail check [--probe other@mailbox] [--json]

  --exact   disable plus-address folding (agent001+tag@ ≠ agent001@)
  mailbox:  $GRAPH_MAILBOX (default agents@thecloudassist.com)`;

async function main() {
  const { flags, positional } = parseArgs(process.argv.slice(2));
  const [verb, ...rest] = positional;
  try {
    switch (verb) {
      case 'now':
        return await cmdNow();
      case 'list':
        return await cmdList(flags);
      case 'wait':
        return await cmdWait(flags);
      case 'show':
        return await cmdShow(rest[0], flags);
      case 'links':
        return await cmdLinks(rest[0], flags);
      case 'check':
        return await cmdCheck(flags);
      case undefined:
      case 'help':
      case '--help':
        console.log(USAGE);
        return;
      default:
        fail(`unknown verb "${verb}"\n${USAGE}`);
    }
  } catch (e) {
    fail(e.message);
  }
}

export { extractLinks, htmlToText, normaliseAddress, recipientMatches, unwrapSafeLink, parseDuration };

import { realpathSync } from 'node:fs';
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) main();
