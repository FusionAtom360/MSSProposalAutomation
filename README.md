# MSS Proposal Automation

Windows desktop automation for turning a SolarGraf project into a proposal package.

This application is intended for one trained operator on a Windows workstation. It is not a multi-user service, hosted application, or general-purpose proposal platform.

## What it does

The application combines data from SolarGraf, Excel pricing templates, Word cover-letter templates, and manufacturer specification sheets. A typical run:

1. Checks for an application update.
2. Loads a SolarGraf project.
3. Creates a project workspace under `projects/<project-id>/`.
4. Generates a pricing workbook.
5. Downloads the SolarGraf proposal PDF.
6. Generates a cover letter.
7. Combines the cover letter, SolarGraf proposal, and specification sheets into a final PDF.
8. Creates an Outlook email draft and copies the completed package to the configured bids folder.

The main application is in [`src/`](src/). The browser extension used for token handoff is in [`extension/`](extension/). Templates are stored in [`src/templates/`](src/templates/).

## Requirements

- Windows
- Python compatible with the pinned dependencies in [`src/requirements.txt`](src/requirements.txt)
- Microsoft Excel
- Microsoft Word, required by `docx2pdf`
- Microsoft Outlook desktop, required to create the email draft
- Google Chrome, when using the token-extractor extension
- Network access to SolarGraf, GitHub, and manufacturer specification URLs
- A writable application directory and writable bids destination

The application is Windows-specific because it uses `os.startfile`, Outlook COM automation, `pywin32`, and Microsoft Office PDF conversion.

## First-time setup

### Option A: use the installer

Run `install.py` from the folder where you want the application installed:

```powershell
python install.py
```

The installer clones the repository, creates `.venv`, installs dependencies, and creates `src/.env`.

Review the generated `.env` before starting the application. The installer is a convenience bootstrapper; if it fails partway through, use the manual setup below or repair the installation before retrying.

### Option B: manual setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\src\requirements.txt
Copy-Item .\src\.env.example .\src\.env
```

If `.env.example` is not present in the installed copy, create `src/.env` manually using the variables below.

Start the application from the repository root:

```powershell
.\.venv\Scripts\python.exe .\src\main.py
```

The included [`run.ps1`](run.ps1) is equivalent to the last command, but assumes it is executed from the repository root.

## Configuration

Create `src/.env` and set the values appropriate for the workstation:

```dotenv
SOLARGRAF_EMAIL=your-login@example.com
SOLARGRAF_PASSWORD=your-password
LOAN_TERM=0
LOAN_INTEREST_RATE=0.0
BIDS_FOLDER=C:\Path\To\Bids
```

### Variable reference

| Variable | Required | Purpose |
|---|---:|---|
| `SOLARGRAF_EMAIL` | Usually | SolarGraf login used by browser automation. |
| `SOLARGRAF_PASSWORD` | Usually | SolarGraf password used by browser automation. |
| `REQUEST_AUTH_KEY` | As needed | Existing SolarGraf request token. The application can also obtain a token through the extension flow. |
| `LOAN_TERM` | Optional | Default loan term used before spreadsheet values are loaded. |
| `LOAN_INTEREST_RATE` | Optional | Default interest rate used before spreadsheet values are loaded. |
| `BIDS_FOLDER` | Required for finalization | Destination where the completed package is copied. |

Do not commit `src/.env`, passwords, request tokens, or customer data. The application writes project data to `projects/<project-id>/data.json`.

## Browser extension token setup

The extension is an optional fallback for obtaining a SolarGraf browser token.

1. Open Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the repository's `extension` folder.
5. Keep the extension enabled.
6. Start the application and allow it to open SolarGraf.
7. Sign in to SolarGraf in Chrome if prompted.
8. Keep the SolarGraf tab open while the application waits for authentication.

The extension sends the token to a local listener at `http://127.0.0.1:8765/token`. The listener is temporary and is used only during the authentication flow.

## Normal operating procedure

### 1. Start the application

