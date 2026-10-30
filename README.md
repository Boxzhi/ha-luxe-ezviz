# Luxe EZVIZ

Unofficial Home Assistant integration for EZVIZ Cloud cameras.

**Version:** `v1.2.1` — stable patch release based on v1.2.0, with a horizontal-only refinement to the recording camera icon. Recording behavior, MP4 metadata repair, EZUIKit 9.0.24, and the existing integration configuration remain unchanged. This is an unofficial Home Assistant integration and is not an official EZVIZ product.

## HACS installation

1. This repository must first be created and published on GitHub.
2. In HACS, add `https://github.com/Boxzhi/ha-luxe-ezviz` as a custom **Integration** repository.
3. Download it and restart Home Assistant. The integration will download the unmodified **ezuikit-js 9.0.24** package directly from the official npm registry on first startup, validate all required SDK files against official source Git blob fingerprints and exact file sizes, and store them outside the HACS-managed code folder.
4. The packaged card module is registered automatically when Lovelace resource mode is `storage`. If using YAML resources, manually add:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /luxe_ezviz/static/luxe-ezviz-card.js?v=1.2.1-ezuikit-9.0.24-record-icon-width
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

## v1.2.1 release notes

This is a stable patch release based on the v1.2.0 production baseline.

- Widens the recording camera icon horizontally only; its height remains unchanged.
- Keeps the 23px SVG viewport, stroke weight, button position, 36px hit area, and screenshot control unchanged.
- Re-centers the recording-state dot and spinner within the wider camera body.
- Keeps the existing recording lifecycle, 25-minute warning, 30-minute maximum, multi-camera recording, serial download queue, and MP4 metadata repair unchanged.
- Keeps EZUIKit pinned to 9.0.24.
- Does not change recording filename generation or SDK-provided filename handling.

Existing integration configuration and dashboard YAML remain unchanged.

## v1.2.0 release notes

This stable release updates the existing production integration in place; it is not a second integration domain. The v1.2.0-beta.2 baseline passed real-device recording regression before the final recording-control and timer presentation refinements. Back up the current HACS-managed integration folder before updating.

- PTZ trigger and panel move to the left side; the trigger uses a centered crosshair icon.
- Screenshot and recording controls are stacked on the right, with screenshot above recording.
- Recording uses a left-facing camera icon: white when idle, with a white outline and red center while recording. The icon remains aligned to the screenshot control's 23px visual size and 36px hit area.
- The top-right recording label is a lightweight translucent timer: a red dot with white elapsed time, changing to amber at 25 minutes. The redundant REC text is removed; processing and save-failure states have their own indicators.
- Each camera has an independent recording session, 25-minute warning, and 30-minute automatic stop.
- The SDK is configured with downloadRecord disabled and original-stream recording mode so completed Blobs can enter the page-level sequential download queue.
- Recording audio is intended to preserve the camera's source audio independently of live playback mute. Verify this on real cameras; the SDK's browser/player behavior can vary by stream and device.
- Multiple cameras may record at the same time. Completed file downloads are triggered one at a time with a short gap; browser APIs do not expose reliable download-completed notifications.
- Leaving the dashboard asks active players to stop and hand off recordings before teardown. Force-closing the browser or HA app can still interrupt an unfinished save.
- Adds browser-side MP4 metadata validation for AVC (`avc1`/`avc3`) and HEVC (`hvc1`/`hev1`) recordings. When the SPS provides an unambiguous display size and the track uses an identity matrix without `clap`/`pasp`, only zero-valued Sample Entry and/or `tkhd` dimensions are repaired.
- Valid files are passed through as the original Blob without changing any bytes. Unsupported or conflicting metadata is left untouched; the repair does not remux or transcode audio/video.

The 30-minute limit is enforced independently for each camera. Browser download completion is not observable through a reliable browser event, and force-closing the browser or HA app can interrupt an unfinished save; do not treat browser-side recording as an unattended archival system.

## SDK licensing

This GitHub repository intentionally excludes all EZUIKit JavaScript/WASM/Worker vendor artifacts. They are downloaded from the official npm source onto each user's Home Assistant device; the download is version-pinned and integrity-checked. The third-party package remains subject to EZVIZ's separate terms. **This does not imply redistribution rights for the vendor files.**

## Stored data

Camera product images remain at `/config/www/luxe-ezviz/images/` and device credentials remain in HA config entries. Neither is included in HACS source releases.

## Release policy

Use GitHub tags/releases and keep `manifest.json` and `frontend_setup.py` versions aligned. Verify SHA256 manifests when updating the SDK. GitHub publishing requires an existing repository and explicit project license selection.

## Diagnostics

If the custom card does not load, visit `/luxe_ezviz/static/luxe-ezviz-card.js`; if playback fails, check `/luxe_ezviz/sdk/ezuikit.js` and HA logs for SDK provisioning failures. Do not publish access tokens, device verification codes, or serial numbers in public issues.

## PTZ controls (v1.1.0)

The player checks the selected camera's cloud capability set. Supported cameras show a four-direction PTZ button on the left side of the video after live playback starts. Unsupported/unknown devices show no PTZ entry. Opening the translucent panel hides the other video controls; tap outside the panel to close it (there is no close button).

- Tap an arrow for a short movement; press and hold for continuous movement.
- Releasing, pointer cancellation, leaving the control area, closing the panel, stopping the video or leaving the dashboard sends a stop request.
- The HA backend also stops movement if no heartbeat arrives for 2.5 seconds.
- The control endpoints require an authenticated HA administrator and never expose EZVIZ cloud credentials to the card.
- Directional support is based on the official `device/capacity` API, not camera model names.
- **Validation note:** GitHub Actions and automated regression tests pass. Before unattended use, verify movement and stop behavior on a real PTZ camera, and confirm the PTZ entry stays hidden on a non-PTZ camera.

## Multi-camera audio exclusivity (v1.1.1)

All Luxe EZVIZ cards on the same Home Assistant page coordinate audio playback. Enabling sound on one camera requests the other cameras to mute first. The card also mutes peer cameras before starting two-way talk. Ending talk releases the audio lock but does not restore sound on other cameras; the user must explicitly choose the next audio source.

- Video playback remains independent; only audio is coordinated.
- The existing `muted: true` default remains unchanged.
- If another camera cannot confirm mute, the new sound request fails closed instead of intentionally allowing multiple audio sources.
- Coordination is scoped to the same browser tab/page, not separate browser tabs or devices.
- On iOS/Safari, verify sound switching, native fullscreen volume controls, talk start/stop, and playback teardown on the actual devices before unattended use.

