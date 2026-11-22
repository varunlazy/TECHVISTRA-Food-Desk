## One-file website QR setup

Ask the website administrator to fill website-qr-setup-template.json privately with the matching website AES key and the full P-256 public verification PEM. The template is not a working configuration until real website values are supplied. Do not generate replacement keys for already issued QR codes. public_pem stores the full PEM text; JSON uses \n for line breaks. Never include the website’s private signing key.

On each laptop run Mac - Setup Website QR.command or Windows - Setup Website QR.bat. Press Enter for one-file import, then drag the same completed private JSON into the prompt. The app validates and saves it locally. No server restart is needed. Keep the JSON private; configure each laptop once and test a fresh actual pass. Do not upload the completed file to chat, GitHub or public hosting.

Phone scanning: bundled jsQR 1.4.0 decodes camera images on the phone without internet. Native BarcodeDetector is preferred when available; an occasional laptop decoder fallback remains. Apache-2.0 license is included in static/jsQR-LICENSE.txt. Actual camera speed depends on focus, lighting, phone and QR size. Refresh each phone page after updating.

# Three classrooms / three independent networks

Use a separate extraction on each of the three laptops. Assign one year to one laptop for the entire event: 2nd, 3rd, and 4th year.

1. Connect each laptop and its counter phones to that classroom’s hotspot.
2. Run Install and Setup. Create an administrator and separate counter accounts on each laptop.
3. Configure matching website QR encryption and public verification keys locally on each laptop with configure_secure_qr.py. No attendance CSV is needed for verified live TV26E2 passes.
4. In admin Overview click Open food counters. Select the year and enter total veg/non-veg meals prepared (including meals already served).
5. Live encrypted QR passes must include an integer `year`: 2, 3 or 4 inside the signed/encrypted payload. The year is verified before student details are accepted. No register-number prefix is required. Old passes without year must be reissued by the website.
6. Use the admin phone-login QR for this laptop. Each phone must first install and trust this laptop’s event certificate through Phone Setup.
7. Test a fresh correct-year QR, a wrong-year QR, and a repeated QR before opening for students. Wrong-year passes are rejected at both check and redemption. Stock cannot go below zero.

Each laptop has independent stock, logins, devices, and reports. The networks do not synchronize. Duplicate blocking applies within one laptop; correct, non-overlapping year assignments keep students on their assigned server. Do not run a second server for the same year, reset/copy event databases mid-service, or move a year to another laptop without its records. Year changes are blocked after any real meal is served. Reopening and updating stock preserve all serving records.

Export all three reports at the end. Keep the original website keys private. This distribution ZIP contains no existing database, passwords, QR keys, or certificates; configure each laptop separately.

---

# TECHVISTRA Food Desk v8

## Start here
Extract the entire ZIP to a writable local folder. Keep the `app` folder beside the four entry files. Do not run directly inside the ZIP. Do not move only a launcher.

| Platform | First time, with internet | Event day, offline |
| --- | --- | --- |
| macOS 11+ | Mac - Install and Setup.command | Mac - Check and Open.command |
| Windows 10/11 | Windows - Install and Setup.bat | Windows - Check and Open.bat |

Install & Setup provisions a private Python environment, installs all QR and HTTPS dependencies, checks the database and ports, prepares local certificates, starts the server and opens the browser. If Python is absent, macOS downloads the signed official Python installer and asks for the computer administrator password; Windows uses winget. Windows machines without winget need Python 3.12 installed from python.org first. Security policies may require allowing a downloaded script; on Mac use Open from the context menu, or `bash "Mac - Install and Setup.command"` in Terminal. If executable bits are lost while extracting, the Terminal command works.

Check & Open makes no downloads. It checks dependencies, database health, certificates and port availability, reuses an existing local server when detected, and opens the laptop dashboard. Keep the console open and laptop awake. Ctrl+C stops the server. Setup can be rerun to repair dependencies; saved data is preserved. The launchers use the standard ports 8787/8788/8789; leave custom FOODDESK environment overrides unset.

