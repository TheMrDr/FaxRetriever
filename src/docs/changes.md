# FaxRetriever — What’s New (for everyone)

This changelog explains updates in simple, user‑friendly terms. For step‑by‑step how‑tos, see the User Guide (Help → Read Me) or `src/docs/readme.md`.

---

## 2.6.8 - Receiver Reliability Improvement (2026-01-21)
What's new
- Improved the reliability of the automatic fax retrieval process.
- Faxes are now only marked as "downloaded" in the ledger after all side effects (saving PDF/JPG/TIFF, printing, and third party integration forwarding) have successfully completed.

Why it matters
- Ensures that if the app is interrupted or encounters an error during processing, it will correctly retry downloading the "New" faxes on the next poll instead of skipping them.

## 2.6.7 - LibertyRx GET Parameter Case Insensitivity (2026-01-21)
What's new
- Added case-insensitive lookup for the `id` query parameter in the LibertyRx status GET endpoint.
- Now correctly handles variations like `Id` or `ID` when polling for fax status via `/liberty/faxstatus?id=...`.

Why it matters
- Resolves "unknown" status errors in LibertyRx caused by the system sending the job ID with different capitalization than the expected lowercase `id`.

## 2.6.6 - LibertyRx Key Case Insensitivity (2026-01-21)
What's new
- Added case-insensitive key lookup for LibertyRx POST payloads.
- Now correctly handles PascalCase keys (`FaxNumber`, `ContentType`, `FileData`) in addition to the standard camelCase keys.

Why it matters
- Resolves "415 Unsupported Media Type" and "400 Invalid Number" errors caused by LibertyRx sending field names with different capitalization than specified in their documentation.

## 2.6.5 - LibertyRx ContentType Tolerance (2026-01-21)
What's new
- Improved tolerance for LibertyRx POST requests with missing or empty `contentType` fields; the listener now defaults these to `application/pdf`.
- Added more detailed logging of received JSON keys when validation fails to assist in diagnosing integration issues.

Why it matters
- Resolves "415 Unsupported Media Type" errors when LibertyRx sends faxes without explicitly setting the content type in its payload.

## 2.6.3 - LibertyRx Spec Alignment (2026-01-21)
What's new
- Improved LibertyRx status GET endpoint to handle both path-based (`/liberty/faxstatus/ID`) and query-based (`/liberty/faxstatus?id=ID`) requests more robustly.
- Aligned status responses ('pending', 'success', 'error') and error messages with the LibertyRx integration specification.
- Ensured consistent behavior for both inbound and outbound LibertyRx flows.

Why it matters
- Ensures full compatibility with Liberty Software's faxing integration specification, providing clear delivery feedback and flexible integration options.

## 2.6.2 - LibertyRx Port 80 Support (2026-01-21)
What's new
- Added support for port 80 for the LibertyRx Local Listener.
- Updated the Endpoint URL helper to omit the port when port 80 is used (e.g., `http://192.168.1.10/liberty/fax`).
- Added friendly error messaging if starting the listener on port 80 fails due to missing Administrator privileges.

Why it matters
- Some external systems, including some LibertyRx configurations, may have trouble with non-standard ports in URIs. Using port 80 allows for a cleaner, standard URL.

## 2.6.1 - LibertyRx Local Lister and Outbox Recovery (2026-01-21)
What's new
- Improved handling and whitelisting of LibertyRx Listener
- Improved logging visibility for any issues encountered
- Added an additional UI element in the system settings to provide the correct URI endpoint

Why it matters
- Enahnces reliability and troubleshooting when attempting to send faxes from LibertyRx through FaxRetriever

## 2.6.0 — LibertyRx Local Listener and Outbox recovery (2026‑01‑08)
What’s new
- New LibertyRx Local Listener built into the desktop app. Liberty can POST a PDF over your LAN to this PC and FaxRetriever will send it using your selected caller ID.
- Clear, simple HTTP contract on the workstation:
  - POST `/liberty/fax` with `{ "faxNumber": "8174882861", "contentType": "application/pdf", "fileData": "<base64>" }` → `{ "id": "<uuid>" }`
  - GET  `/liberty/faxstatus/<id>` (or `?id=<id>`) → `{ "status": "pending|success|error", "message?": "..." }`
- Outbox persistence for recovery: each posted PDF is saved locally and deleted automatically on success. Failed items are purged after a retention window (default 72 hours).
- Safer by default on a LAN: access is open to any device that can reach the chosen port (default 18761). The app prompts to add a Windows Firewall rule (admin approval) for the chosen port on first enable.
- Options → Integrations → LibertyRx now includes “Enable Sending from LibertyRx (Local Listener)” and a port setting (default 18761).

Why it matters
- Keeps all fax content on your workstation (Admin/FRA never touches the PDF), meets Liberty’s contract, and makes deployment fast for on‑prem pharmacies.

How to use it
- Open System → Options → Integrations → choose LibertyRx.
- Check “Enable Sending from LibertyRx (Local Listener)” and keep port 18761 (or adjust).
- On first enable, the app resolves `LibertyServer`; if not found, you’ll be asked to enter the server’s IP. Approve the firewall prompt.
- Configure Liberty to POST to `http://<this-PC>:<port>/liberty/fax` and poll `/liberty/faxstatus/<id>`.

---

