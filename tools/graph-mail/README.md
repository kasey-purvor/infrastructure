# graph-mail

Read the shared **AI-agent test mailbox** (`agents@thecloudassist.com`) from the
command line, over Microsoft Graph. Built so an agent driving an app under test
can fetch the verification / invite / password-reset email the app just sent and
pull the action link out of it — from any repo, with no browser and no user
session.

Five deliverable addresses all land in the one mailbox:

```
agent001@thecloudassist.com … agent005@thecloudassist.com
```

Plus addressing works too, so `agent001+run42@thecloudassist.com` is a fresh,
never-registered address every time you need one, and this tool folds the
`+tag` away when matching (`--exact` turns that off).

Zero dependencies. Node ≥ 22. One file.

## Install

```bash
cd ~/dev_wsl/infrastructure/tools/graph-mail
mkdir -p ~/.config/graph-mail
cp .env.example ~/.config/graph-mail/env   # fill in tenant, client id, secret; chmod 600
ln -sf "$PWD/graph-mail.mjs" ~/.local/bin/graph-mail   # (infrastructure/bootstrap.sh does this)
graph-mail check --probe <some-other-mailbox@thecloudassist.com>
```

`check` proves the four things worth proving before trusting anything on top:
a token issues, the roles claim is exactly `Mail.Read`, the mailbox reads, and
(with `--probe`) that the credential **cannot** read a different mailbox.

Credentials are read from the first of: `.env` beside the script, then
`~/.config/graph-mail/env`, then the ambient environment. The `~/.config`
location is the one the dev-environment recipe carries between machines.

## The two-step you always do

```bash
WM=$(graph-mail now)                     # 1. watermark BEFORE triggering the send
# ... drive the app: sign up as agent001+run42@thecloudassist.com ...
graph-mail wait --to agent001@thecloudassist.com --after "$WM"   # 2. wait, print body + links
```

`wait` refuses to run without `--after` or `--since`. Without a watermark the
second run of any flow matches the *first* run's email and follows an expired
link, which looks exactly like an application bug. `now` already subtracts 5s
for clock skew.

## Verbs

| Verb | What it does |
|---|---|
| `now` | Print a UTC watermark (ISO 8601, minus 5s skew). |
| `list [--to A] [--since 30m] [--limit N]` | Recent messages across **all folders** (Junk included), newest first. |
| `wait --to A (--after ISO \| --since DUR) [--subject S] [--from F] [--timeout 120] [--poll 5]` | Poll until a matching message arrives; print text body and ranked links. |
| `show <id\|latest> [--to A] [--headers]` | Full message. `--headers` adds the raw internet headers (`Delivered-To`, `Received`). |
| `links <id\|latest> [--to A] [--must-contain X] [--best]` | Just the links. `--best` prints the single top-ranked URL, for piping. |
| `check [--probe other@mailbox]` | Acceptance checks. Exit 2 on any failure. |

All verbs take `--json`. `wait` exits 1 on timeout with a message that says
**which** of three things happened: no mail at all arrived (delivery problem),
mail arrived but none to that address (recipient mismatch), or mail to that
address arrived but the subject/from filter excluded it.

## Links

Every `href` plus bare URLs, HTML-unescaped, deduplicated, then:

- Safe Links wrappers (`*.safelinks.protection.outlook.com/?url=…`) are unwrapped
  **before** ranking, otherwise every link looks identical.
- Noise is demoted: `unsubscribe`, `privacy`, `terms`, `support`, `aka.ms`, social domains.
- Action words are boosted: `verify`, `confirm`, `activate`, `invite`, `accept`,
  `token`, `magic`, `reset`, `validate`, `set-password`.
- A 20+ character opaque path/query segment (the token) is boosted.
- `--must-contain <your-app-domain>` overrides the heuristic when it guesses wrong.

## Things that will bite you

**Defender pre-visits links.** Microsoft Safe Links may fetch a URL to scan it
before you ever open it. If a single-use token reports "already used" on a link
nobody clicked, that is Defender, not the app. The fix is a Safe Links policy
exclusion for this mailbox — Exchange admin work, not code.

**The mailbox only grows.** The credential is `Mail.Read`: nothing here can
delete, move or mark-read. Either accept the accumulation or ask for a
retention policy on the mailbox.

**Locally, you often don't need this.** Apps in dev-stub mode typically log the
link instead of sending. This tool earns its keep against deployed
environments (UAT and the like) where real mail goes out.

**403 right after a permission change** can persist for ~2 hours — Exchange's
permission cache. Still 403 the next day means the grant or an access policy
is wrong.

## Security posture

- The secret lives in `.env` (gitignored) or `GRAPH_CLIENT_SECRET`. It is never
  logged, never printed, never in an error message.
- Client-credentials redemption **cannot** happen from a browser (Entra returns
  `AADSTS9002326` on any request carrying an `Origin` header). This is a
  server-side tool by design.
- Tenant status as of 2026-09-07: the credential is **not** scoped by an
  `ApplicationAccessPolicy` — `check --probe` against another mailbox returned
  200. Until an admin applies one, this credential can read any mailbox in the
  tenant. The tool only ever addresses `$GRAPH_MAILBOX`, but the policy is what
  makes that a guarantee rather than a convention:

  ```powershell
  New-ApplicationAccessPolicy -AccessRight RestrictAccess `
    -AppId <client id> -PolicyScopeGroupId <mail-enabled security group containing agents@> `
    -Description "AI agent mailbox reader: agents@ only"
  Test-ApplicationAccessPolicy -Identity someone.else@thecloudassist.com -AppId <client id>
  ```

- Longer term, swap the shared secret for a certificate credential (or workload
  identity federation if this ever runs in Azure): nothing to leak or rotate.

## Tests

```bash
node test/parsing.test.mjs
```

Covers plus-address folding, recipient matching, Safe Links unwrapping, link
ranking, `--must-contain`, HTML-to-text, and duration parsing. Everything that
touches the network is exercised by `graph-mail check`.
