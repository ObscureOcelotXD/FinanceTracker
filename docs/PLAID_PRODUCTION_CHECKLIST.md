# Plaid Production Checklist

Use this checklist to finish the non-code parts of Plaid production approval.

## 1. App Profile And Public Artifacts

Complete the Plaid app/company profile with information that matches the app and repository:

- App name: `FinanceTracker`
- App URL: your public landing page or deployed URL
- Support email: use the same email shown on `/support`
- Product description: use the wording in `docs/PLAID_PRODUCTION_REQUEST.md`
- Branding: add a logo if you have one
- Product framing: read-only personal finance dashboard, not payments or trading

Before taking screenshots, set these values in `.env`:

- `PUBLIC_APP_NAME`
- `PUBLIC_APP_URL`
- `PUBLIC_SUPPORT_EMAIL`
- `PUBLIC_OWNER_NAME`

Then capture:

1. `/`
2. `/privacy`
3. `/terms`
4. `/support`

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

The app now reads `PLAID_PRODUCTS` and `PLAID_COUNTRY_CODES` from the environment so your approval request and runtime config can stay aligned.

## 4. Security Questionnaire Prep

Answer conservatively and truthfully. Plaid is generally looking for a credible baseline, not enterprise theater.

Suggested answer themes:

- End-user data is stored server-side, not in the browser.
- Plaid access tokens are not exposed client-side.
- Secrets are managed through environment variables or Infisical CLI injection.
- Access to production credentials is limited to authorized development use.
- Data is transmitted over HTTPS in production.
- Users can disconnect accounts and linked items can be removed when no longer needed.
- The product uses financial data only for user-requested personal finance features and does not sell or rent user data.
- The product is read-only and is not used for money movement, payment initiation, account funding, or execution of trades.

## 5. Submission Package

When you submit the request, include or be ready with:

- Exact app description from `docs/PLAID_PRODUCTION_REQUEST.md`
- Product list: `transactions`, `investments`
- DTM use case: `Track and manage your finances`
- Support email and public URL
- Screenshots of the approval-facing routes
- A clear note that the app is read-only and does not buy, sell, trade, transfer, or move funds

## 6. If Plaid Still Limits Access

Ask support which of these is blocking broader access:

- missing business/profile information
- missing or insufficient security questionnaire answers
- OAuth/compliance gating for specific institutions
- lack of public-facing privacy/terms/support documentation

If they want a more formal identity, the cleanest next step is a sole proprietorship or LLC plus a real domain and email.
