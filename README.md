# TECHVISTRA '26 Offline Food Desk (v8.2)

Self-hosted **offline food-pass scanning desk** for event meal distribution. The desktop/server code is in `app/`, with iOS and Android client code under `app/phone-apps/`.

## Getting started

See [`app/README.md`](app/README.md). On a Mac, run `Mac - Install and Setup.command`; on Windows, run `Windows - Install and Setup.bat`. Keep the supplied scripts and the `app` folder together.

## Security and deployment

This repository intentionally omits event databases, student details, administrator credentials, QR signing/encryption secrets, private TLS keys, local certificates, logs, `.venv` and operating-system cache files.

The `website-qr-setup-template.json` file is a **placeholder**. Obtain the matching website AES key and **public** P-256 verification key through a secure private channel; never put the completed file into GitHub. Never regenerate an encryption/signing key for passes that already exist.

The project is an **offline Python application**, not a PHP web application for direct deployment to Hostinger. Consult the internal README for setup and QR verification requirements.
