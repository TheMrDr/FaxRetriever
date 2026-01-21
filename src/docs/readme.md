# FaxRetriever 2.6.8 — User Guide

Welcome to FaxRetriever — a simple, Windows‑friendly desktop app for sending and receiving faxes. This guide explains how to install, set up, and use the app day‑to‑day. 

If you ever need help, we’re here:
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

Tip: For a summary of recent updates, open Help → What’s New or see src/docs/changes.md.

---

## What FaxRetriever does
- Send faxes from PDFs and images on your computer.
- Receive faxes automatically on a schedule and save them where you choose.
- Keep things organized with history, optional printing, and archiving.
- Integrate with LibertyRx (forward inbound faxes and accept outbound posts over LAN) or Computer‑Rx/WinRx (automate outbound sends). Only one integration may be active at a time.

---

## Before you start
- Windows 10 or later (64‑bit recommended)
- Internet connection

Optional for IT/developers: The app can run from source with Python 3.10+ (`python main.py`), but typical users install and run the packaged app.

---

## Quick start (2–3 minutes)
1) Launch FaxRetriever.
2) Go to System → Options.
3) Enter the Fax User and Authentication Token provided by Clinic Networking. Click Save.
4) In the main window, click Configure Fax Retrieval to choose which number(s) this device should retrieve (optional if you only send faxes).
5) Click Select Save Location and choose the folder where received faxes should be stored.
6) You’re ready to go. The app will check for new faxes automatically.

You can check immediately at any time with Check for New Faxes.

---

## Everyday use

### Send a fax
1) Use the Send Fax panel on the left.
2) Enter the destination fax number and add your documents (PDFs and common image types).
3) Optional: add a cover sheet (Attention, Memo, etc.).
4) Review the built‑in preview.
5) Click Send.

Notes
- The app cleans up phone numbers automatically (digits only).
- Multi‑page PDFs and images are supported.

### Receive faxes automatically
1) Make sure the app is running and you’ve selected a Save Location.
2) Click Configure Fax Retrieval to select one or more numbers for this device.
3) FaxRetriever will retrieve faxes only when this device is allowed as the retriever for a number and the mode is Sender/Receiver. When not authorized, manual and scheduled polling are disabled by design.
4) Received faxes are saved to your chosen folder. You can also enable automatic printing in Options.

Top‑bar indicators
- Token Lifespan: time remaining before the app refreshes your sign‑in token automatically.
- Next Poll: countdown to the next check for new faxes (click to poll now).

### Track outgoing faxes with Outbox
The Outbox shows what you’ve sent and what happened next.
- Statuses: Accepted (in‑flight), Delivered, Failed Delivery, Invalid Number, Quarantined, Delivery Unknown (no final result after one day).
- Refresh: updates automatically while the app is open and after you take actions.
- Actions per item: View PDF, Open Folder, Retry/Send (enabled when the original PDF exists), Remove (for finished items).
- Notifications: you’ll see a short notification when a fax is accepted for sending and another when a final delivery result is known.

Invalid number (Computer‑Rx/WinRx)
- If a number from WinRx is missing or unclear, the job is stopped so it doesn’t loop.
- The original PDF is moved to WinRx\FaxRetriever\Failed.
- You’ll see an easy correction window to view the PDF, fix the number, and resend.

### Find and save received faxes (History)
- Use the History panel to see thumbnails and open a full preview.
- Filter between Inbound and Outbound and search by number, name (Address Book), or status.
- Click Download to save as PDF, JPG (one per page), or TIFF (single multi‑page file).

Important: Once a fax is downloaded by the receiver, it’s recorded in an internal ledger. Faxes in that ledger are never downloaded again automatically, even after restarts. You can still download them manually from the History panel whenever you like.

### Address Book
- Save frequent contacts and reuse them when sending.
- Import or export entries for sharing/backup (Tools → Manage Address Book).

---

## Options you may want to set
Open System → Options.

- Polling Frequency: specifies how frequently (in minutes) FaxRetriever checks for new faxes.
- Download Format: specifies which file format you would like your faxes saved in. Choose from PDF, JPG, and TIFF.
- File Naming: Specifies the saved file name format. Choose from Fax ID or CID-DDMM-HHMM where the date and time stamp reflect the original receipt time of the fax.
- Print Faxes: prints received faxes automatically upon download.
- Enable Notifications: enables or disables Windows desktop notifications on issues or new fax.
- Close to Tray: when closed, FaxRetriever will continue running in the system tray. It will continue to retrieve faxes if it's setup to retrieve faxes.
- Start with System: starts FaxRetriever with Windows.
- Archive retention: how long to keep local copies of all inbound faxes (e.g., 30–365 days).
- Logging: choose how much detail is written to the rotating log file (applies immediately and is saved for next time).
- Enable 3rd Party Integrations: choose LibertyRx or Computer‑Rx/WinRx (only one can be active at once).

Behind the scenes
- Tokens are handled automatically and refreshed before they expire.
- Only one active retriever device per fax number is allowed to prevent duplicates.

---

## Integrations (optional)
You can enable exactly one integration at a time in System → Options → Integrations.

LibertyRx — forward inbound faxes
- Enter your Pharmacy NPI (10 digits) and 7‑digit API Key.
- When enabled, new inbound faxes are forwarded securely to LibertyRx. Very large faxes may be split into single pages for reliable delivery.
- You can choose whether to keep or remove local copies after a successful hand‑off.
- Tip: Your LibertyRx API Key can be created in Liberty RXQ/PharmacyOne → System → Settings → Utilities → API Keys (click Add).

