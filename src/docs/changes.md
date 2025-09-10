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

A typo in the download_methods would crash the application during new deployments when no download method was pre-specified. 
The change now defaults the system to PDF in the event that no download method is specified.

---

# What's new in FaxRetriever 2.0.5

The scanner operations were adjusted to remove hard-coded file formatting and will now dynamically query the scanner for 
file format options. Images are scanned in as .JPG if available, otherwise .PDF will be used.

---

# What's new in FaxRetriever 2.0.4

The fax history indexer was refactored to ensure that it saves the history to ./log instead of MEIPASS. This ensures that 
already-downloaded faxes are not redownloaded, even after being deleted from the fax inbox. Manual download is not impacted.

The scanner operations were enhanced to auto-select the system scanner if only 1 is present or to allow the user to select 
from any installed scanner if multiple scanners are present. This reduces user input when scanning documents. 

---

# What's new in FaxRetriever 2.0.3
The `scan_worker` was updated to allow scanning multiple pages in a single operation by replacing the single-page acquisition
with a multi-page loop using WIA. This change eliminates the need for users to click "Scan Document" for each page, and the 
output now aggregates all scanned paths into a list. The previous functionality for flatbed devices is preserved as a fallback.

Updates to the Auto Upgrade processes are intended to ensure that the application relaunches after successfully updating.

---

# What's new in FaxRetriever 2.0.2
The Auto Update process was improved by forcing a startup check for new versions, enhancing the GitHub API call with headers 
for reliability, and implementing a streaming download with atomic replace for updates. As a result, the system now performs u
pdates more effectively while retaining a 24-hour check gating for non-startup instances.

---

# What's New in FaxRetriever 2.0.1
Version 2.0.1 replaces PDFtoPPM with Fitz to reduce dependencies on 3rd party applications.
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