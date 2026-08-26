from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["legal"])


LEGAL_STYLE = """
body {
    color: #17202a;
    font-family: Arial, sans-serif;
    line-height: 1.6;
    margin: 0 auto;
    max-width: 860px;
    padding: 40px 20px;
}
h1, h2 { color: #0b3d2e; line-height: 1.25; }
a { color: #0b63ce; }
ul { padding-left: 22px; }
.meta { color: #5d6d7e; }
""".strip()


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Finance Rampung Privacy Policy</title>
  <style>{LEGAL_STYLE}</style>
</head>
<body>
  <h1>Finance Rampung Privacy Policy</h1>
  <p class="meta">Last updated: August 26, 2026</p>

  <p>
    Finance Rampung is a personal finance management application that helps users
    record transactions, manage subscriptions, review recurring payments, and
    receive reminders.
  </p>

  <h2>Information We Collect</h2>
  <p>We may collect and process the following information:</p>
  <ul>
    <li>Telegram account information used to authenticate and identify the user.</li>
    <li>Financial records entered by the user, such as wallets, categories, transactions, debts, subscriptions, and payment history.</li>
    <li>Gmail account email address after the user connects Gmail through Google OAuth.</li>
    <li>Limited Gmail message metadata and content snippets needed to detect subscription-related invoices, receipts, billing notices, renewals, and trial notices.</li>
    <li>OAuth access tokens and refresh tokens required to access Gmail with the user's permission.</li>
  </ul>

  <h2>Google User Data</h2>
  <p>
    If a user connects Gmail, Finance Rampung uses the Gmail readonly scope to
    search and read email messages that may contain subscription, billing,
    invoice, receipt, renewal, payment confirmation, or trial-related content.
  </p>
  <p>
    Google user data is used only to detect possible recurring subscriptions and
    show those detections to the user for review. Finance Rampung does not create
    an active subscription from Gmail data unless the user confirms it.
  </p>

  <h2>How We Use Information</h2>
  <ul>
    <li>To provide dashboard authentication and account access.</li>
    <li>To display personal finance summaries and transaction history.</li>
    <li>To detect potential subscriptions from Gmail and present them for user review.</li>
    <li>To create subscription records, payment history, and reminders when requested by the user.</li>
    <li>To troubleshoot errors, prevent abuse, and maintain service reliability.</li>
  </ul>

  <h2>How We Store and Protect Information</h2>
  <p>
    OAuth tokens are encrypted before being stored in the database. Access to the
    database and application configuration is restricted to the application
    operator. Users can disconnect a Gmail account, which removes stored Gmail
    tokens from the application database.
  </p>

  <h2>Sharing and Disclosure</h2>
  <p>
    Finance Rampung does not sell Google user data. Finance Rampung does not
    share Gmail data with third parties for advertising, marketing, or unrelated
    purposes. Gmail data may be processed by configured infrastructure providers
    only as necessary to operate the application.
  </p>

  <h2>AI Processing</h2>
  <p>
    Subscription-related email candidates may be processed by the configured AI
    provider to extract structured subscription information. The application sends
    only candidate email subject, sender, date, snippet, and limited body content
    needed for subscription detection.
  </p>

  <h2>User Controls</h2>
  <ul>
    <li>Users can review, edit, confirm, ignore, or merge subscription detections.</li>
    <li>Users can disconnect Gmail from the subscription email accounts page.</li>
    <li>Users can delete or update subscription records from the dashboard.</li>
  </ul>

  <h2>Data Retention</h2>
  <p>
    Finance records and subscription detections are retained while the user uses
    the service. Gmail OAuth tokens are removed when the user disconnects Gmail.
  </p>

  <h2>Contact</h2>
  <p>
    For privacy questions, contact the Finance Rampung operator through the
    support channel provided in the application.
  </p>

  <p><a href="/terms">Terms of Service</a></p>
</body>
</html>
"""


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Finance Rampung Terms of Service</title>
  <style>{LEGAL_STYLE}</style>
</head>
<body>
  <h1>Finance Rampung Terms of Service</h1>
  <p class="meta">Last updated: August 26, 2026</p>

  <h2>Use of the Service</h2>
  <p>
    Finance Rampung is provided to help users manage personal finance data,
    subscriptions, reminders, and related records. Users are responsible for the
    accuracy of information they enter or confirm in the application.
  </p>

  <h2>Gmail Connection</h2>
  <p>
    Users may connect Gmail through Google OAuth to scan for subscription-related
    emails. Gmail access is readonly and is used only to detect possible
    subscription, invoice, receipt, billing, renewal, payment confirmation, and
    trial-related messages.
  </p>

  <h2>User Review Required</h2>
  <p>
    Email scan results are detections only. Users must review and confirm a
    detection before it becomes an active subscription record.
  </p>

  <h2>No Financial Advice</h2>
  <p>
    Finance Rampung is an informational personal finance tool. It does not
    provide financial, investment, tax, accounting, or legal advice.
  </p>

  <h2>Account Security</h2>
  <p>
    Users are responsible for keeping their account access secure. Users should
    disconnect Gmail if they no longer want Finance Rampung to access Gmail data.
  </p>

  <h2>Service Changes</h2>
  <p>
    The service may change over time, including available features, integrations,
    limits, and pricing plans.
  </p>

  <h2>Limitation of Liability</h2>
  <p>
    Finance Rampung is provided as-is. The operator is not responsible for losses
    caused by incorrect user input, inaccurate detections, missed reminders,
    third-party service outages, or user decisions based on application data.
  </p>

  <h2>Contact</h2>
  <p>
    For questions about these terms, contact the Finance Rampung operator through
    the support channel provided in the application.
  </p>

  <p><a href="/privacy">Privacy Policy</a></p>
</body>
</html>
"""
