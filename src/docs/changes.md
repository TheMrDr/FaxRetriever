# FaxRetriever — What’s New (for everyone)

This changelog explains updates in simple, user‑friendly terms. For step‑by‑step how‑tos, see the User Guide (Help → Read Me) or `src/docs/readme.md`.

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