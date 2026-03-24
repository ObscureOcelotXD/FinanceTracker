# Plaid Production Request

Use this document when filling out the Plaid production request form for `FinanceTracker`.

## Recommended Positioning

Describe the app as a read-only personal financial management product in active development for personal use first, not a broad data or AI experiment.

- Primary use case: `Track and manage your finances`
- Secondary use cases if needed: `Invest your money`, `Prepare your taxes`
- Current user scope: my own connected accounts first
- Broader end-user category if asked: individual consumers managing their own finances
- Geography: United States first
- Access model: read-only balances, transactions, and holdings data
- Explicitly excluded: payments, transfers, ACH verification, trading, buying, selling, or movement of funds

## Recommended Product Scope

Request only the products the app uses today:

- `transactions`
- `investments`

Do not request `auth` unless you add an account/routing-number or ACH funding workflow. Asking for narrower, read-only access is more consistent with the current app and easier to justify.

## Suggested Description

```text
FinanceTracker is a read-only personal financial management application that I am building for my own use and active development. It allows me to securely connect my bank and investment accounts in order to view balances, transaction history, investment holdings, cash positions, and overall financial trends in a single dashboard. The product is designed for aggregation, visualization, and analytics, including spending summaries, portfolio visibility, and decision-support insights.

I use Plaid only to access the read-only financial data required to provide these features. The application does not support buying, selling, trading, transfers, payments, ACH verification, or any other movement of funds. I do not store bank credentials, and Plaid access tokens are stored securely server-side and never exposed client-side. Linked items can be removed when no longer needed.

My initial production scope is limited to the Plaid products required for read-only account aggregation and personal financial management. At this stage, I only need production access for my own connected accounts while I continue building and validating the product with real data. I have prepared a public product site, privacy/terms pages, and support information for the review process.
```

## Short Form Answers

Use these if the form asks for shorter fields.

- What does your app do?
  A read-only personal finance dashboard for balances, transaction history, holdings, net worth, and cash-flow analytics.
- Why do you need Plaid?
  To securely connect my own financial institutions and import the read-only data needed for account aggregation and personal financial management while the product is in active development.
- Who is using it right now?
  I am currently using it for my own connected accounts while I build and validate the product.
- How does it help?
  It lets me see balances, transaction history, investment holdings, and trends in one place and use the app's analytics to make better financial decisions.
- What data do you access?
  Account/balance, transactions, and investments data only.
- Do you move money or support trading?
  No. The app is read-only and does not support payments, transfers, ACH verification, trading, or any movement of funds.
- Do you store credentials?
  No. Bank credentials are handled by Plaid Link, not stored by the app.

## Submission Tips

- Tell the truth about your current stage. If this is a solo project, frame it as a real PFM product in active development for personal use first.
- Keep the scope tight. Plaid reviewers are more likely to approve a specific, user-facing workflow than a vague platform pitch.
- Match the request to the app. The production form, GitHub Pages site, Link customization, privacy page, and screenshots should all tell the same story.
