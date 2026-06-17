# QuailCash iOS Native Port Tree

Status legend:
- `done`: native screen exists and the main backend contract is wired
- `partial`: native screen exists, but some webapp controls or flows are still missing or simplified
- `placeholder`: route exists, but screen is still a shell or missing major functionality

## App Shell
- `done` Shared top bar
  - file: `QuailCash/QuailCash/AppChrome.swift`
  - used by Home, Settings, Budget, Account, Analytics, Recurring, All, Notifications
- `done` Shared bottom bar
  - file: `QuailCash/QuailCash/AppChrome.swift`
- `done` Shared navigation stack/router
  - file: `QuailCash/QuailCash/AppNavigator.swift`
  - root stack file: `QuailCash/QuailCash/WebAppHomeApp.swift`
- `partial` Shared modal / popup patterns
  - transaction inspector is shared
  - budget add/edit flows currently use native sheets, not inline web-style controls everywhere

## Home
- web sources
  - `static/pages/home/home.html`
  - `static/pages/home/home.js`
  - `static/pages/home/home.css`
- iOS source
  - `QuailCash/QuailCash/HomeView.swift`
- status: `partial`
- implemented
  - chart section
  - month snapshot
  - monthly spending
  - bank totals accordion
  - recent transactions
  - transaction inspector popup
  - account row navigation
  - budget button navigation
  - chart controls and YTD
- missing / still not fully matched
  - final chart spacing and exact mobile positioning
  - any remaining web-only popups tied to Home sections
  - exact parity for every chart interaction edge case

## Budget
- web sources
  - `static/pages/budget/budget.html`
  - `static/pages/budget/budget.js`
  - `static/pages/budget/budget.css`
- backend sources
  - `/page/budget` in `app/routers/category_rules.py`
  - `/budget/groups` in `app/routers/budget_groups.py`
  - `/funds*` in `app/routers/funds.py`
  - `/settings/round-ups` in `app/routers/settings.py`
  - `/settings/savings-goal` in `app/routers/savings_goal.py`
  - `/day-limit` in `app/routers/page_payloads.py`
- iOS sources
  - `QuailCash/QuailCash/NativeBudgetPage.swift`
  - API: `QuailCash/QuailCash/QuailCashAPI.swift`
  - models: `QuailCash/QuailCash/QuailCashModels.swift`
- status: `partial`
- implemented
  - month navigation
  - month KPI card
  - recalc today
  - budget groups list
  - add/edit/delete groups
  - synthetic savings goal save flow
  - sinking funds list
  - add/edit/delete funds
  - fund add/use adjustments
  - spent categories list
  - pie chart area
  - category navigation
  - six-month trend
  - round-up toggle
- missing / still not fully matched
  - exact web inline editing layout for groups
  - exact mobile card/table visual parity
  - web calc popups for income / safe-to-spend / spent rows
  - web modal parity for funds and transaction drilldowns

## All Transactions
- web sources
  - `static/pages/all-transactions/all-transactions.html`
  - `static/pages/all-transactions/all-transactions.js`
  - `static/pages/all-transactions/all-transactions.css`
- iOS source
  - `QuailCash/QuailCash/NativeReportAndListPages.swift`
- status: `partial`
- implemented
  - filters card
  - add transaction form
  - paged transaction loading
  - shared transaction inspector
  - signed amount color fix
- missing / still not fully matched
  - exact filter layout parity
  - any missing web filter options
  - exact transaction row spacing and mobile polish

## Analytics
- web sources
  - `static/pages/analytics/analytics.html`
  - `static/pages/analytics/report-page.js`
  - `static/pages/analytics/analytics.css`
- iOS source
  - `QuailCash/QuailCash/NativeReportAndListPages.swift`
- status: `partial`
- implemented
  - monthly report load
  - summary
  - category breakdown
  - account sections
  - biggest transactions
  - recurring/subscriptions
  - budget performance
  - month-over-month changes
- missing / still not fully matched
  - exact mobile report layout
  - actual PDF download/export
  - any chart/table interactions the web report has beyond the current cards

## Recurring
- web sources
  - `static/pages/recurring/recurring.html`
  - `static/pages/recurring/recurring.js`
- iOS source
  - `QuailCash/QuailCash/NativeReportAndListPages.swift`
- status: `partial`
- implemented
  - native recurring page exists
  - projected calendar and recurring groups
- missing / still not fully matched
  - full web interaction parity
  - exact calendar behaviors
  - merge / ignore / edit flows if not already surfaced in native page

