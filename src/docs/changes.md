# What's new in FaxRetriever 2.4.5 (2025-12-10)

- Stability: Fixed a startup crash that could occur when SkySwitch returned HTTP 400 indicating a blocked destination number during initialization.
  - Introduced a thread-safe UI notifier that marshals background-thread notifications to the main UI thread.
  - Notifications raised by the Computer-Rx integration (blocked number, delivered, failed-after-3) are now shown safely without cross-thread UI access.
  - If the UI isn’t ready yet, messages are queued and shown once the main window is displayed; events are always logged.
  - Defensive defaults were added around integration settings to avoid missing-key errors at startup.

---

# What's new in FaxRetriever 2.4.4 (2025-12-10)

- Computer-Rx delivery tracking and anti-blacklisting:
  - Deferred deletion on HTTP 200 (queued). The app now records each CRx outbound attempt in a durable, device-scoped ledger and waits for a confirmed delivery outcome from outbound history before removing the WinRx queue item.
  - Background poller correlates outbound history and updates outcomes. On delivery failure, it retries automatically; after 3 failed deliveries, it notifies the user and removes the Btrieve record and associated file.
  - Immediate blocked-number handling: If SkySwitch reports the destination is blocked (e.g., due to many failed attempts), the app warns the user to investigate in WinRx and removes pending records to prevent repeated attempts.
  - Settings (optional): `enable_crx_delivery_tracking` (Yes), `crx_poll_interval_sec` (60), `crx_max_attempts` (3). The poller starts when CRx is enabled and stops on app exit.
  - Transparent logs for attempts, correlations, outcomes, and cleanup.

- Logging and crash visibility:
  - Centralized crash/exit handlers capture unhandled exceptions from the main thread and background threads with full tracebacks in `log/ClinicFax.log`.
  - Process shutdown is recorded via an `atexit` hook, and Qt lifecycle is logged (`QApplication.aboutToQuit`).
  - The application now logs the main loop exit code after the UI closes.
  - User-driven closures are clearly annotated: normal window close, Close to Tray, Receiver-mode prompt choices (Minimize to Tray / Close Anyway / Cancel), and Quit via tray menu. This helps distinguish intentional exits from crashes during support.

---

# What's new in FaxRetriever 2.4.3 (2025-12-01)

- UI: Improved small-screen support. The main window minimum height was reduced and the Send Fax panel now scrolls when vertical space is limited. This prevents controls from being cut off on displays shorter than 950px.

---

# What's new in FaxRetriever 2.4.3 (2025-12-10)

- Log level control: System → Options → Logging now lets you choose the minimum level written to the rotating log file. When you pick a level (Info, Warning, etc.), only messages at that level and above are persisted. This reduces clutter in Help → View Log.
- Immediate effect: Changing the selection applies at runtime without restart. The choice is also saved and re-applied on next launch.

---

# What's new in FaxRetriever 2.4.2 (2025-11-03)

- New tool: Tools → Convert PDF to JPG...
  - Convert any selected PDF(s) into JPG pages, saved one image per page.
  - Output naming: <pdf_basename>_p001.jpg, _p002.jpg, ... in a per-PDF subfolder under your chosen output folder.
  - Uses bundled Poppler automatically when available; defaults to 200 DPI and JPEG quality 90 for a good balance of clarity and size.

---

# What's new in FaxRetriever 2.4.1
We need to
- Reliability: Automatic history reconciliation on receiver startup ensures the server-side per-domain download history is recreated and synchronized from your existing local cache if it was ever lost. The app now:
  - Rebuilds local history from the server when the local ledger is empty.
  - Pushes local-only FaxIDs to the server to recreate the per-domain history document if it was dropped.
  - Flushes any queued history posts after connectivity/auth issues.
- Server alignment: FRAAPI now provides /sync/post and /sync/list with JWT scope history.sync and stores history in a single document per domain. Legacy per-fax documents are no longer used by the API.

---

# What's new in FaxRetriever 2.4.0