## Laptop and phone workflow
1. Create the administrator password on the laptop at http://localhost:8789 (12+ characters). No default password is supplied. Admin login from a remote phone is blocked.
2. Under Food counters create a **different username and password for each phone**, with a clear counter name. Staff passwords need at least 8 characters. Disabling an account immediately revokes its sessions.
3. Import approved attendance/QR CSV, or configure the original secure QR integration. Open distribution when ready. Demo QR tests never authorize real food or count as meals.
4. Connect laptop and phones to the same private Wi-Fi. Internet is unnecessary after setup. Permit the app through the OS firewall for the private network if prompted. Guest Wi-Fi/client isolation can prevent phones reaching the laptop.
5. Open Laptop server for the phone setup address. On each phone install and trust the event's public CA, verify its fingerprint against the laptop, then open the HTTPS scanner. Phone OS certificate trust and camera permissions require manual approval. Remove the event CA after the event.
6. Sign in using that phone's staff account, and enter a recognizable device label. Staff see the scanner, identity/meal confirmation, and totals for their browser device. Scan, confirm identity and tap Give Food only when handing over the meal.
7. On the laptop open **Live operations**. Devices, requests and the food given list refresh every 3 seconds. A device is online when its authenticated heartbeat arrived in the last 22 seconds. Background/sleeping phones may show offline. A scan marked awaiting confirmation expires in 2 minutes; expiry changes the dashboard status only, and does not revoke a pass or block a later valid redemption. Cancel changes that device's pending check to cancelled. Successful redemption resolves pending scans of that same pass.
8. Export the full CSV report, including the giving device. The on-screen scan and given lists each show the latest 100 records. All real meals are retained in the database and full export.

## Device accounting
A device means a browser profile with a persistent cookie, not a hardware serial number. It survives logout/login in the same browser. Clearing cookies, private browsing, switching browser, switching between the HTTP laptop URL and HTTPS phone URL, or reinstalling a native app creates a separate device record. Use one assigned staff account per phone/browser. Reusing a browser under another account retains that browser's meal attribution and updates its displayed account/label. Do not use shared browser profiles across counters.

Meal counts increase only after a successful SQLite redemption transaction; concurrent attempts yield exactly one success. Requests/checks and demos do not increment totals. Old v7 records migrate automatically on startup. Historical meals cannot be attributed retrospectively to a device; they show Legacy / unknown device. Existing counter-level totals remain available on Overview.

## Existing data and backup
For an upgrade, stop the old server and copy the entire old `data` folder into `app/data` **before first launch**. Keep a separate backup of the original. SQLite schema migration preserves users, students and redemptions. Do not overwrite an existing populated `data` folder. Copy backups only while the server is stopped, including certificate and QR key files. Private keys and the database must remain private.

## Validation
Linux integration checks cover schema migration reruns, separate staff access, request logging, concurrent duplicate prevention, exact device totals and cookie persistence. Headless Chromium checks passed for desktop rendering, live device refresh, scanner-only staff UI and device totals with no JavaScript errors. Python compilation and JavaScript syntax checks passed. macOS/Windows installers and real phone camera/certificate flows still need testing on the actual target devices before event day.

## v8.1 startup repair
Corrected macOS virtual-environment detection: Python executables may be symlinks to the same system binary; the launcher now uses sys.prefix to identify the active environment. Setup repairs pip, preserves unusable environments under .venv-backup-* and rebuilds them when needed. Common dependency, permission, database, certificate and port failures show recovery guidance; diagnostics are appended to app/data/startup-error.log. No automatic deletion of event records or certificates. Check and Open does not download dependencies; use Install and Setup for repairs. Unexpected startup exceptions are logged instead of printing a raw traceback.

To update an existing installation without replacing its data, replace app/launcher.py and app/local_https.py from this release. Leave the existing app/data folder untouched. Alternatively extract a fresh copy into a separate folder and follow the backup/migration instructions above.

Validation: four startup regression tests passed (symlink detection, child error propagation, logged failure categories and interruption). Real setup --check-only completed in Linux, as did the food-desk integration test. Native Mac/Windows execution remains unverified.
