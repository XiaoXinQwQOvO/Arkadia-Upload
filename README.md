# Arkadia Upload

Re-sign and upload decrypted Arkadia IPA to App Store Connect / TestFlight using GitHub Actions.

## Workflows

### 1. Build Assets.car

Generates an `Assets.car` containing a complete AppIcon set (all required sizes for iPhone + iPad + App Store).

**Trigger:** Actions > "Build Assets.car" > Run workflow  
**Output:** `Assets.car` artifact (downloadable, 30-day retention)

### 2. Re-sign & Upload IPA to App Store Connect

Downloads a decrypted IPA, replaces its `Assets.car`, re-signs with the distribution certificate, and uploads to TestFlight.

**Trigger:** Actions > "Re-sign & Upload IPA to App Store Connect" > Run workflow  
**Inputs:**
- `ipa_url` — download URL for the decrypted IPA
- `assets_car_url` — download URL for the `Assets.car` from the Build Assets.car workflow artifact

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

- `.github/workflows/build_assets.yml` — Build Assets.car workflow
- `.github/workflows/upload_ipa.yml` — Re-sign & Upload workflow
- `gen_assets.py` — Generates Asset Catalog with all required icon sizes
