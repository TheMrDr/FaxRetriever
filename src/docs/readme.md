# FaxRetriever — User Guide

Welcome to FaxRetriever, a Windows desktop app for sending and receiving faxes. This guide walks you through setup, everyday use, and answers to common questions.

If you ever get stuck, we’re happy to help:
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

---

## What FaxRetriever does
- Send faxes from documents on your PC (PDF and images)
- Receive faxes automatically and save them to a folder you choose
- Keep things organized with archiving, optional printing, and a searchable history
- Connect to optional integrations (LibertyRx or Computer‑Rx/WinRx)

Behind the scenes, FaxRetriever handles sign‑in tokens for you so you don’t have to manage passwords or sessions.

---

## System requirements
- Windows 10 or later (64‑bit recommended)
- Internet connection
- PDF preview support is included (no extra install needed)

Developers (optional):
- Python 3.10+ if running from source
- From the project root: `python main.py`

---

## Key ideas
- Device mode
  - Sender — Send only
  - Sender/Receiver — Send and automatically retrieve inbound faxes
- Save Location — The folder where received faxes are stored
- Assignments — To prevent duplicates, only one active “retriever” device per fax number at a time
- Download history — Once a fax is downloaded, FaxRetriever records its ID in an append‑only log so it is not downloaded again automatically. Manual, user‑initiated downloads are always allowed.
- Tokens — Authentication is automatic and refreshed before it expires

---

## Quick start (about 2 minutes)
1) Launch FaxRetriever
2) Go to `System` → `Options`
3) Enter the `Fax User` and `Authentication Token` provided by Clinic Networking, then click `Save`
4) In the main window, click `Configure Fax Retrieval` to select the number(s) this device should retrieve (optional if send‑only)
5) Click `Select Save Location` and choose a folder for received faxes
6) You’re set! In Sender/Receiver mode, FaxRetriever checks for new faxes automatically. You can click `Check for New Faxes` any time.

---

## Sending faxes
1) Open the Send Fax panel (left side)
2) Add recipients and attach your documents
3) Optionally add a cover page (Attention, Memo, etc.)
4) Review your attachments with the built‑in preview
5) Click `Send`

Notes
- Phone numbers are normalized automatically (digits only)
- Multi‑page PDFs and images are supported
- Large outbound jobs are split into multiple sessions automatically when needed to stay under provider limits; you’ll be asked to confirm before sending a multi‑part fax

---

## Receiving faxes
1) Make sure FaxRetriever is running and authenticated
2) Click `Configure Fax Retrieval`, choose your retrieval number(s), and select a `Save Location`
3) FaxRetriever retrieves faxes only when this device is authorized as the retriever (Sender/Receiver mode AND Allowed status). When not authorized, polling and manual checks are disabled.
4) Faxes are saved into your folder on a schedule; you can click the poll timer to retrieve now

Helpful options (System → Options)
- Archive retention (e.g., 30, 60, 90, 120, 365 days)
- Print received faxes automatically

Status indicators (top header)
- Token Lifespan — Time remaining until auto‑refresh
- Next Poll — Countdown to the next retrieval (click to retrieve now)

---

## Fax History
- Browse thumbnails for inbound faxes and open a full preview
- Filter with the Inbound/Outbound toggles and search by number, name (if in Address Book), or status
- Click `Download` on a fax card to choose a format:
  - PDF — single PDF file
  - JPG — one JPG per page (prefix-1.jpg, -2.jpg, ...)
  - TIFF — single multi‑page .tiff file

Notes
- Manual downloads are recorded in the download history and won’t be auto re‑downloaded by the receiver
- If a local PDF already exists, FaxRetriever reuses it for conversions when possible

---

## Address Book
- Save and reuse contacts
- Import or export entries for backup and sharing
- Open from `Tools → Manage Address Book`

---

## Integrations (optional)
FaxRetriever supports one of the following at a time: LibertyRx or Computer‑Rx/WinRx.

