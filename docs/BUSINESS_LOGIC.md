# MSS Proposal Automation Business Logic Specification

## 1. Purpose and scope

MSS Proposal Automation is a Windows desktop application for turning a
SolarGraf project into a customer proposal package. It combines:

- SolarGraf project and financial data
- Excel pricing and settings workbooks
- Word cover-letter templates
- SolarGraf proposal PDFs
- Manufacturer specification-sheet PDFs
- Outlook email automation

The application is designed for one trained operator on one Windows
workstation. It is not a hosted service, multi-user system, or general-purpose
proposal platform.

This document describes the behavior implemented by the application. It is a
functional specification, not a data-schema or template redesign.

## 2. Runtime architecture

The application starts in [`src/main.py`](../src/main.py) and creates the
following collaborating components:

| Component | Responsibility |
|---|---|
| `App` in [`src/ui.py`](../src/ui.py) | GUI, action sequencing, status messages, background task execution, and user-facing errors. |
| `Scraper` in [`src/scraper.py`](../src/scraper.py) | SolarGraf authentication, project listing, project retrieval, proposal download, and specification-sheet download. |
| `AuthenticatedHttpClient` in [`src/http_client.py`](../src/http_client.py) | Shared HTTP session, bearer-token handling, timeout policy, and request logging. |
| `DataManager` in [`src/data.py`](../src/data.py) | Maps external JSON and workbook values into application state and calculates file paths. |
| `TemplateManager` in [`src/template.py`](../src/template.py) | Builds placeholder values from application state and settings workbook aliases/variables. |
| `OfficeDocumentManager` in [`src/office.py`](../src/office.py) | Generates Excel/DOCX outputs, converts and combines PDFs, drafts Outlook email, and copies final files. |
| `SettingsManager` in [`src/settings.py`](../src/settings.py) | Holds authentication state and workstation paths. |

Long-running GUI actions run on daemon worker threads. Completion and errors
are marshalled back to the Tk event loop. A successful action updates the UI
status and activity log; an expected operational error displays a message box
and writes diagnostic information to the application log.

## 3. Startup and configuration

Startup behavior:

1. Load environment variables.
2. Configure rotating file logging under `src/logs/app.log`.
3. Install process and thread exception hooks.
4. Run the update UI.
5. Create the main application window.

The application expects a Windows environment with:

- Microsoft Excel for pricing workbook review
- Microsoft Word for DOCX-to-PDF conversion
- Microsoft Outlook desktop for email drafts
- Google Chrome for the optional browser-extension authentication flow
- Network access to SolarGraf and manufacturer specification URLs

Important environment values:

| Variable | Use |
|---|---|
| `REQUEST_AUTH_KEY` | Existing SolarGraf bearer token, when available. |
| `SOLARGRAF_EMAIL` | SolarGraf browser-login email. |
| `SOLARGRAF_PASSWORD` | SolarGraf browser-login password. |
| `LOAN_TERM` | Initial loan-term default before workbook values are imported. |
| `LOAN_INTEREST_RATE` | Initial loan-interest default before workbook values are imported. |
| `BIDS_FOLDER` | Destination for the copied final proposal package. |

The runtime project root is normally the repository root. Relative paths in
the UI and settings are therefore expected to resolve from that directory.

## 4. Operator workflow

### 4.1 Create or load a project

The operator may open SolarGraf's project-creation page, or load an existing
project:

1. Request the recent project list from SolarGraf.
2. Display projects by customer name and project ID.
3. Let the operator select one project.
4. Request the selected project's detailed payload.
5. Normalize the payload into `DataManager`.
6. Create the project workspace and runtime directories.
7. Rebuild template values.
8. Display customer, address, project ID, utility, system type, and system size.

The project is considered loaded when a nonzero project ID is present.
Document actions require a loaded project.

### 4.2 Review and prepare pricing

`Open Pricing Spreadsheet`:

1. Validates prerequisites.
2. Loads `src/templates/pricing_spreadsheet.xlsx`.
3. Replaces placeholders across all workbook cells using current template
   values.