- New: Automatic multi-session outbound sending when combined attachments exceed the upstream 10 MiB session cap. Sessions are sized conservatively (target ≤ 9.9 MiB including multipart overhead) and sent sequentially.
- Policy: Enforce a per-file size rule — individual files ≥ 9.5 MiB are rejected up front with user guidance to split or compress.
- Indicators: Session 1 includes a cover sheet annotated with “Multi-part Fax — Session 1 of N”. Sessions 2..N begin with a compact “Continuation — Session i of N” page (when ReportLab is available). If ReportLab is unavailable, the send proceeds without these pages.
- Transparency: Before sending, if a fax will be split into multiple sessions, the UI informs the user and allows Cancel or Proceed.
- Reliability: Clear per-session logging (attempts, successes/failures) and robust cleanup of temporary normalized and generated files.

---

# What's new in FaxRetriever 2.3.1

- Fix: A small typo on the LibertyRx integration prevented proper license and credential acquisition.

# What's new in FaxRetriever 2.3.0

- LibertyRx forwarding: Inbound faxes can be forwarded directly to LibertyRx. Enable in System → Options → Integrations, choose LibertyRx, and enter your Pharmacy NPI (10 digits) and 7‑digit API Key. Vendor authorization is fetched securely and stored encrypted.
- Drop‑to‑send: You can drop PDFs into the Liberty queue folder to send them on the next poll: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue. Files are removed automatically after a successful handoff (HTTP 200).
- Caller ID from filename (optional): If the dropped PDF name starts with 11‑digit CID using CID‑DDMM‑HHMM (or CID‑DDMMYY‑HHMMSS), that CID is used as FromNumber. Otherwise your selected caller ID is used.
- Keep or purge local copies: When enabling LibertyRx, you can choose whether to keep local copies after a successful Liberty delivery. If you choose No, FaxRetriever purges the local PDF/JPG/TIFF for that fax after a 200 OK from Liberty.
- Clear delivery visibility: Logs now include LibertyRx actions and results (attempts, success, 401/413 handling). See log\ClinicFax.log.
- Robust delivery: Automatic retries with exponential backoff; if Liberty returns 413 (file too large), FaxRetriever splits the PDF into pages and delivers them individually.
- Tip: To obtain your LibertyRx API Key: In Liberty RXQ/PharmacyOne → System → Settings → Utilities → API Keys, click Add to generate a random key. Use this key for Clinic Networking Faxing.
- Fix: Help → View Log now opens and streams the live rotating log from the app folder next to FaxRetriever.exe (log\ClinicFax.log) instead of a temporary path.

---

# What's new in FaxRetriever 2.2.0

- Critical reliability: FaxRetriever will never automatically re-download a fax that has been downloaded before. We replaced the fragile JSON map with an immutable, append-only ledger of FaxIDs stored on disk with flush+fsync durability. This guarantees that once a fax is recorded as downloaded, it will not be auto-downloaded again across restarts and environments.
- Dual-location ledger for resilience: The downloaded-fax ledger is written to two stable locations and merged on read: (1) shared\history\downloaded_faxes.log in the app's shared folder, and (2) %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\downloaded_faxes.log per Windows user. On first run, legacy JSON indices are migrated into the new logs and any divergence is synchronized both ways.
- Receiver integration hardened: The receiver now marks FaxIDs as downloaded in additional paths to close remaining gaps. Specifically, when the local PDF already exists (no new download needed) and when all requested output formats (PDF/JPG/TIFF) are already present and the fax is skipped. These safeguards ensure previously processed faxes are always recorded in the ledger.
- Backwards compatible APIs: The public history_index API (is_downloaded, mark_downloaded, load_index/save_index) is preserved; no UI changes are required. Manual, user-initiated downloads remain possible even if a fax is in the ledger.
- Local cleanup parity: Inbox cleanup continues to cover PDF/JPG/TIFF files according to retention settings.
- Fax History: The Download button on each history card is now a dropdown with PDF, JPG, or TIFF options. JPG saves one file per page (prefix-1.jpg, -2.jpg, ...); TIFF saves a single multi-page .tiff. Manual downloads are recorded in the ledger.

---

# What's new in FaxRetriever 2.1.0