## Account
- web sources
  - `static/pages/account/account.html`
  - `static/pages/account/account.js`
  - `static/pages/account/account.css`
- iOS source
  - `QuailCash/QuailCash/NativeAccountPage.swift`
- status: `partial`
- implemented
  - account dropdown in top bar
  - account chart area and date controls
  - upcoming section
  - transaction list
  - audit mode route
  - verified action
- missing / still not fully matched
  - final balance-sign parity for every account type edge case
  - exact web layout and modal parity
  - any missing export/add/audit subflows

## Category
- web sources
  - `static/pages/category/category.html`
  - `static/pages/category/category.js`
  - `static/pages/category/category.css`
- iOS source
  - `QuailCash/QuailCash/NativePages.swift`
- status: `partial`
- implemented
  - category transaction list
- missing / still not fully matched
  - trend/chart sections
  - any category summary blocks
  - web action parity

## Settings
- web sources
  - `static/pages/settings/settings.html`
  - `static/pages/settings/settings.js`
  - `static/pages/settings/settings.css`
- iOS source
  - `QuailCash/QuailCash/SettingsHomePageView.swift`
- status: `partial`
- implemented
  - mobile-style native settings layout
  - Google OAuth status
  - initial setup status
  - cache versions
  - notification settings route
  - widget/setup/external apps/income wizard/admin entry points
- missing / still not fully matched
  - exact mobile spacing/dividers on all sections
  - every downstream screen ported natively

## Notification Settings
- web sources
  - `static/pages/notification-settings/notification-settings.html`
  - `static/pages/notification-settings/notification-settings.js`
- iOS source
  - `QuailCash/QuailCash/NativePages.swift`
- status: `partial`
- implemented
  - toggles list
- missing / still not fully matched
  - exact web groupings and descriptions if they differ

## Notifications Inbox
- web sources
  - shared top-bar / notifications JS behavior
- iOS source
  - `QuailCash/QuailCash/NativePages.swift`
- status: `partial`
- implemented
  - native unread list
- missing / still not fully matched
  - exact web drawer behavior
  - mark-read / actions if applicable

## Bank Info
- web sources
  - Home popup logic in `static/pages/home/bankInfo.js`
- iOS sources
  - Home popup in `QuailCash/QuailCash/HomeView.swift`
  - route screen in `QuailCash/QuailCash/NativePages.swift`
- status: `partial`
- implemented
  - native popup and route entry
  - rates/accounts/cards data load
- missing / still not fully matched
  - exact web panel interactions
  - full interest-rate edit flow parity in routed screen

## CSV Import
- status: `placeholder`
- iOS source
  - `QuailCash/QuailCash/NativePages.swift`
- current state
  - route exists
  - no real importer flow yet

## Unassigned / Rule Builder
- web sources
  - `static/pages/category-rules/category-rules.html`
  - `static/pages/category-rules/category-rules.js`
- iOS source
  - `QuailCash/QuailCash/NativePages.swift`
- status: `placeholder`
- current state
  - route exists
  - original rule form and matcher flow not yet ported

## External Apps
- web sources
  - `static/pages/external-apps/external-apps.html`
  - `static/pages/external-apps/external-apps.js`
- iOS source
  - currently entered from Settings
- status: `placeholder`

## Income Wizard
- web sources
  - `static/pages/income-wizard/income-wizard.html`
  - `static/pages/income-wizard/income-wizard.js`
- iOS source
  - currently entered from Settings
- status: `placeholder`

## Setup Wizard
- web sources
  - `static/pages/setup/setup.html`
  - `static/pages/setup/setup.js`
- iOS source
  - currently entered from Settings
- status: `placeholder`

## Admin
- web sources
  - `static/pages/admin/admin.html`
  - `static/pages/admin/admin.js`
- iOS source
  - currently entered from Settings
- status: `placeholder`

## Backend / Data Issues Already Identified
- home snapshot cache vs live totals mismatch
  - files:
    - `app/core/account_totals_cache.py`
    - `app/core/home_snapshot_cache.py`
    - `app/routers/page_payloads.py`
- account running total pending-transaction mismatch
  - file:
    - `app/routers/balances.py`
- credit `CR` semantics
  - frontend formatters corrected, but account-type-specific validation still matters per screen

## Suggested Order To Finish
1. Budget visual parity pass
2. Account page parity pass
3. Recurring parity pass
4. Analytics parity pass
5. Category parity pass
6. CSV Import
7. Rule Builder / Category Rules
8. Setup / Income Wizard / External Apps / Admin