4. Converts replacement values to integers when possible.
5. Saves the populated workbook to the project documents directory.
6. Opens the workbook with the operating system.

The operator reviews and completes required workbook inputs in Excel. The
workbook is the source of pricing and selected operating values used by later
document stages.

### 4.3 Download and review the SolarGraf proposal

`Download Proposal Document`:

1. Validates the loaded project and required SolarGraf identifiers.
2. Builds the SolarGraf financial PDF URL from API, proposal, and financial
   identifiers.
3. Downloads the PDF to the project documents directory.
4. Opens the downloaded PDF.

### 4.4 Generate and review the cover letter

`Generate Cover Letter`:

1. Validates project, customer, system, template, settings, and pricing
   prerequisites.
2. Imports values from the operator-reviewed pricing workbook.
3. Rebuilds template values using the imported state.
4. Opens the system-specific cover-letter DOCX template.
5. Replaces placeholders in normal document paragraphs, including placeholders
   split across Word runs.
6. Saves the generated DOCX to the project documents directory.
7. Opens the generated DOCX.

The operator must review customer information, pricing, unresolved
placeholders, and formatting before finalization.

### 4.5 Finalize and package

`Finalize Proposal`:

1. Validates all required finalization inputs before writing output.
2. Converts the generated cover letter DOCX to PDF through `docx2pdf`.
3. Starts a combined PDF containing the cover-letter PDF and SolarGraf
   proposal PDF.
4. Reads specification-sheet page limits from the `Spec Sheets` worksheet.
5. Downloads applicable specification sheets.
6. Trims each downloaded specification sheet when a page limit is configured.
7. Appends specification sheets to the combined PDF.
8. Writes the final proposal PDF.
9. Opens the final PDF.
10. Creates an Outlook draft with the final PDF attached.
11. Copies the final proposal package to the configured bids folder.

The operator remains responsible for reviewing the final PDF and Outlook
draft before customer delivery.

## 5. Data normalization

`DataManager.load_json()` stores the original payload and maps selected fields
into mutable application state. Missing fields generally use the existing
application defaults; hard validation prevents document generation when
required values remain absent.

### 5.1 Project and customer

| Application value | Payload source |
|---|---|
| Project ID | `id` |
| SolarGraf API/public ID | `public_id` |
| Customer name | `client_name` |
| Customer phone | `client_phone` |
| First name | First token of `client_name` |
| Last name | Remaining tokens of `client_name` |
| Street | `Position.street` |
| City | `Position.city` |
| Region | `Position.region_code` |
| Postal code | `Position.postal_code` |
| Project display name | Uppercase customer name |

### 5.2 System type

The system type is derived from flags:

| Condition | Type |
|---|---:|
| `is_roofing_only` is truthy | `0` — PV |
| `is_battery_only` is truthy | `1` — ESS |
| Otherwise | `2` — PV + ESS |

### 5.3 Equipment and utility

Panel, inverter, and battery values are read from the first matching material
entry. Utility and billing data are read from the nested pricing/project
connection section.

Annual consumption is calculated by summing `consumptionInKwh` for each bill.
Battery ESS size is calculated as battery capacity multiplied by battery count.
Panel PTC is taken from the payload when present; otherwise the modules
workbook is searched by panel model.

### 5.4 Pricing workbook import

`DataManager.update_from_pricing_spreadsheet()` reads cell references from the
`Spreadsheet` sheet in `settings.xlsx`, then reads the referenced cells from
the generated pricing workbook. It updates:

- Tree-trimming selection
- ESS operating mode
- PV, ESS, and total cost
- Loan term, interest rate, and monthly payment
- Panel PTC
- Inverter efficiency
- Equipment counts

## 6. Template and workbook contracts

The settings workbook contains these logical worksheets:

- `Aliases`: source values to display replacements
- `Variables`: configurable placeholder values
- `Spec Sheets`: equipment models and maximum page counts
- `Spreadsheet`: pricing workbook cell references