- New: Multi-format download selection. In Options → Fax Retrieval, the PDF/JPG/Both radio buttons were replaced with three checkboxes: PDF, JPG, and TIFF. Users can select any combination. Legacy configurations with "Both" are automatically mapped to PDF + JPG.
- New: Multi-page TIFF support. Inbound fax PDFs can now be converted to multi-page .tiff files. Rendering uses PyMuPDF (in-app) and saving uses Pillow with Group 4 compression (fallback to LZW when needed).
- Receiver behavior refined for multi-format outputs: the engine skips a fax only if all requested outputs already exist; it avoids re-downloading when the PDF is already present, performs the requested conversions (JPG and/or TIFF), and removes the PDF if it isn’t selected and printing is disabled. Local cleanup now includes .tiff/.tif files.
- Stabilized inbound deduplication index location to prevent accidental re-downloads when the app is launched from a different working directory (e.g., via a scheduler). The downloaded_index.json now always lives under <base_dir>\\log regardless of CWD; existing indexes are migrated automatically from prior locations.
- Saving Options no longer resets the app to Sender-only. The current retrieval mode (Sender or Sender/Receiver) is preserved when updating settings.
- Status bar save message simplified to "Settings saved." to avoid implying a mode change.
- Minor Options refinements: improved startup shortcut handling (Start with System), persisted printer preferences per device, and integration settings mirrored to device scope for runtime gating.

---

# What's new in FaxRetriever 2.0.9

- Enforced receiver authorization: FaxRetriever will never retrieve faxes unless the device is configured as Sender/Receiver and the FRA assignments indicate this device is Allowed to retrieve for at least one number.
- Manual and scheduled polling now respect authorization and are disabled when not permitted.
- Startup and UI improvements clarify current authorization: retrieval controls are greyed out and the poll timer is stopped when unauthorized; logs indicate the current mode and status.
- Reliability: Added guards in the receiver engine and poll triggers to prevent inadvertent downloads.
- Scanner selection dialog now shows friendly device names (Vendor + Model) instead of GUID/USB identifiers, making it easier to pick the correct scanner when multiple are installed.

---

# What's new in FaxRetriever 2.0.8

- Scanner refactored to use pyinsane2 instead of direct WIA calls. This should resolve issues with scanners failing to scan on some systems.
- Scanned pages are now optimized for size and quality using a combination of color-limiting and compression.
- Added delayed cleanup to remove temporary fax files after 5 minutes, preventing disk bloat and improving stability.

---

# What's new in FaxRetriever 2.0.7

- Added a startup bootstrap that transparently copies the executable to a trusted local cache when launched from a network path (UNC or mapped drive) and relaunches from there. This allows launching FaxRetriever.exe directly from SMB shares without ordinal/DLL loader errors on some systems. No behavior change when the app is started from a local disk or during development.
- The app now continues to use a shared global configuration (shared/config/config.json) located on the original network share even after relocating the EXE to the local cache. At bootstrap, the original launch root is persisted and passed to the relaunched process; the configuration loader resolves the shared config via that origin, environment overrides (FR_GLOBAL_CONFIG_FILE/FR_GLOBAL_CONFIG_DIR), or falls back to process/repo-relative locations. This ensures all clients read the same global_config and any changes are reflected across devices on next reload/startup.
- Address Book is now shared across clients when launching via SMB/network share. The address_book.json will be resolved in this priority: FR_ADDRESS_BOOK_FILE/FR_ADDRESS_BOOK_DIR override, then the original network root (FR_ORIGINAL_ROOT or origin.path), then process/repo/CWD. Saves are atomic to avoid corruption when multiple clients write concurrently.
- Build: Disabled UPX packing for the Windows EXE. On some systems, UPX-compressed binaries launched from SMB can fail early in the loader with ordinal/DLL errors (e.g., ordinal 380). Disabling UPX eliminates this class of issues while having minimal impact on file size/performance.

---

# What's new in FaxRetriever 2.0.6

- A typo in the download_methods would crash the application during new deployments when no download method was pre-specified. 
- The change now defaults the system to PDF in the event that no download method is specified.

---

# What's new in FaxRetriever 2.0.5

- The scanner operations were adjusted to remove hard-coded file formatting and will now dynamically query the scanner for 
file format options. Images are scanned in as .JPG if available, otherwise .PDF will be used.

