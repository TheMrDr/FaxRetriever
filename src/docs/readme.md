# FaxRetriever 2.4.1 — User Guide & Quick Start

Welcome to FaxRetriever 2.4.1 — a modern, Windows‑friendly desktop application for sending and receiving faxes. This guide helps you install, set up, and use the app with confidence.

If you ever get stuck, our support team is happy to help.
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

---

## New in 2.4 — Multi‑session Outbound Sending
FaxRetriever 2.4 automatically splits large outbound fax jobs into multiple sessions when the combined attachments would exceed the upstream 10 MiB cap. Individual files ≥ 9.5 MiB are rejected with guidance to split or compress.

Highlights:
- Automatic multi‑session send with per‑session target ≤ 9.9 MiB (overhead‑aware)
- Professional indicators: Session 1 cover page labeled “Multi‑part Fax — Session 1 of N”; Sessions 2..N begin with a compact “Continuation — Session i of N” page (when ReportLab is available)
- Pre‑send confirmation dialog lets you Cancel or Proceed when a split is required
- Clear per‑session logging and robust cleanup of temporary files

---

## New in 2.3 — LibertyRx Integration
FaxRetriever 2.3 introduces a direct integration with LibertyRx so inbound faxes can be forwarded securely and automatically into your pharmacy workflow — without passing through our servers.

Highlights:
- One‑click setup in System → Options → Integrations (choose LibertyRx)
- Enter your Pharmacy NPI (10 digits) and 7‑digit API Key; vendor authorization is fetched securely from the Clinic Networking Servers
- Where to find your LibertyRx API Key: In Liberty RXQ/PharmacyOne → System → Settings → Utilities → API Keys, click Add to generate a random key. Use this key for Clinic Networking Faxing.
- Reliable delivery with automatic retry/backoff; very large faxes are split into individual pages when required
- No PHI forwarded through the Clinic Networking Servers; credentials are stored on your device using Windows DPAPI

Note: Endpoint selection (Production/Development) is automatic for this build.

---

## Why FaxRetriever?
FaxRetriever is an easy-to-use desktop app that lets you:
- Send faxes using documents on your computer (PDF, images, and more)
- Receive faxes automatically on a schedule
- Keep everything organized with smart saving, archiving, and optional printing
- Integrate with select third‑party systems (e.g., Computer‑Rx/WinRx)

FaxRetriever 2.0 introduces a cleaner UI, improved reliability, and automatic token management behind the scenes so you can focus on your work.

---

## System Requirements
- Windows 10 or later (64-bit recommended)
- Internet connection
- Poppler is bundled with the app for PDF previews (no extra install needed)

Developer note (optional):
- Python 3.10+ if running from source
- From the project root: `python main.py`

---

## Key Concepts
- Device Mode
  - Sender: Send only
  - Sender/Receiver: Send and automatically retrieve inbound faxes
- Save Location: Where received faxes are stored on your computer
- Assignments: Only one active “retriever” device per fax number at a time (prevents duplicates)
- Immutable Download History: Once a fax has been downloaded, FaxRetriever records its FaxID in an append-only ledger so it will never be automatically re-downloaded again (even across restarts). Manual user-initiated downloads remain available.
- Tokens: Authentication is handled automatically by the app; no need to manage passwords or sessions

---

## Quick Start (2–3 minutes)
1) Launch FaxRetriever 2.0
2) Go to `System` → `Options`
3) Enter the `Fax User` and `Authentication Token` provided by Clinic Networking and click `Save`
4) In the main window, click `Configure Fax Retrieval` (top header) to select the number(s) this device should retrieve (optional if send‑only)
5) Click `Select Save Location` and choose a folder for received faxes
6) You’re set! The status bar will indicate readiness. In Sender/Receiver mode, FaxRetriever polls automatically.

Tip: You can manually check for new faxes any time with `Check for New Faxes`.

---

## Sending Faxes
1) Use the Send Fax panel (left side of the main window)
2) Add recipients and attach your documents
3) Optionally add a cover sheet
4) Review your attachments using the built‑in preview
5) Click Send

Notes:
- Numbers are normalized automatically (digits only)
- Multi‑page PDFs and images are supported
- Cover page fields like Attention and Memo are available

---

## Receiving Faxes
1) Ensure FaxRetriever is running and authenticated
2) Click `Configure Fax Retrieval`, choose your retrieval number(s), and select a `Save Location`
3) FaxRetriever will only retrieve faxes when this device is authorized as the retriever (Sender/Receiver mode AND Allowed status). When not authorized, polling and manual checks are disabled.
4) The app polls on a schedule and saves faxes to your folder

Options you can enable in System → Options:
- Archive retention (e.g., 30, 60, 90, 120, 365 days)
- Print received faxes automatically

Status indicators (top header):
- Token Lifespan: Time remaining until automatic refresh
- Poll Timer: Countdown to the next retrieval (click to retrieve now)

---

## Fax History
- View thumbnails for inbound faxes and open a full preview.
- Filter using the Inbound/Outbound toggles and search by number, name (if in Address Book), or status.
- Click the Download button on a fax card to choose a format:
  - PDF: saves a single PDF file.
  - JPG: saves one JPG per page (prefix-1.jpg, -2.jpg, ...).
  - TIFF: saves a single multi-page .tiff file.