## 2.5.0 — Clear delivery status and the Outbox (2026‑01‑07)
What’s new
- New Outbox tab shows everything you’ve sent and where it stands: Accepted (in‑flight), Delivered, Failed Delivery, Invalid Number, Quarantined, or Delivery Unknown (no final result after a day).
- You’ll get a small pop‑up when a fax is accepted for sending and another when a final result is known.
- If a number from Computer‑Rx/WinRx is missing/ambiguous, we stop it safely, move the PDF to `WinRx\FaxRetriever\Failed`, and show a friendly correction window so you can fix the number and resend.
- Failed sends try again a few times and then move to Quarantined so you can decide what to do next.
- Cover Sheet: Replaced the “Add a little…” footers with a new, more business-appropriate, “Configure Custom Footer” with a text area; when off or empty, the default footer “The remainder of this page is intentionally left blank.” is used.

Why it matters
- You can see at a glance what happened to each fax and quickly retry if needed.
- Fewer surprises and easier recovery when a number is wrong or a delivery fails.
- Simpler by default with optional customization of the cover sheet footer — no more randomized/silly messages.

How to use it
- Open the Outbox tab in the main window.
- Use the row actions: View PDF, Open Folder, Retry/Send (enabled when the original PDF is available), or Remove.
- To customize the cover footer: in Send Fax → Configure Cover Sheet, check “Configure Custom Footer” and enter your text; leave it off to use the default footer.

---

## 2.4.3 — Two small improvements (2025‑12‑10 and 2025‑12‑01)
- Logging control (Dec 10): System → Options → Logging lets you choose how much detail goes to the rotating log file. Your choice applies immediately and is remembered.
- Small‑screen support (Dec 1): The main window fits better on short displays; the Send Fax panel scrolls so controls don’t get cut off.

Why it matters
- Easier troubleshooting when needed, and a better fit on smaller monitors.

---

## 2.4.2 — Convert PDF to JPG tool (2025‑11‑03)
What’s new
- Tools → Convert PDF to JPG… turns any PDF into one JPG per page and saves them in a subfolder (e.g., `mydoc_p001.jpg`).

Why it matters
- Quickly create page images for systems that prefer JPGs.

Tip
- Packaged builds include everything you need. If you’re running from source and see a message about Poppler/page counts, install PyMuPDF (`pip install pymupdf`) or set `POPPLER_PATH`.

---

## 2.4.1 — Keeps your download history in sync
What’s new
- If server history is ever lost, the app rebuilds it from your local records and re‑posts anything missing.

Why it matters
- The app won’t accidentally re‑download old faxes. Your “already handled” list stays intact.

---

## 2.4.0 — Large faxes send in parts automatically
What’s new
- When attachments are too large to send in one go, the app splits them into multiple sessions for you. Oversize individual files are detected up front with clear guidance.
- The first session can include a cover note indicating it’s a multi‑part fax.

Why it matters
- Big faxes go through reliably without you having to split files manually.

---

## 2.3.1 — LibertyRx credentials fix
- Fixed an issue that could block LibertyRx setup for some users.

---

## 2.3.0 — LibertyRx forwarding
What’s new
- Inbound faxes can be forwarded securely to LibertyRx. Turn it on in System → Options → Integrations and enter your Pharmacy NPI (10 digits) and 7‑digit API Key.
- Optional “drop‑to‑send” folder lets you place PDFs at `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue` for the next poll.
- Very large faxes are split into pages if needed. You can choose to keep or purge local copies after a successful hand‑off.

Why it matters
- Saves time by moving faxes straight into your pharmacy workflow.

---

## 2.2.0 — Never auto re‑download the same fax twice
What’s new
- A durable “downloaded” ledger records faxes you’ve already pulled, stored in two safe places on disk.
- History → Download now offers PDF, JPG (one per page), or multi‑page TIFF.

Why it matters
- Reliability. Once handled, a fax won’t be pulled again automatically, even across restarts.

---

## 2.1.0 — More download formats and smarter receiving
What’s new
- Choose any combination of PDF, JPG, and TIFF in Options.
- The receiver skips a fax only when all your selected outputs already exist.

Why it matters
- You get exactly the files you need without duplicates.

---

## 2.0.9 — Clear authorization for receiving
- The app only retrieves when this device is set to Sender/Receiver and is allowed for at least one number. Controls are disabled when not authorized so it’s obvious what’s happening.

Why it matters
- Prevents accidental duplicate downloads and confusion over who’s retrieving.

---

## 2.0.8 — Better scanner compatibility
- Switched to a more compatible scanning method and improved image quality/size. Temporary files are cleaned up automatically.

---

## 2.0.7 — Reliable when launched from a network share
- If you run the app from a network drive, it transparently runs from a safe local cache but keeps using the shared configuration and address book so all users stay in sync.

---

## 2.0.6 — Safe default download format
- If no download format was set previously, the app safely defaults to PDF.

---

## 2.0.5 — Smarter scanner file type
- Scans use JPG when available, otherwise PDF.

---

## 2.0.4 — Stable history and easier scanner selection
- History is saved in a stable place so already‑downloaded faxes aren’t pulled again.
- If only one scanner is installed, it’s selected automatically; otherwise you can pick from a friendly list.

---

## 2.0.3 — Scan multiple pages at once
- You can now scan several pages in one go. The auto‑update process was also improved so the app restarts cleanly after updates.

---

## 2.0.2 — More reliable updates
- Startup checks for new versions and a safer download/install process.

---

## 2.0.1 — Fewer dependencies
- Switched to a built‑in PDF renderer, reducing reliance on external tools.

---

## 2.0 — Big refresh focused on reliability and ease of use
Highlights
- Clearer interface with at‑a‑glance status.
- Better protection against duplicate downloads.
- Streamlined Send Fax with previews and optional cover page.
- Automatic sign‑in handling behind the scenes.

See the User Guide (Help → Read Me) for a full walkthrough.