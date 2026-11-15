# Ultrabar Mac

An experimental native macOS companion for the **Sanytron UltraBar X**. Configure widgets, launch Mac apps from the device, discover attached modules, and preview images without the Windows-only UltraWorkspace client.

This is an independent community project, not affiliated with or endorsed by Sanytron. The device runs Sanytron **LineOS**, which is unrelated to LineageOS.

## Features

- Pair over the local network, with approval on the device and a pinned vendor TLS certificate.
- Discover KnobKey, DotKey, VivoCube and SenseCube modules; combine discovery replies with registered online status.
- List and switch saved profiles.
- Edit clocks, timers, fixed-offset world clocks, weather coordinates, installed app launchers and supported soundscapes.
- Save local drafts, import/export JSON and review profile changes before deployment.
- Create a touchscreen Mac app-launch panel and assign app launchers to DotKey and KnobKey press gestures.
- Set screensaver enablement and inactivity timeout, with settings read-back.
- Preview a selected image full-screen on CoreBAR, cropped locally to 1424 × 280. Tap the device to dismiss it.
- Experimental Mac system-volume handling for KnobKey rotation.

## Requirements

- Apple Silicon Mac running macOS 14 or newer.
- Xcode Command Line Tools (`xcode-select --install`).
- Python 3.14 installed using the macOS installer from [python.org](https://www.python.org/downloads/macos/). The current app expects `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`; Homebrew Python alone does not satisfy this path.
- UltraBar X reachable on the same LAN. Protocol work used the vendor's LineOS v1.0.8 and CoreBridge v1.0.3 packages; other firmware versions may differ.

Python dependencies are all in the standard library. The app does not bundle Python and is not notarized.

## Build and run

```sh
git clone https://github.com/MortenGad/ultrabar-mac.git
cd ultrabar-mac
zsh source/build.sh
open "build/Ultrabar Mac.app"
```

The build creates an ad hoc signed app. In **Device**, enter your CoreBAR's local IP address, choose **Pair**, and approve the request on its screen. Use **Connect** on later launches. No personal IP or pairing token is included in this repository.

## Widgets and Mac buttons

In **Widgets**, add and edit cards, then save the local draft. **Review & apply** shows the proposed profile changes before sending them to the device. The initial example is a new draft, not an import of the current device layout. World-clock offsets are fixed and do not adjust for daylight saving.

In **Mac buttons**, select apps using **Add Mac app…**, save locally, and use **Test launch** to test them. Assign launchers to physical press gestures, then review and apply the dedicated Mac buttons profile. Keep the app open and app buttons enabled. The bridge accepts configured action IDs only; device messages cannot supply shell commands or arbitrary application paths.

## Wallpaper preview

Choose **Screen → Choose image… → Show on Ultrabar**. Supported input formats include PNG, JPEG, HEIC, TIFF and WebP. Review the centre crop before sending. The image selection lasts for the app session.

This is a temporary full-screen preview. It **does not set permanent wallpaper behind widgets or an automatic image screensaver**. A successful transfer confirms image fetch, not visual rendering. VivoCube screen customization is not implemented.

The Mac briefly serves only the selected image over HTTP on its LAN interface. Access requires an unpredictable URL and the connected device's IP. The listener closes after transfer or a 15-second timeout; pairing credentials are never sent over this HTTP connection.

## Experimental limitations

**Profile deployment can replace device layouts.** The available firmware operation writes the whole profile list, while existing widget definitions cannot be downloaded. Unknown profiles require explicit replacement confirmation. Known app-managed profiles are preserved from a local ledger, but external edits with unchanged profile IDs and names cannot be detected. Review every deployment. Profile-name records are not restorable layout backups.

**Using other companion apps on the same CoreBAR.** Tools such as [UltraBar Studio](https://github.com/qlerup/ultrabar-studio) (Windows) write the same whole-profile list. If another tool edits a profile that Ultrabar Mac deployed and keeps its ID and name, applying from Ultrabar Mac restores this app's last recorded version and discards those edits. On LineOS 1.0.8 the device reports only each profile's ID, name and a boolean flag, so Ultrabar Mac detects another tool's changes only when profile IDs or names change. If another tool removes or renames app-managed profiles, the review lists them as replaced and requires confirmation. Widget edits that keep a profile's ID and name cannot be detected. After each verified deployment the app also records any extra non-boolean metadata the device reports, and flags app-managed profiles whose metadata later changes. This helps only on firmware that reports such metadata. Manage each profile from one app only, and create a separate profile for each tool.

The older **Mac volume** deployment replaces profiles, widgets and gateway registration with a dedicated volume profile. It blocks deployment if other custom profiles exist. It is not a safe way to add rotation controls to an existing custom layout. Physical rotation behavior remains unverified.

Live checks have confirmed pairing, module status, profile deployment acknowledgments, a Mac app-launch event, and image fetch with unchanged profile names and screen settings. Physical key numbering, all press gestures, weather/audio rendering and rotation still need broader hardware testing.

VivoCube screen design, permanent wallpaper, firmware updates, arbitrary Android widgets and full device backup/restore are not included.

## Local data and trust

Pairing credentials, drafts, app-launch settings, module inventory and deployment records are stored under `~/Library/Application Support/Ultrabar Mac/`. Pairing files use private permissions. Keep that directory out of Git and do not attach it to public issues.

The TLS pin matches the public certificate observed in CoreBridge v1.0.3. It is checked before a pairing token is sent. Firmware that changes this certificate needs a reviewed pin update. A shared vendor certificate is not a unique identity for an individual device.

## Tests and source

```sh
python3 -m unittest discover -s source -p 'test_*.py' -v
```

The 58 tests cover protocol framing, pairing, rejected writes, profile preservation, external-change detection, app action restrictions, module status merging and image-transfer access controls. They do not replace physical-device testing.

- `source/UltrabarMac.swift`, `WidgetEditor.swift`, `MacActions.swift`, `Wallpaper.swift`: SwiftUI interface.
- `source/bridge.py`: device transport, pairing and stdio commands.
- `source/widgets.py`: widget validation and reviewed deployment.
- `source/mac_actions.py`: app launchers and physical bindings.
- `source/module_inventory.py`: discovery/status reconciliation.
- `source/wallpaper.py`: temporary image-preview transfer.

Protocol investigation used official packages from [Qinkunex/UltraWorkspace](https://github.com/Qinkunex/UltraWorkspace). Vendor firmware, binaries, extracted code, credentials and session logs are not distributed here.

## License

MIT. See [LICENSE](LICENSE). Sanytron and its product names belong to their respective owners.
