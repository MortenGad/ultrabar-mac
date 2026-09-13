#!/bin/zsh
set -eu
cd "$(dirname "$0")"
app='../build/Ultrabar Mac.app'
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp Info.plist "$app/Contents/Info.plist"
cp bridge.py widgets.py mac_actions.py module_inventory.py wallpaper.py "$app/Contents/Resources/"
swiftc -parse-as-library -target arm64-apple-macos14.0 UltrabarMac.swift WidgetEditor.swift MacActions.swift Wallpaper.swift -o "$app/Contents/MacOS/UltrabarMac" -framework SwiftUI -framework AppKit
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"