LibertyRx — send from Liberty (Local Listener)
- New in 2.6: FaxRetriever can accept Liberty’s outbound fax POST over your LAN and send it using your selected caller ID.
- Enable in Options → Integrations → LibertyRx: check "Enable Sending from LibertyRx (Local Listener)" and choose the port (default 18761).
- Endpoints (on this workstation):
  - POST `http://<this-PC>:<port>/liberty/fax` with JSON `{ "faxNumber": "8174882861", "contentType": "application/pdf", "fileData": "<base64>" }` → returns `{ "id": "<uuid>" }`.
  - GET  `http://<this-PC>:<port>/liberty/faxstatus/<id>` (or `?id=<id>`) → returns `{ "status": "pending|success|error", "message?": "..." }`.
- Inbound Faxes (to Liberty): Set the "Save Location" in the main window to the network share monitored by your Liberty server. Faxes will be saved there as PDFs.
- Access control: access is open to any device on the network that can reach this port (default 18761). A Windows Firewall rule is created/requested when you enable the listener.
- Windows Firewall: the app will prompt for administrator approval to add an inbound rule allowing the chosen port from Any IP.
- Outbox & recovery: each posted PDF is saved to an Outbox for recovery at `{exe_dir}\LibertyRx\Outbox` or (fallback) `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\LibertyRx\Outbox`. Files are deleted automatically when a fax succeeds; failed items are purged after the retention window (default 72 hours).

Computer‑Rx/WinRx — automate outbound sends
- Select your WinRx folder and follow the prompts.
- FaxRetriever reads new items and sends them using your selected caller ID.
- If a number is invalid, you’ll be prompted to correct and resend.

---

## Tools
Convert PDF to JPG…
- Open Tools → Convert PDF to JPG…
- Pick one or more PDFs and an output folder.
- The app creates a subfolder per PDF and saves one JPG per page (e.g., mydoc_p001.jpg).

IT/Developers: If you see a message about Poppler or page counts while running from source, install PyMuPDF (`pip install pymupdf`) or set the `POPPLER_PATH` environment variable. Packaged builds include what’s needed.

---

## Where things are saved
- Global settings (all users on this PC):
  - shared\config\config.json
- Device/user settings (this Windows user):
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\config.json
- Download history ledger (prevents automatic re‑downloads):
  - shared\history\downloaded_faxes.log
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\downloaded_faxes.log
- LibertyRx Outbox (for Liberty outbound posts, if enabled):
  - {exe_dir}\LibertyRx\Outbox (preferred)
  - %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\LibertyRx\Outbox (fallback)
- Logs
  - log\ClinicFax.log (rotating)

Please don’t edit these files directly. Use the app’s Options instead.

---

## Troubleshooting
Can’t send
- Open Options and confirm Fax User and Authentication Token.
- Make sure a valid caller ID is assigned to you.
- See Help → View Log for details.

Not receiving
- Confirm the app is in Sender/Receiver mode.
- Click Configure Fax Retrieval and make sure this device is allowed for the number(s) you expect.
- Verify a Save Location is set and the drive/folder is available.
- Internet access and firewall rules can also block retrieval.

Tokens or sign‑in
- Tokens refresh automatically. If needed, close and reopen the app and re‑save Options.

Scanner issues (sending from paper)
- If you have more than one scanner, pick the correct one when prompted.
- Update or reinstall the scanner’s driver; unplug/replug to let Windows re‑detect.

LibertyRx Local Listener
- URI Format: Ensure the Liberty POST Endpoint is configured as a full URL starting with `http://` and using forward slashes (e.g., `http://192.168.1.10:18761/liberty/fax` or `http://192.168.1.10/liberty/fax`). Missing the `http://` or using backslashes `\` will cause a `System.UriFormatException` in Liberty.
- Can’t reach endpoint from Liberty server:
  - Verify the listener is enabled in Options → Integrations → LibertyRx.
  - Check the port (default 18761) and that a Windows Firewall rule exists; approve the elevation prompt when asked.
  - Port 80: If you choose port 80, you must run FaxRetriever as Administrator to allow the app to bind to a privileged port.
  - Ensure Liberty posts to `http://<this-PC>:<port>/liberty/fax`. Access is open to any device on the network that can reach this port (Windows Firewall rule is created on enable).
- 403 Forbidden:
  - This error should no longer occur as the IP allowlist has been removed. Check if the listener is truly active.
- 415 Unsupported Media Type:
  - `contentType` must be `application/pdf`.
- 400 Invalid payload/base64:
  - Ensure the JSON matches the spec and `fileData` is base64 for the PDF.
- 413 Payload too large:
  - Default maximum is 25 MB (configurable in Options). Send a smaller file or adjust the limit.
- Status stays pending:
  - For 2.6, `success` is reported once the telco accepts the fax; final delivery confirmation is not tracked yet.
- Files accumulating in Outbox:
  - Failed or unsent items are purged automatically after the retention window (default 72 hours). You can also resend manually using the saved PDFs.

---

## Privacy & security
- FaxRetriever never stores your provider username or password.
- Authentication tokens are managed automatically and refreshed as needed.
- Local configuration stores only device and app settings.

---

## FAQ
- Can multiple devices retrieve the same number?
  - No. To prevent duplicates, only one device can retrieve a number at a time. Any number of devices can send.
- Can I retrieve from multiple numbers?
  - Yes. Use Configure Fax Retrieval to select more than one.
- Can I change where faxes are saved?
  - Yes. Click Select Save Location at the top of the main window.
- Can faxes open automatically when received?
  - They don’t open automatically. You can enable printing or open them from your folder or History.

---

## Need more help?
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

Thank you for using FaxRetriever!
