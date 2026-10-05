# Development and Maintenance Guide

This guide documents the current implementation for the single-user Windows application. It is intentionally practical: the repository is maintained as a desktop tool, not as a deployed server.

## Repository map

| Path | Responsibility |
|---|---|
| `src/main.py` | Application entry point; loads environment settings, logging, updater, and UI. |
| `src/ui.py` | CustomTkinter window, workflow buttons, task threads, status, and user-facing errors. |
| `src/scraper.py` | SolarGraf project access, browser authentication, proposal download, and spec-sheet downloads. |
| `src/token_receiver.py` | Temporary local HTTP endpoint used by the Chrome extension token handoff. |
| `src/data.py` | Maps SolarGraf JSON and pricing workbook values into nested application state. |
| `src/template.py` | Builds placeholder values and loads aliases/variables from `settings.xlsx`. |
| `src/office.py` | Generates Excel/DOCX files, converts and combines PDFs, drafts Outlook email, and copies output. |
| `src/settings.py` | Workstation paths and authentication settings. |
| `src/update.py` | Startup version check and repository-based update window. |
| `src/app_logging.py` | Rotating file logging and uncaught exception hooks. |
| `src/templates/` | Excel, Word, HTML, and module-reference inputs. |
| `extension/` | Chrome Manifest V3 extension for sending a SolarGraf token to localhost. |
| `projects/` | Runtime-generated project data; ignored by Git. |

## Runtime model

The application is a sequential workflow wrapped in a GUI:

```text
main.py
  -> UpdateManager
  -> App
       -> Scraper
       -> DataManager
       -> TemplateManager
       -> OfficeDocumentManager
```

Long-running UI actions execute in daemon threads and marshal completion back to Tk with `after()`. The model is mutable: loading a project fills `DataManager`, spreadsheet import updates pricing and system fields, and template generation reads the current state.

When changing this behavior, preserve the distinction between:

- SolarGraf source data
- Derived values
- Operator-edited spreadsheet values
- Generated files

The current implementation does not enforce that distinction strongly, so changes should avoid introducing additional hidden mutation.

## Local development setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\src\requirements.txt
.\.venv\Scripts\python.exe .\src\main.py
```

For a UI-only launch:

```powershell
.\.venv\Scripts\python.exe .\src\ui.py
```

The VS Code launch configuration is in [`.vscode/launch.json`](../.vscode/launch.json).

## Templates and workbook contracts

### `settings.xlsx`

The code expects these worksheets:

- `Aliases`: placeholder or source value in column A, display replacement in column B.
- `Variables`: configurable placeholder values in columns A and B.
- `Spec Sheets`: equipment model in column A and maximum page count in column B.
- `Spreadsheet`: pricing workbook cell references in cells `B2:B11`.

The `Spreadsheet` values are used as references into the `Pricing Calculator` sheet. The code also reads equipment counts from `C12`, `C13`, and `C16`.

### `pricing_spreadsheet.xlsx`

The workbook is copied/populated for each project. Placeholder replacement occurs across worksheet cells. After the operator edits or reviews the workbook, `DataManager.update_from_pricing_spreadsheet()` reads the calculated values back.

Because the code relies on exact sheet names and cell references, template changes should be reviewed as code changes. Keep a backup and test a complete PV, ESS, and combined-system run.

### Word templates

Cover-letter placeholders use names such as:

```text
{{CLIENT_NAME}}
{{CLIENT_ADDRESS_1}}
{{UTILITY_NAME}}
{{PV_SIZE}}
{{TOTAL_COST}}
{{PREPARED_DATE_MMDDYYYY}}
```

The replacement code is designed for placeholders split across Word runs in normal paragraphs. Test any placeholders placed in tables, headers, footers, text boxes, or other document parts before relying on them.

## Adding a placeholder

1. Add the placeholder to the relevant DOCX, XLSX, or HTML template.
2. If it is a derived application value, add it in `TemplateManager.update()`.
3. If it is configurable, add it to the appropriate `settings.xlsx` sheet.
4. Confirm the value is available for PV-only, ESS-only, and combined systems as applicable.
5. Generate a representative document and search the outputs for unresolved `{{` text.
6. Review formatting and units manually.

Prefer configuration for business wording and aliases. Keep calculations in Python only when they cannot reasonably be represented as validated configuration.

## Changing SolarGraf field mappings

The external payload is mapped in `DataManager.load_json()`. When adding or changing a field:

1. Identify the exact payload shape and whether the field is required.
2. Decide whether missing data should block generation or be optional.
3. Normalize the value and units once in `DataManager`.
4. Add a corresponding validation check.
5. Update the template or UI summary if the field is user-visible.
6. Test malformed, missing, and empty values.

Avoid adding more silent defaults. A default is safe only when it is a documented business rule, not when it masks a changed payload.

## Testing and validation

There is currently no automated test suite. Before submitting a change:

```powershell
Get-ChildItem -Path . -Recurse -File -Filter *.py |
  Where-Object { $_.FullName -notmatch '\\.venv\\' } |
  ForEach-Object { .\.venv\Scripts\python.exe -m py_compile $_.FullName }
```

Then perform a manual smoke test:

1. Start the application.
2. Load a known SolarGraf project.
3. Confirm the summary fields.
4. Generate and inspect pricing.
5. Generate and inspect the cover letter.
6. Download the proposal.
7. Finalize into a test bids folder.
8. Confirm the final PDF, attachment, and copied files.

Do not use a live customer delivery folder for development tests.

High-value future tests should cover:

- Payload mapping and missing fields
- Annual consumption calculation
- Panel PTC lookup
- Placeholder replacement across runs
- Pricing workbook import
- PDF assembly with isolated fixtures
- Token receiver malformed requests
- Installer and updater behavior using local fixtures

## Logging and diagnostics

Logs are written to `src/logs/app.log` using a rotating handler. The UI activity log is for operator feedback; the file log is the better source for stack traces and background-thread failures.

When diagnosing an issue, record:

- Application version from `src/details.json`
- Project ID
- Action that failed
- Whether the input came from SolarGraf, Excel, Word, or Outlook
- Relevant log timestamp
- Exact output path

Never paste passwords, request tokens, or full customer payloads into issues or commits.

## Safe release procedure

1. Test from a clean copy or fresh virtual environment.
2. Confirm templates are present and open correctly.
3. Run syntax validation.
4. Perform the manual smoke test with a non-customer test project.
5. Update `src/details.json` version and changelog.
6. Review the Git diff, including template changes.
7. Create a release or tagged revision only after the complete package is usable.
8. Keep a copy of the previous working version for rollback.

The current updater follows the repository `main` branch and copies files into the installed `src` directory. Do not publish a breaking template or code change without coordinating the version and rollback plan.

## Known implementation hazards

- Most runtime paths are relative to the working directory. Launch from the repository root.
- The updater can replace the installed source tree before startup.
- The token receiver is local-only but does not authenticate requests.
- Finalization writes multiple artifacts and has no transaction or manifest.
- `os.startfile`, Outlook COM, and `docx2pdf` require Windows desktop applications.
- Spreadsheet sheet names and cell references are hard-coded contracts.

These are documented operational constraints, not guarantees that the application will recover automatically.
