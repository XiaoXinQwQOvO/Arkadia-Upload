# Arkadia Upload

Re-sign and upload Arkadia IPA to App Store Connect / TestFlight using GitHub Actions.

## Setup

1. Place `Arkadia.ipa` at a downloadable URL (or upload to repo root)
2. Go to Actions > "Re-sign & Upload IPA to App Store Connect" > Run workflow
3. Enter the IPA download URL
4. Wait for the workflow to finish — the IPA will be uploaded to TestFlight

## Required Secrets

| Secret | Description |
|--------|-------------|
| `APPLE_CERTIFICATE_P12_BASE64` | Base64-encoded `.p12` signing certificate |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the `.p12` file |
| `APPLE_PROVISIONING_PROFILE_BASE64` | Base64-encoded `.mobileprovision` file |
| `APPLE_API_ISSUER_ID` | App Store Connect API Issuer ID |
| `APPLE_API_KEY_ID` | App Store Connect API Key ID |
| `APPLE_API_PRIVATE_KEY` | Contents of the `AuthKey_XXXXX.p8` file |

## What it does

1. Downloads the IPA from the provided URL
2. Imports the signing certificate into a temporary keychain
3. Installs the provisioning profile
4. Re-signs all frameworks, dylibs, and the main app
5. Packages the re-signed IPA
6. Uploads to App Store Connect via `xcrun altool` (appears in TestFlight)

## Files

- `.github/workflows/upload_ipa.yml` — GitHub Actions workflow