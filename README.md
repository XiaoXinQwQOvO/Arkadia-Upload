# Arkadia Upload

Re-sign and upload decrypted Arkadia IPA to App Store Connect / TestFlight using GitHub Actions.

## Workflow

**Re-sign & Upload IPA to App Store Connect**

1. Downloads the decrypted IPA from the provided URL
2. Generates all required app icon sizes (iPhone + iPad + App Store 1024x1024) into the bundle root
3. Updates `Info.plist` with `CFBundleIcons` / `CFBundleIcons~ipad`
4. Imports the signing certificate into a temporary keychain
5. Installs the provisioning profile
6. Re-signs all frameworks, dylibs, and the main app
7. Uploads to App Store Connect via `xcrun altool` (appears in TestFlight)

**Trigger:** Actions > "Re-sign & Upload IPA to App Store Connect" > Run workflow  
**Input:** `ipa_url` — download URL for the decrypted IPA

## Required Secrets

| Secret | Description |
|--------|-------------|
| `APPLE_CERTIFICATE_P12_BASE64` | Base64-encoded `.p12` signing certificate |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the `.p12` file |
| `APPLE_PROVISIONING_PROFILE_BASE64` | Base64-encoded `.mobileprovision` file |
| `APPLE_API_ISSUER_ID` | App Store Connect API Issuer ID |
| `APPLE_API_KEY_ID` | App Store Connect API Key ID |
| `APPLE_API_PRIVATE_KEY` | Contents of the `AuthKey_XXXXX.p8` file |

## Files

- `.github/workflows/upload_ipa.yml` — GitHub Actions workflow
- `gen_icons.py` — Generates app icon PNGs and updates Info.plist