Launch from the repository root so relative paths resolve correctly. Wait for the update window to finish before using the main UI.

### 2. Load a project

Choose **Load Project from Solargraf**. Select the project from the list returned by SolarGraf. Confirm the customer, project ID, utility, system type, and size in the summary panel.

Use **Update Project from Solargraf** if the SolarGraf project changes before documents are generated.

### 3. Review settings and templates

The quick-access buttons open:

- **Settings**: `src/templates/settings.xlsx`
- **Pricing Template**: `src/templates/pricing_spreadsheet.xlsx`
- **Cover Template**: the system-specific cover letter template
- **Email Template**: `src/templates/email.html`

Do not rename worksheet names or move referenced cells without updating the code and testing a complete run.

### 4. Generate pricing

Choose **Open Pricing Spreadsheet**. Review the generated workbook in Excel and complete any required operator inputs. The workbook is saved under the project documents folder.

The settings workbook provides aliases, variable references, specification-sheet page limits, and pricing cell references.

### 5. Download and review the proposal

Choose **Download Proposal Document**. Confirm that the SolarGraf proposal PDF opens and is saved under the current project workspace.

### 6. Generate the cover letter

Choose **Generate Cover Letter**. Review the DOCX for unresolved placeholders, incorrect customer information, and pricing values before finalization.

### 7. Finalize

Choose **Finalize Proposal** only after reviewing the pricing workbook and cover letter. This action:

- Converts the cover letter to PDF.
- Downloads and trims configured specification sheets.
- Creates the final combined PDF.
- Opens the final PDF.
- Creates an Outlook draft with the final PDF attached.
- Copies the package to `BIDS_FOLDER`.

Review the final PDF and Outlook draft manually before sending or delivering anything to a customer.

## Project files

For project ID `12345`, generated files are normally stored as:

```text
projects/
└── 12345/
    ├── data.json
    ├── images/
    └── documents/
        ├── solargraf_proposal.pdf
        ├── pricing_spreadsheet.xlsx
        ├── cover_letter.docx
        ├── cover_letter.pdf
        ├── final proposal PDF
        └── specsheets/
```

The application also writes logs to `src/logs/app.log`.

## Troubleshooting

### The application cannot find templates or details

Start it from the repository root. Avoid launching `src/main.py` with an unrelated working directory. Confirm that `src/templates/` and `src/details.json` exist.

### SolarGraf authentication times out

Confirm that Chrome is open, the extension is loaded, the SolarGraf tab is active, and port `8765` is available. Check `src/logs/app.log`. If a stale token is suspected, close the application and start a fresh authentication attempt.

### A proposal contains blanks, zeros, or `{{...}}` text

Stop before delivery. Recheck the SolarGraf project payload, the settings workbook sheets and cell references, and the generated pricing workbook. Do not treat a successful button completion as proof that every value is correct.

### PDF conversion fails

Confirm that Microsoft Word is installed and can open the generated DOCX. Close any locked copy of the output files and retry.

### Outlook draft creation fails

Confirm that the classic Outlook desktop application is installed and configured. The final PDF may still exist even if the email step fails; inspect the project documents folder and create the message manually if necessary.

### The bids copy fails

Confirm that `BIDS_FOLDER` points to a reachable, writable folder. Check for an existing file lock or a disconnected network share.

## Important limitations

- The application assumes one operator and one active run at a time.
- There is no multi-user access control or shared job queue.
- Output generation is operator-assisted; always review customer-facing documents.
- Templates and spreadsheet coordinates are part of the application contract.
- The automatic updater currently retrieves application files from the repository; update behavior should be treated as trusted internal infrastructure.
- The application does not provide a database, audit dashboard, or formal rollback for generated documents.

## Developer documentation

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the module map, local development workflow, templates, testing guidance, and safe change practices.

See [`dev/TECHNICAL_REVIEW.md`](dev/TECHNICAL_REVIEW.md) for the adversarial technical review and prioritized engineering gaps.
