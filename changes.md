# 🚀 FaxRetriever Update - Version 1.18.04  
*Released: 03/27/2025*  

## 🧠 **Memory Fixes & Performance Optimizations**

- 🗑️ **Temp File Cleanup Fix**  
  - Resolved an issue where **temporary files were not being properly cleaned up** when sending faxes repeatedly.  
  - This fix **prevents previously sent messages from being resent unintentionally**.

- ⚙️ **Optimized Imports Across the Application**  
  - Cleaned and streamlined **import statements** throughout the codebase.  
  - Slightly improves application load times and overall performance.  

---

# 🚀 FaxRetriever Update - Version 1.18.03  
*Released: 03/24/2025*  

## ✅ **Scanner & PDF Processing Fixes**  

### 🖨️ Scanner Improvements  
- Fixed bug causing **duplicate “Select Scanner” dialogs** when multiple scanners are installed.  
- Scanner selection is now handled in the **main thread** and passed cleanly to the background scan thread.  
- Removed deprecated `force_reload=True` parameter from `pyinsane2.get_devices()` to restore **scanner detection on 32-bit builds**.  
- Properly using `pyinsane2.exit()` and `pyinsane2.init()` to refresh the WIA device list safely.  

### 📄 PDF Compatibility & Stability  
- Replaced deprecated `rotate_clockwise()` with `rotate()` in `normalize_pdf_to_portrait()` to fix **landscape page rendering**.  
- Fixes 0-byte PDF creation issues and ensures **full preview support** for all valid PDF files.  

---

# 🚀 FaxRetriever Update - Version 1.18.01  
*Released: 03/19/2025*  

## 🛠️ **Bug Fixes & Minor Improvements**  
- **Send Fax Window Fixes**:  
  - The **Send Fax** window now properly clears and resets when a fax is successfully sent or when the window is closed.

---


# 🚀 FaxRetriever Update - Version 1.18.00  
*Released: 03/17/2025*  

## 🎉 **Official Support for Computer-Rx/WinRx Integration!**  
- When **integration is enabled** from **System Settings**, FaxRetriever will **automatically poll WinRx** for any prescription refills and send them **without user intervention**.  
- This means **fully automated fax processing** for prescription refills—no manual input needed!  

## 🛠️ **Bug Fixes & Minor Improvements**  
- **Options Menu Fix**:  
  - **Print Faxes** setting now properly retains its checked state when the app is restarted.  

---

# 🚀 FaxRetriever Update - Version 1.17.01  
*Released: 03/13/2025*  

## 🛠️ **Bug Fixes & Improvements**  
- **Fixed UI Icon Issues**:  
  - Address Book button icons now properly load.  
  - All custom popup windows now correctly display their icons.  

- **Enhanced Computer-Rx Integration**:  
  - Added support for **Pervasive v10**.  
  - When multiple pharmacy paths are detected, the user is prompted to select the correct one.  
  - Validation is performed to ensure all required files exist.  

- **Options Menu Fixes**:  
  - Resolved an issue where **Print Faxes** was incorrectly enabled when **Archive Faxes** was selected.  

- **Improved Fax Retrieval & Archival**:  
  - Prevents re-downloading already archived faxes.  
  - Enhanced logic to check both **Archive** and **Destination folders** before downloading.  
  - Faxes are now archived under `C:\Clinic Networking, LLC\FaxRetriever\Archive` in a structured **Year → Month → Day → Hour** format.  

- ✅ **Code Cleanup & Stability Enhancements**  

---

# 🚀 FaxRetriever Update - Version 1.17.00  
*Released: 03/08/2025*  

## 🔄 **Major Architecture Change - Now 32-Bit for Better Compatibility!**  
- FaxRetriever has been **recompiled from 64-bit to 32-bit** to ensure **better interoperability with third-party integrations**.  
- This change **improves compatibility** with external software and legacy systems.  
- **Reduced program size by nearly 25%!** The switch to 32-bit results in a **smaller, more efficient application**.  
- **No functionality loss** – everything works the same, just with broader support!

---

## 🌟 **New Features & Enhancements**  

### 📇 **Address Book Added!**  
- Now accessible inside the **Send Fax** window.  
- Save frequently-used fax numbers for quick selection.  
- Import and export contacts for easy backup and sharing.  