LibertyRx (forward inbound faxes)
- Setup
  - In `System → Options → Integrations`, choose LibertyRx
  - Enter your Pharmacy NPI (10 digits) and 7‑digit API Key
  - Where to find your LibertyRx API Key: In Liberty RXQ/PharmacyOne → System → Settings → Utilities → API Keys, click Add to generate a random key. Use this key for Clinic Networking Faxing.
- How it works
  - Inbound faxes are posted to Liberty over HTTPS; success shows as delivered
  - If a fax is too large, FaxRetriever splits it into single pages and delivers them one by one
  - Automatic retries with backoff; credentials are stored encrypted using Windows DPAPI
- Drop‑to‑send folder (optional)
  - Drop PDFs into: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue
  - Files are forwarded on the next poll and removed after a successful delivery
- Caller ID from filename (optional)
  - If the PDF name starts with 11‑digit caller ID using CID‑DDMM‑HHMM (or CID‑DDMMYY‑HHMMSS), that ID is used as FromNumber
- Keep local copies (optional)
  - When enabling LibertyRx, you can choose whether to keep local copies after a successful delivery

Computer‑Rx/WinRx
- Select the WinRx folder (contains `FaxControl.btr`) and follow prompts
- FaxRetriever reads `FaxControl.btr` and sends documents using your selected caller ID

---

## Where settings are stored
- Global (all users on this machine)
  - `shared\config\config.json`
- Device/user (per Windows user)
  - `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\config.json`
- Downloaded fax history (append‑only; prevents auto re‑downloads)
  - `shared\history\downloaded_faxes.log`
  - `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\downloaded_faxes.log`

Notes
- The history is merged from both locations; do not edit these files
- Use Options in the app to make changes

---

## Logs and help
- Logs: `log\ClinicFax.log` (rotating log; useful for support)
- Help → Read Me — opens this guide in a window
- Help → What’s New — opens the changelog

---

## Troubleshooting
Can’t send faxes
- Check `System → Options` for your Fax User and Authentication Token
- Make sure you have a valid caller ID (assigned by Clinic Networking)
- Open `log\ClinicFax.log` for details

Not receiving faxes
- Confirm this device is Allowed as the retriever for at least one number (one active retriever per number)
- Verify `Sender/Receiver` mode is selected
- Click `Configure Fax Retrieval` to check the selected numbers
- Ensure a Save Location is set and accessible
- When not authorized, manual and scheduled polling are disabled by design
- Check your internet connection and firewall

Token expired or authentication errors
- FaxRetriever refreshes tokens automatically
- If needed, close and reopen FaxRetriever, re‑initialize in Options, or contact support

Scanner issues (sending from paper)
- If multiple scanners are present, select the correct device when prompted
- Ensure drivers are installed; try unplug/replug or let Windows re‑detect

---

## Privacy & security
- FaxRetriever never stores your provider username/password
- Authentication tokens are handled automatically and refreshed before they expire
- Local configuration stores device and app settings only

---

## FAQ
- Can multiple devices retrieve the same number?
  - No. To prevent duplicates, only one active retriever per number is allowed. Any number of devices can send.
- Can I retrieve faxes from multiple numbers?
  - Yes. Use the `Configure Fax Retrieval` button in the top header.
- Can I change where faxes are saved?
  - Yes. Use the `Select Save Location` button in the top header.
- Can I open received faxes automatically?
  - Faxes do not auto‑open, but you can enable printing, or open them from your save folder.

---

## Tools
Convert PDF to JPG…
- Open `Tools → Convert PDF to JPG…`
- Select one or more PDFs and an output folder; the app creates a subfolder per PDF and saves one JPG per page
- Default rendering is 200 DPI at JPEG quality 90. The app tries PyMuPDF first, then uses pdf2image with Poppler when needed
- Output naming example: `mydoc_p001.jpg`, `mydoc_p002.jpg`, …

---

## Getting more help
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

Thank you for using FaxRetriever! 
