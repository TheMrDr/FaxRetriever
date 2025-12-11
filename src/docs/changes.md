# FaxRetriever Changelog (What’s New)

This page summarizes changes in each version in simple, user‑friendly language. For detailed how‑to steps, see Help → Read Me (User Guide).

Tip: If an item mentions a menu path, it’s something you can change yourself in the app.

---

## 2.4.5 — 2025-12-10
- Fixed a rare startup crash that could happen if the destination number was blocked by the provider.
- Messages from the Computer‑Rx integration (for example, delivery updates or blocked destinations) are shown reliably even if they happen right as the app starts.
- Startup is more forgiving if some integration settings are missing.

---

## 2.4.4 — 2025-12-10
Computer‑Rx delivery tracking and safer retries
- FaxRetriever now tracks each Computer‑Rx outbound attempt and waits for a confirmed outcome before removing items from the WinRx queue. This helps avoid premature deletions and repeated sends.
- If a number becomes blocked after many failed attempts, you’ll see a clear warning and pending items are removed to prevent repeated attempts.
- Automatic retries happen up to 3 times by default; you can adjust this in Options if needed.

Logging and shutdown clarity
- Crashes and exits are recorded more clearly in `log\ClinicFax.log` so support can tell the difference between a normal close and an unexpected exit.

---

## 2.4.3 — 2025-12-10 and 2025-12-01
- New: System → Options → Logging lets you choose the minimum log level written to the log file. This reduces clutter in Help → View Log. Changes apply immediately and persist across restarts.
- Better small‑screen support: the main window fits on shorter displays and the Send Fax panel scrolls when space is tight.

---

## 2.4.2 — 2025-11-03
Tools → Convert PDF to JPG…
- Convert any selected PDF into JPG pages (one image per page), saved to a folder you choose. Good defaults are used for clarity and file size.

---

## 2.4.1
- Receiver startup now double‑checks your history with the server and fills in anything missing from previous sessions so already‑processed faxes aren’t downloaded again.

---

## 2.4.0
Multi‑part sending for large faxes
- When your attachments are too large for a single send, FaxRetriever automatically splits them into multiple parts and asks you to confirm before sending. Very large individual files may need to be split or compressed first.

---

## 2.3.1
- Fixed an issue that prevented LibertyRx licensing/credentials from being acquired in some cases.

## 2.3.0
LibertyRx integration (optional)
- Forward inbound faxes directly to LibertyRx. Enable in System → Options → Integrations, choose LibertyRx, and enter your Pharmacy NPI (10 digits) and 7‑digit API Key.
- Drop‑to‑send: Place PDFs in `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue` to forward them on the next poll.
- If a fax is too large, it is automatically split into single pages for delivery. You can choose whether to keep a local copy after a successful delivery.
- Help → View Log now opens your live log file from `log\ClinicFax.log`.

---

## 2.2.0
- Stronger protection against duplicates: once a fax is downloaded, it won’t be automatically re‑downloaded again. The app keeps a durable history so you don’t get duplicates across restarts or devices.
- History is stored in two safe places (shared and per‑user) and merged automatically.
- Fax History: The Download button now lets you pick PDF, JPG, or TIFF. Manual downloads are still allowed and recorded in history.

---

## 2.1.0
- Choose any combination of download formats (PDF, JPG, TIFF) in Options → Fax Retrieval.
- New: Save to multi‑page TIFF.
- The receiver skips a fax only if all the formats you selected already exist.
- Saving settings no longer switches you back to Sender‑only.

---

## 2.0.9
- The app only retrieves faxes when this device is Allowed for at least one number and is set to Sender/Receiver. When not allowed, retrieval controls are disabled to avoid mistakes.
- Easier scanner selection: you’ll see friendly device names when picking a scanner.

---

## 2.0.8
- Improved scanning reliability and better file sizes.
- Temporary files are cleaned up automatically after a short delay.

---

## 2.0.7
- You can launch FaxRetriever from a network share more reliably; the app will relocate itself to a safe local cache automatically while still using the shared configuration.
- Address Book works well for shared/network launches and saves safely when multiple users are involved.

---

## 2.0.6
- Default download format now falls back to PDF if nothing is selected, preventing a startup crash on fresh installs.

---

## 2.0.5
- Scanning chooses JPG when available, otherwise uses PDF. This removes the need for hard‑coded formats.

---

## 2.0.4
- Download history is saved consistently so previously downloaded faxes aren’t pulled again even after inbox cleanup.
- If you have only one scanner, it’s selected automatically; otherwise, you can choose from any installed device.

---

## 2.0.3
- Scan multiple pages in one go without clicking Scan for each page.
- The app now relaunches itself after completing an update.

---

## 2.0.2
- Updates are more reliable and happen at startup when a new version is available. Downloads are robust and won’t leave partial files.

---

## 2.0.1
- Replaced a PDF tool to reduce extra dependencies. No other changes.

---

## 2.0.0
A major update focused on reliability, ease of use, and a cleaner interface.
- Simpler sign‑in (tokens refresh automatically; your credentials are not stored)
- Clearer UI with at‑a‑glance status and manual Check for New Faxes
- One active retriever per number to avoid duplicates
- Better logging and built‑in troubleshooting cues
- Optional Computer‑Rx/WinRx integration