### 📜 **View System Logs in Real Time**  
- Added a new **View Log** option under the **Help** menu.  
- Monitor the system log **live**, making troubleshooting **easier than ever!**  

### 📂 **Improved Archival Process**  
- **Better error handling, logging, and cleanup functionality**.  
- Archival storage is now **more efficient**, reducing unnecessary disk usage.  

### 🔌 **Third-Party Integrations - Beta Begins!**  
- The **first phase of integrations** is here, starting with **Computer-Rx** in **testing mode**.  
- **How to Enable:**
  1. Navigate to **System → Options**.  
  2. Select **Enable 3rd Party Integrations**.  
- **More vendors coming soon** – Let us know which integrations **you** want to see!  

### 🎨 **Refined Options Menu & UI Enhancements**  
- **System Options menu redesigned** for a **cleaner, more organized layout**.  
- **Smaller main window banner** – (previously, branding took up over **60% of the UI** 😬).  
- **More status messages** to keep users informed of what’s happening **in real-time**.  

### 📥 **Improved Fax Retrieval**  
- Ensures **only new, undownloaded faxes** are retrieved.  
- **Deletes faxes from the server** correctly (if "Delete Faxes" is enabled in settings).  

### 💾 **Better Save Management & Access Tokens**  
- Eliminated **unnecessary calls** to invalid settings.  
- **More detailed status messages** during token retrieval and error handling.  
- **Enhanced save file logic** to prevent **null or missing values**.  

## 🛠️ **Behind-the-Scenes Improvements**  
- **Optimized internal code structure** for better performance.  
- Cleaned up **tons of old comment blocks** to make the app **smaller and more efficient**. 

---

# 🚀 FaxRetriever Update - Version 1.16.03  
*Released: 02/10/2025*  

## 🛠️ **Minor Bug Fix**  
- Fixed an issue where **undefined archival settings** could cause the archival module to fail.  
- This update **prevents unnecessary error popups** when saving faxes.  

---

# 🚀 FaxRetriever Update - Version 1.16.02  
*Released: 02/10/2025*  

## 🛠️ **Bug Fixes & Improvements**  
- 🕒 **System Time Zone is now properly detected** for fax archival, ensuring accurate retention periods.  
- ❌ **Faxes now properly delete from the server** after being downloaded (if enabled in settings).  

---

# 🚀 FaxRetriever Update - Version 1.16.01  
*Released: 02/07/2025*  

## 🔹 **Fax Status Button is Now Enabled!**  
- Users can now **access the Fax Status tool** from the toolbar.  
- View **sent and received fax history** directly from within the app.  
- 💡 *Heads up: The UI needs some love—it’s functional but overdue for a redesign!* Stay tuned for future improvements!  

---

# 🚀 FaxRetriever Update - Version 1.16.00  
*Released 02/07/2025*

## 🔥 **Computer-Rx Users, This One is for You!** 🔥  
We've introduced **new file naming options** that will **eliminate extra work** and make managing faxes easier than ever!  

### 📂 **New File Naming Conventions**
- **Choose how your faxes are named!** You now have two options:
  - **Fax ID (Default)** – Uses the original numeric fax ID.
  - **CID-MMDD-HHMM Format** – A **detailed, structured naming system** including:
    - **CID** – Caller ID of the sender.
    - **MMDD** – Month and day the fax was received.
    - **HHMM** – Hour and minute the fax was received.
- **No more renaming faxes manually!** This update is designed **specifically for Computer-Rx users** who need a **clearer, more structured file system**.

💡 **Interested in integrating incoming faxes directly into your pharmacy management software?**  
Contact us for assistance in configuring this service and streamlining your workflow.

## 🛠️ **Revamped Options Menu**
- The **Options Menu** has been **completely restructured** for a **cleaner, more organized layout**.
- **Easier navigation** and **clearer settings** for better user experience.

## 🗄️ **Optimized Fax Archival**
- Adjustments have been made to **prevent duplicate downloads**.
- **Reduces unnecessary disk space usage** by ensuring unique file storage.

