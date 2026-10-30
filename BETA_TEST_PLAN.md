# Luxe EZVIZ v1.2.0-beta.1 — HACS test plan

This is a pre-release test build of the existing production integration domain (luxe_ezviz). Installing it through HACS updates the existing integration in place; it does not install a second integration.

Release channel: GitHub pre-release v1.2.0-beta.1. The stable v1.1.2 release remains unchanged and latest.

## Before installing

- Back up the current custom_components/luxe_ezviz folder and Home Assistant configuration.
- Enable beta/pre-release versions for the Luxe EZVIZ custom repository in HACS.
- Install v1.2.0-beta.1 and restart Home Assistant.
- If Lovelace resources are managed in YAML, update the card resource to:
  /luxe_ezviz/static/luxe-ezviz-card.js?v=1.2.0-beta.1-ezuikit-9.0.24

## UI regression

- Confirm the PTZ crosshair appears at the left vertical center only for cameras with PTZ capability.
- Open PTZ and confirm its panel opens from the left, supports existing drag and eight-direction controls, and keeps the existing close behavior.
- Confirm screenshot is on the right above the recording button.
- Confirm the quality menu stays above the quality button, right-aligned to it, after portrait/landscape and fullscreen changes.
- Confirm the quality menu retains the existing close behavior and has the increased background transparency.
- Confirm the existing bottom controls, talk behavior, audio exclusivity, PiP, fullscreen, and screenshot remain functional.

## Recording — one camera

- Start recording and confirm the button changes to the stop-record icon.
- Confirm REC and elapsed time appear at the top-right.
- Confirm all other controls for that player are hidden while recording; other camera cards remain independently usable.
- Stop recording manually and verify a file is triggered for download to the current device.
- Play the file using the EZVIZ player and check both video and audio.
- Repeat while live playback is muted; the recording should still contain camera audio.
- Verify filenames include camera display name, serial suffix, local date/time, and a millisecond suffix.

## Recording — multiple cameras

- Start recording on two cameras at the same time.
- Stop them in different orders and confirm each produces its own file.
- Stop one camera and confirm the other continues recording.
- Confirm completed files are handed to the page-level download queue and download triggers are serialized with a short gap.
- Note: browsers do not expose a reliable event confirming that a download has fully completed. The queue serializes download triggers, not the operating system's full download completion.

## Limits and lifecycle

- Confirm the 25-minute warning and orange REC status.
- Confirm automatic stop at 30 minutes.
- Navigate away while recording and confirm the player stops, hands the completed Blob to the parent queue, and only then releases the iframe.
- Test a failed save/download path and confirm the player is not immediately destroyed and the recording button allows retry.
- Force-closing the browser or HA app cannot guarantee an in-progress save.

## Device matrix

- iPhone 16 Pro: Safari and Home Assistant App.
- iPad 11-inch: portrait and landscape.
- Mac: Safari and Chrome.

## Beta acceptance

Do not treat the beta as production-ready until single-camera audio, two-camera simultaneous recording, local download, 25/30-minute limits, and page-navigation handoff have been verified on the actual devices.