---

# What's new in FaxRetriever 2.0.4

- The fax history indexer was refactored to ensure that it saves the history to ./log instead of MEIPASS. This ensures that 
already-downloaded faxes are not redownloaded, even after being deleted from the fax inbox. Manual download is not impacted.

- The scanner operations were enhanced to auto-select the system scanner if only 1 is present or to allow the user to select 
from any installed scanner if multiple scanners are present. This reduces user input when scanning documents. 

---

# What's new in FaxRetriever 2.0.3
- The `scan_worker` was updated to allow scanning multiple pages in a single operation by replacing the single-page acquisition
with a multi-page loop using WIA. This change eliminates the need for users to click "Scan Document" for each page, and the 
output now aggregates all scanned paths into a list. The previous functionality for flatbed devices is preserved as a fallback.

Updates to the Auto Upgrade processes are intended to ensure that the application relaunches after successfully updating.

---

# What's new in FaxRetriever 2.0.2
- The Auto Update process was improved by forcing a startup check for new versions, enhancing the GitHub API call with headers 
for reliability, and implementing a streaming download with atomic replace for updates. As a result, the system now performs u
pdates more effectively while retaining a 24-hour check gating for non-startup instances.

---

# What's New in FaxRetriever 2.0.1
- Version 2.0.1 replaces PDFtoPPM with Fitz to reduce dependencies on 3rd party applications.
No additional changes have been made.

---

# What’s New in FaxRetriever 2.0

Welcome to FaxRetriever 2.0 — a major update focused on reliability, ease of use, and a cleaner interface. Here’s what’s changed and why it matters to you.

If you’re new to FaxRetriever, open Help → Read Me (User Guide) for a full walkthrough.

---

## Highlights
- Modern, clearer user interface with at‑a‑glance status
- Stronger protection against duplicate downloads (one retriever per number)
- Streamlined Send Fax with preview and optional cover page
- Automatic, behind‑the‑scenes sign‑in token handling
- Improved logging and built‑in troubleshooting cues
- Optional Computer‑Rx/WinRx integration

---

## Simpler, Safer Sign‑In
- Tokens are handled automatically and refreshed before they expire
- Your provider credentials are not stored in the app
- Progress bars show token life and next poll time so you always know what’s happening

Why you’ll like it:
- Fewer interruptions from expired sessions
- Stronger privacy and security with less to manage

---

## One Device per Number (to prevent duplicates)
- Each fax number can have a single active “retriever” device at a time
- Use the `Configure Fax Retrieval` button to claim or release numbers
- Easily move retrieval responsibilities to a different workstation when needed

Result: No more accidental duplicate downloads.

---

## A Cleaner, More Helpful UI
- Top header includes:
  - Save Location field and button
  - Configure Fax Retrieval
  - Check for New Faxes (manual poll)
  - Two progress bars: Token Lifespan and Next Poll
- Send Fax panel enhancements:
  - Multi‑page PDF/image preview
  - Optional cover page (Attention, Memo, etc.)
  - Number normalization (digits only)
- Help menu:
  - Read Me (User Guide)
  - What’s New
  - About

All Help documents open in a modeless (non‑blocking) window so you can keep working.

---

## Reliability & Control for Receiving
- Clear indicators for token status and next poll time
- Manual polling available any time with `Check for New Faxes`
- Save Location front‑and‑center to avoid surprises
- Options (System → Options):
  - Archive retention (30–365 days)
  - Print on receipt
  - Delete from server after successful download

---

## Integrations (Optional)
- Computer‑Rx/WinRx support can be enabled in Options
- When enabled, FaxRetriever can poll WinRx for prescription refills and fax them automatically
- First‑time setup helps you choose the correct pharmacy path and validates required files

---

## After You Update
1) Open the app and go to `System` → `Options` to confirm your Fax User and Authentication Token
2) Click `Configure Fax Retrieval` to ensure the right numbers are claimed for this device
3) Verify your Save Location and any desired options (archive, printing)

You’re ready to go.

---

## Need Help?
- Phone: 405-300-0122
- Email: info@clinicnetworking.com
- Web: https://ClinicNetworking.com

Thank you for using FaxRetriever 2.0!