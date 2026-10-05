# Operator User Guide

This is the short daily-use guide for the intended single operator.

## Before starting

Check that:

- You are connected to the internet.
- Chrome can open SolarGraf.
- Excel, Word, and Outlook are installed and signed in.
- The bids destination is available.
- No earlier copy of the application is still running.

Start the application from its repository folder. If you use a shortcut, configure its **Start in** directory to the repository root.

## Daily workflow

### Load the customer project

Click **Load Project from Solargraf**, complete authentication if requested, and choose the project. Check:

- Customer name
- Project ID and API ID
- Utility
- System type
- PV size

If anything is wrong, do not continue. Use **Update Project from Solargraf** or correct the SolarGraf project first.

### Prepare pricing

Click **Open Pricing Spreadsheet**. In Excel:

1. Review the customer and system values.
2. Enter or verify any operator-controlled pricing inputs.
3. Confirm totals, loan terms, interest rate, and monthly payment.
4. Save and close Excel.

Do not rename worksheets or move calculation cells.

### Prepare the cover letter

Click **Generate Cover Letter**. Open the DOCX and check the customer name, address, utility, equipment, system type, costs, and dates. Search for `{{` to find unresolved placeholders.

### Download the proposal

Click **Download Proposal Document**. Confirm the downloaded PDF opens and belongs to the selected project.

### Finalize and review

Click **Finalize Proposal**. Wait for the action to finish. It creates the final PDF, opens an Outlook draft, and copies files to the bids folder.

Before sending or delivering:

- Read the complete final PDF.
- Confirm the equipment and pricing match the workbook.
- Confirm the specification sheets belong to the installed equipment.
- Confirm the Outlook recipient and attachment.
- Confirm the copied package exists in the bids folder.

## Where to find outputs

The project folder is:

```text
projects\<project-id>\
```

Documents are under:

```text
projects\<project-id>\documents\
```

The copied delivery package is under the `BIDS_FOLDER` configured in `src/.env`.

## If something goes wrong

Do not send a proposal that contains blanks, zeros, unresolved placeholders, or a stale customer name.

Use this recovery sequence:

1. Close Excel, Word, and any PDF opened by the application.
2. Check the UI message and `src/logs/app.log`.
3. Confirm the selected project and source data.
4. Retry only the failed stage when possible.
5. If the project data is stale, use **Update Project from Solargraf** and regenerate affected documents.
6. If finalization partially completed, inspect the project documents folder before retrying so you know which files are current.

For authentication failures, close the application and start a fresh run. Keep Chrome and the SolarGraf tab open while the application waits.

## Editing templates

Only edit templates when you understand the placeholder and workbook contracts. Make a backup first. A template can open normally in Office and still be incompatible with the automation if sheet names, cell references, or placeholder text change.

## Data and privacy

The application stores raw project data in `projects\<project-id>\data.json` and customer-facing documents in the same project folder. Treat the repository and project folders as confidential business data. Do not upload them to public issue trackers or share them without removing customer information and credentials.
