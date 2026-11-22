# TECHVISTRA Food Desk v8.2

First standalone public source release of the TECHVISTRA '26 offline food distribution desk.

## What's included
- Local Python/SQLite food desk server designed to operate on a classroom Wi-Fi/LAN without event-day internet
- Laptop administrator dashboard and phone-browser QR scanner for counter staff
- Verified website QR-pass handling, attendance and venue/year checks, and one-time meal collection
- Separate 2nd-, 3rd- and 4th-year laptop deployments, veg/non-veg stock controls, device accounting and CSV reporting
- macOS and Windows install/open launchers, plus Android and iOS client source projects
- PIN-controlled QR restoration and collection-history handling

## Install
1. Download `TECHVISTRA-Food-Desk-v8.2.zip` under **Assets** and extract it into a writable folder.
2. Keep the `app` directory together with the Mac/Windows launcher files.
3. Read `README.md` and `app/README.md`; run the appropriate **Install and Setup** launcher while online, before event day.
4. Configure your own approved student attendance and original website QR keys **privately** on each laptop. Never upload populated databases, QR key JSON, private certificates, or passwords.
5. Test the correct venue/year, mismatched passes, duplicate scans, and camera/certificate setup on each actual laptop and phone.

**Important:** This is a source distribution, not a prebuilt Windows EXE, signed Mac app, or production-hosted website. Python dependencies must be installed during setup. This public release intentionally excludes event database files, personal student records, administrator secrets, private signing/encryption keys, generated certificates, logs, and virtual environments.

See [README.md](README.md) and [app/README.md](app/README.md) for prerequisites and operational limitations.