`TemplateManager` combines settings values with derived values. Examples
include customer fields, utility display names, system type, panel/inverter/
battery values, costs, loan values, prepared date, utility language, and
conditional text.

Placeholder replacement rules:

- Workbook replacements are applied to all worksheet cells.
- DOCX replacement is applied to normal paragraphs.
- Placeholder matching is longest-key-first.
- Word placeholders split across multiple runs are reconstructed without
  intentionally replacing unrelated text.
- Templates, worksheet names, and configured cell references are external
  contracts and must not be renamed without coordinated code changes.

## 7. Validation gates

Document operations call `DataManager.validate_for_document_generation()` before
writing or downloading output.

Common required values include:

- Positive project ID
- SolarGraf project ID
- Proposal and financial IDs
- Customer name and complete address
- Utility
- Supported system type

PV systems additionally require PV size, panel identity/size/count, and
inverter identity/count. ESS systems additionally require battery identity,
capacity, and count.

Stage-specific file checks include:

| Stage | Required inputs |
|---|---|
| Pricing | Pricing template and settings workbook |
| Cover letter | Cover-letter template, settings workbook, and pricing workbook |
| Proposal download | Required project/API identifiers |
| Finalization | Cover letter DOCX, SolarGraf proposal PDF, pricing workbook, settings workbook, and applicable specification-sheet URLs |

Validation collects missing prerequisites and raises one descriptive error
before the operation proceeds.

## 8. Authentication and HTTP behavior

SolarGraf API calls use the shared authenticated HTTP client:

1. Try the current in-memory token.
2. If necessary, try `REQUEST_AUTH_KEY`.
3. If no valid token is available, wait for the local browser-extension token
   handoff.
4. Store the resulting token in settings and persist the request key.

API requests use bearer authorization and a shared timeout. Request logging
records method, URL, timeout, and request content while redacting sensitive
headers such as authorization and cookies.

The browser-extension fallback listens on local port `8765` at `/token`.
Authentication failures, missing credentials, non-success HTTP responses, and
token wait timeouts are surfaced as operational errors.

## 9. File outputs

For project ID `12345`, the normal workspace is:

```text
projects/12345/
├── data.json
├── images/
└── documents/
    ├── pricing_spreadsheet.xlsx
    ├── solargraf_proposal.pdf
    ├── cover_letter.docx
    ├── cover_letter.pdf
    ├── <dated final proposal>.pdf
    └── specsheets/
```

Finalization also copies the completed proposal, pricing workbook, cover
letter, SolarGraf proposal, and images into a customer-named folder under
`BIDS_FOLDER`.

## 10. Failure and recovery behavior

Typical blocking failures include:

- No loaded project
- No SolarGraf projects
- Invalid or expired authentication
- Missing project identifiers
- Missing required customer/equipment data
- Missing templates or settings workbook
- Missing reviewed pricing workbook
- Failed SolarGraf or specification-sheet download
- Word PDF conversion failure
- Outlook automation failure
- Unwritable project or bids directory

The UI marks the action as failed, writes the exception and traceback to the
activity/file log, and shows an error dialog. The application does not treat
partial output as successful completion.

## 11. Business invariants

The following conditions must hold for a valid customer-ready package:

1. A project is loaded from SolarGraf before document actions are enabled.
2. Customer and system data are confirmed before generation.
3. Pricing values come from the operator-reviewed pricing workbook.
4. Cover-letter generation occurs before finalization.
5. The SolarGraf proposal PDF and cover letter PDF are both included in the
   final proposal.
6. Applicable specification sheets are included according to configured page
   limits.
7. The final PDF is attached to the Outlook draft.
8. The same completed artifacts are copied to the configured bids folder.
9. The operator reviews the final artifacts before delivery.

## 12. Verification expectations

The repository regression suite is run with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
```

Current regression coverage includes data normalization, settings-backed
template values, shared HTTP authentication behavior, and final PDF assembly.