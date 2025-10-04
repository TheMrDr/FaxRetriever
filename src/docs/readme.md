# FaxRetriever 2.0 — User Guide & Quick Start

Welcome to FaxRetriever 2.0 — a modern, Windows‑friendly desktop application for sending and receiving faxes. This guide helps you install, set up, and use the app with confidence.

If you ever get stuck, our support team is happy to help.
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

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

## Address Book
- Save and reuse contacts
- Import or export entries for backup and sharing
- Open from Tools → Manage Address Book

---

## Integrations (Optional)
FaxRetriever 2.0 supports Computer‑Rx/WinRx integration.
- Enable in System → Options → Integrations
- When enabled, FaxRetriever can poll WinRx for outbound refill requests and send faxes automatically
- On first setup, the app helps you select the correct pharmacy path and validates required files

---

## Where Settings Are Stored
- Global config (all users on this machine):
  - shared\config\config.json
- Device/user config (per Windows user):
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\config.json

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

Thank you for using FaxRetriever 2.0!