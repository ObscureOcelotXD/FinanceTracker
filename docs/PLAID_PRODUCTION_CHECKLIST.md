# Plaid Production Checklist

Use this checklist to finish the non-code parts of Plaid production approval.

## 1. App Profile And Public Artifacts

Complete the Plaid app/company profile with information that matches the app and repository:

- App name: `FinanceTracker`
- App URL: your GitHub Pages landing page or other public landing page
- Support email: use the same email shown on the public support page
- Product description: use the wording in `docs/PLAID_PRODUCTION_REQUEST.md`
- Branding: add a logo if you have one
- Product framing: read-only personal finance dashboard, not payments or trading
- Current usage framing: personal use first, my own connected accounts while the app is in active development

Before taking screenshots, set these values in `.env`:

- `PUBLIC_APP_NAME`
- `PUBLIC_APP_URL`
- `PUBLIC_SUPPORT_EMAIL`
- `PUBLIC_OWNER_NAME`

Then capture from the running app:

1. `/`
2. `/privacy`
3. `/terms`
4. `/support`

Also publish the static public site from `docs/` with GitHub Pages and use that URL in the Plaid profile/request.

## 2. Link Customization / Data Transparency Messaging

In the Plaid Dashboard:

1. Go to Link customization.
2. Open the Data Transparency section.
3. Select `Track and manage your finances`.
4. Optionally add `Invest your money` if you want the investment workflow to be explicit.
5. Publish the customization.
6. If you use a named customization, set `PLAID_LINK_CUSTOMIZATION_NAME` in `.env`.

## 3. Product Scope

Keep the request narrow and consistent across the form, screenshots, and app config:

- Request now: `transactions`, `investments`
- Do not request `auth` unless you add a real account/routing-number workflow
- Make the read-only model explicit: balances, transaction history, and holdings only
- State clearly that the app does not support payments, transfers, ACH verification, or trading
- State clearly that current production access is needed for my own connected accounts first, not a broad onboarding rollout

The app now reads `PLAID_PRODUCTS` and `PLAID_COUNTRY_CODES` from the environment so your approval request and runtime config can stay aligned.

## 4. Security Questionnaire Prep

Answer to match what you **actually** deploy. After the improvements in this repo, you can truthfully claim (when configured): published privacy policy, explicit consent before Plaid Link, HTTPS in production, optional encryption of Plaid access tokens at rest.

### Question-by-question (honest templates—edit for your org)

**1 — Security contact**  
Provide your name, title, and email, or a monitored group alias (e.g. `PUBLIC_SECURITY_EMAIL` / `PUBLIC_SUPPORT_EMAIL` shown on `/privacy`).

**2 — Documented security policy/program**  
If you select **No**, a typical honest explanation: *the project is operated by [individual / small team]; we follow sensible practices (secrets in env, no credentials in git, least-privilege server access) but we do not yet maintain a formal written ISMS or ISO-style policy set. We are committed to addressing gaps Plaid identifies.*

**3 — Access controls to production / sensitive data**  
If checklist options do not fit, explain in free text: *production host and Plaid credentials limited to the operator; SSH or provider console access; secrets via environment variables / secret manager; database and backups not world-readable; no shared production passwords in chat.*

**4 — MFA for consumers before Link**  
If **No**: *the app is currently single-user / low-scale [or personal-use-first]; login MFA is on the roadmap [or: not applicable for localhost-only deployment]. Plaid Link itself enforces the financial institution’s authentication including MFA when the bank requires it.*

**5 — MFA for critical systems storing consumer data**  
If **No** for your **own** admin access: be honest—*operator access to the production server may be password + SSH key only; we will enable MFA on hosting/provider and admin consoles where available.* If you **do** use MFA on cloud console + SSH keys, say so.

**6 — TLS 1.2+ in transit**  
Select **Yes** for production only if users reach the app over **HTTPS** (reverse proxy or PaaS). Enable `TRUST_PROXY_HEADERS=1` and `PUBLIC_REQUIRE_HTTPS=1` behind a TLS terminator. Local `http://127.0.0.1` is development-only.

**7 — Encrypt Plaid consumer data at rest**  
Plaid **access tokens** can be encrypted in SQLite when `PLAID_TOKEN_ENCRYPTION_KEY` is set (Fernet). Transaction/holding rows are still ordinary DB fields—note *full-disk encryption on the server* if applicable. If not fully encrypted, answer partially and describe what **is** protected.

**8 — Vulnerability scans**  
Be accurate: e.g. *dependabot or manual dependency updates; periodic `pip list` / OS patches; no dedicated enterprise VM scanning.* Plaid often accepts honest small-team answers.

**9 — Privacy policy**  
If **Yes**, give your live URL: `{PUBLIC_APP_URL}/privacy` (and the static `docs/` mirror if you use GitHub Pages).

**10 — Consent**  
The home page requires acknowledging the Privacy Policy before **Connect Plaid** is enabled—describe that and Link’s own disclosures.

**11 — Data deletion / retention**  
Point to the Privacy Policy retention section and app features (disconnect / wipe where implemented). Note you review the policy when practices change; align with any jurisdiction you target (e.g. CPRA if California users).

## 5. Submission Package

When you submit the request, include or be ready with:

- Exact app description from `docs/PLAID_PRODUCTION_REQUEST.md`
- Product list: `transactions`, `investments`
- DTM use case: `Track and manage your finances`
- Support email and public GitHub Pages URL
- Screenshots of the approval-facing routes
- A clear note that the app is read-only and does not buy, sell, trade, transfer, or move funds
- A clear note that current production access is for my own accounts first while the app remains in active development

## 6. If Plaid Still Limits Access

Ask support which of these is blocking broader access:

- missing business/profile information
- missing or insufficient security questionnaire answers
- OAuth/compliance gating for specific institutions
- lack of public-facing privacy/terms/support documentation

If they want a more formal identity, the cleanest next step is a sole proprietorship or LLC plus a real domain and email.