Notes:
- Manual downloads are recorded in the immutable download history ledger; faxes already recorded will not be auto re-downloaded by the receiver.
- If a local PDF already exists, FaxRetriever will reuse it for conversions when possible.

## Address Book
- Save and reuse contacts
- Import or export entries for backup and sharing
- Open from Tools → Manage Address Book

---

## Integrations (Optional)
FaxRetriever supports LibertyRx and Computer‑Rx/WinRx integration. Choose one.
- Enable in System → Options → Integrations
- Select your integration: LibertyRx or Computer‑Rx (mutually exclusive)

LibertyRx (Inbound Forwarding)
- Setup
  - Choose LibertyRx and enter your Pharmacy NPI (10 digits) and 7‑digit API Key.
  - The app securely fetches the vendor Authorization header from Clinic Networking Servers and stores it encrypted (Windows DPAPI).
  - Where to find your LibertyRx API Key: In Liberty RXQ/PharmacyOne → System → Settings → Utilities → API Keys, click Add to generate a random key. Use this key for Clinic Networking Faxing.
- Delivery flow
  - When enabled, inbound faxes are posted to Liberty over HTTPS. If Liberty returns 200 OK, delivery is complete.
  - If Liberty returns 413 (file too large), FaxRetriever splits the PDF into single pages and delivers them one by one.
  - Retries use exponential backoff. A temporary “401 gate” prevents noisy retry loops if credentials are invalid until they are refreshed.
- Drop‑to‑send folder
  - You can manually drop PDFs into: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue
  - Files are picked up at the start of each polling cycle, forwarded to Liberty, then deleted after a successful 200 OK.
  - Processing is bounded to a few jobs per cycle to avoid blocking normal polling.
- Caller ID from filename (optional)
  - If a dropped PDF is named with an 11‑digit caller ID at the start using CID‑DDMM‑HHMM (or CID‑DDMMYY‑HHMMSS), that CID is used as FromNumber.
  - Any other filename format uses your selected caller ID from Options.
- Keep local copies (optional)
  - When enabling LibertyRx, the app asks if you want to keep local copies after a successful delivery.
  - If you choose No, the local PDF/JPG/TIFF for that fax is purged after Liberty returns 200 OK.
- Visibility and logs
  - The log shows Liberty attempts, success, and error handling (401/413). See log\ClinicFax.log.
- Endpoint selection
  - Production/Development endpoint selection is automatic for each build.

Computer‑Rx/WinRx
- Select the WinRx folder (contains FaxControl.btr) and follow prompts.
- FaxRetriever reads FaxControl.btr and sends documents via SkySwitch using your caller ID.

---

## Where Settings Are Stored
- Global config (all users on this machine):
  - shared\config\config.json
- Device/user config (per Windows user):
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\config.json
- Downloaded fax history ledger (append-only; prevents automatic re-downloads):
  - shared\history\downloaded_faxes.log
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\downloaded_faxes.log

Notes:
- The ledger is immutable and merged from both locations; do not edit these files.
- Manual, user-initiated downloads are still allowed from the UI even if a FaxID is in the ledger.

Do not edit these files directly—use Options in the app.

---

## Logs and Help
- Logs: log\ClinicFax.log (rotating logs; helpful for support)
- Help → Read Me (User Guide): opens this document in a popup window
- Help → What’s New: quick overview of new features and changes

---

## Troubleshooting
- Can’t Send Faxes
  - Ensure your account is initialized in Options (Fax User and Authentication Token)
  - Make sure you have a valid caller ID (assigned by Clinic Networking)
  - Check log\ClinicFax.log for details

- Not Receiving Faxes
  - Ensure this device is authorized as the retriever (Allowed status) for at least one number. Only one active retriever per number is permitted.
  - Confirm you’re in Sender/Receiver mode
  - Verify you’ve claimed the correct fax number(s) via Configure Fax Retrieval
  - Ensure a Save Location is set and accessible
  - When not authorized, manual and scheduled polling are disabled by design; request assignment via Configure Fax Retrieval or contact your administrator.
  - Check internet connectivity and firewall permissions

- Token Expired or Authentication Errors
  - FaxRetriever refreshes tokens automatically
  - If needed, close and reopen FaxRetriever, re‑initialize in Options, or contact support

- Scanner Issues (Sending from paper via scanner)
  - If multiple scanners are present, select the correct device when prompted
  - Ensure drivers are installed; try unplug/replug or let Windows re‑detect

---

## Privacy & Security
- FaxRetriever never stores your provider username/password
- Authentication tokens are handled automatically and refreshed before they expire
- Local configuration stores device and app settings only

---

## FAQ
- Can multiple devices retrieve the same number?
  - To prevent duplicates, only one active retriever per number is allowed; unlimited senders are fine

- Can I retrieve faxes from multiple numbers?
  - Yes. Use the Configure Fax Retrieval button in the top header

- Can I change where faxes are saved?
  - Yes. Use the Select Save Location button in the top header

- Can I open received faxes automatically?
  - Faxes do not open automatically, but you can enable printing and use your PDF viewer’s auto‑open, or check the destination folder

---

## Getting More Help
If you have questions or need assistance:
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

Thank you for using FaxRetriever 2.4.1!