## 🛠️ **New Tools in the Tools Menu**
- **📄 Convert PDF to JPG** – Instantly convert any **PDF** into a **JPG image**.
- **🖼️ Convert JPG to PDF** – Convert **JPG images** back into a **PDF format**.
- These tools allow **quick conversion** between fax file formats.

---

# 🚀 FaxRetriever Update - Version 1.15.04

## 🖨️ **Reworked Scanning Module in Send Fax**
- Now supports **both WIA and TWAIN scanners** with **automatic switching** between the two.
- Improved **UI for the scanning utility**, making it more intuitive and user-friendly.
- Faster and more reliable scanning experience for faxing documents.

---


# 🚀 FaxRetriever Update - Version 1.15.03

## 🛠️ **Bug Fixes & Stability Improvements**
- Fixed **Options menu population** to ensure proper loading and display.
- Archival settings now correctly define and retain variables.
- Settings now properly **save across sessions** without resets.
- **Faxes now correctly delete from the server** when deletion is selected.

---

# 🚀 FaxRetriever Update - Version 1.15.02

## 🛠️ **Minor Bug Fixes**
- Fixed an import issue in **Options menu**.
- Other minor stability and reliability improvements.

---

# 🚀 FaxRetriever Update - Version 1.15.01

## 🆕 **Expanded Fax Archival Options**
- 📂 **Fax archival durations now include additional options**:
  - 🗂️ **120 days**
  - 🗂️ **365 days**
- 🔹 *This feature is available in System → Options → Fax Retrieval Settings → Archival.*

---

# 🚀 FaxRetriever Update - Version 1.15.00

## 🎉 What's New?
- ⚡ **Code Optimizations**: Performance improvements for a smoother experience.
- 📂 **Fax Archival Feature**: You can now automatically archive faxes for **30, 60, or 90 days**.
- 📄 **Automatic Page Orientation**: Landscape pages inside outbound PDFs now send correctly without distortion.
- 🖥️ **Reworked Send Fax Screen**: A brand-new, more intuitive interface for sending faxes!
- 🖼️ **Interactive Document Preview**: View multi-page documents **before sending**.
- 🎨 **UI Enhancements**: More clarity, better layout, and an improved experience.
- 📖 **Coming Soon: Address Book** - A smarter way to manage your fax contacts!

---

## 🆕 **Major UI Overhaul - Send Fax Screen**
### 🖥️ **Cleaner, More Intuitive Layout**
- The **Send Fax** screen has been **completely redesigned** for clarity and ease of use.
- 📂 **Documents are now displayed in a preview window** (except for .doc/.docx files).
- Users can **switch between pages** for **multi-page documents**.
- **Improved button layout** for faster and easier faxing.

---

## 📂 **New Document Preview**
- 📄 **See your document before you send it!**
- Navigate **multi-page PDFs, TIFFs, and images** using **next/previous buttons**.
- **No more surprises**—send exactly what you intend to fax.

---

## 📂 **Fax Archival - Keep Your Faxes Longer**
- You can now **automatically archive received faxes** for:
  - 🗂️ **30 days**
  - 🗂️ **60 days**
  - 🗂️ **90 days**
  - 🗂️ **120 days** (*New in 1.15.01!*)
  - 🗂️ **365 days** (*New in 1.15.01!*)
- **How to Enable**:
  1. Go to **System → Options**.
  2. Navigate to **Fax Retrieval Settings**.
  3. Select your desired **archival duration**.
- **Where are Archived Faxes Stored?**  
  📁 **C:\Clinic Networking, LLC\FaxRetriever\Archive**
- 🔹 *This feature is only available on instances where fax retrieval is enabled.*

---

### 📄 **Improved PDF Handling - Correct Landscape Page Orientation**
- ✉️ **Outbound faxes now properly handle landscape pages!**
- Previously, all uploaded PDFs were **forced into portrait mode**, causing landscape pages to appear **squashed and illegible**.
- 📌 **Now fixed!** Landscape pages inside outbound PDFs will be **automatically detected and sent in the correct orientation**.

---

## 🛠️ **Code Optimizations**
- ✅ Various **performance improvements** for faster fax processing.
- ✅ Reduced memory usage during **PDF handling**.

---

## ❤️ Thanks for Using FaxRetriever!
🔹 **Enjoy the new features?** Let us know! Your feedback helps shape future updates. 🚀
