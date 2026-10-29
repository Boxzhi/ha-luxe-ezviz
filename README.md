# Luxe EZVIZ

Unofficial Home Assistant integration for EZVIZ Cloud cameras.

**Development status:** `v1.1.0 (PTZ release candidate, not yet published)` HACS packaging candidate based on the verified v1.0.36 Luxe EZVIZ codebase. Not an official EZVIZ product.

## HACS installation

1. This repository must first be created and published on GitHub.
2. In HACS, add `https://github.com/Boxzhi/ha-luxe-ezviz` as a custom **Integration** repository.
3. Download it and restart Home Assistant. The integration will download the unmodified **ezuikit-js 9.0.5** package directly from the official npm registry on first startup, validate all expected SDK files by SHA256, and store them outside the HACS-managed code folder.
4. The packaged card module is registered automatically when Lovelace resource mode is `storage`. If using YAML resources, manually add:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /luxe_ezviz/static/luxe-ezviz-card.js?v=1.1.0
      type: module
```

5. Configure one EZVIZ camera per entry under **Settings → Devices & Services → Luxe EZVIZ**.
6. Use the camera's serial number in dashboard YAML:

```yaml
type: custom:luxe-ezviz-card
device_serial: YOUR_DEVICE_SERIAL
autoplay: false
muted: true
debug: false
```

## SDK licensing

This GitHub repository intentionally excludes all EZUIKit JavaScript/WASM/Worker vendor artifacts. They are downloaded from the official npm source onto each user's Home Assistant device; the download is version-pinned and integrity-checked. The third-party package remains subject to EZVIZ's separate terms. **This does not imply redistribution rights for the vendor files.**

## Stored data

Camera product images remain at `/config/www/luxe-ezviz/images/` and device credentials remain in HA config entries. Neither is included in HACS source releases.

## Release policy

Use GitHub tags/releases and keep `manifest.json` and `frontend_setup.py` versions aligned. Verify SHA256 manifests when updating the SDK. GitHub publishing requires an existing repository and explicit project license selection.

## Diagnostics

If the custom card does not load, visit `/luxe_ezviz/static/luxe-ezviz-card.js`; if playback fails, check `/luxe_ezviz/sdk/ezuikit.js` and HA logs for SDK provisioning failures. Do not publish access tokens, device verification codes, or serial numbers in public issues.

## PTZ controls (v1.1.0 candidate)

The player checks the selected camera's cloud capability set. Supported cameras show a four-direction PTZ button directly above the screenshot button after live playback starts. Unsupported/unknown devices show no PTZ entry. Opening the translucent panel hides the other video controls; tap outside the panel to close it (there is no close button).

- Tap an arrow for a short movement; press and hold for continuous movement.
- Releasing, pointer cancellation, leaving the control area, closing the panel, stopping the video or leaving the dashboard sends a stop request.
- The HA backend also stops movement if no heartbeat arrives for 2.5 seconds.
- The control endpoints require an authenticated HA administrator and never expose EZVIZ cloud credentials to the card.
- Directional support is based on the official `device/capacity` API, not camera model names.
- **Release testing:** Test on a real PTZ camera and a non-PTZ camera before publishing the v1.1.0 GitHub Release.

