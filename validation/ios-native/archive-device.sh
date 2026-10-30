#!/usr/bin/env bash
# Unsigned physical-device archive only. No signing, installation or upload.
set -euo pipefail
archive="${1:-native-input.zip}"
expected="23d9d9d68bdd6b18333769aaf049b088c66a6f60aa28b8ff419889dcb36bd773"
[[ "$(uname -s)" == Darwin ]] || { echo 'BLOCKED: macOS/Xcode required'; exit 2; }
[[ "${DEVELOPER_DIR:-}" == /Applications/Xcode_26.3.app/Contents/Developer ]] || { echo 'STOP: explicit Xcode 26.3 selection required'; exit 2; }
[[ -x "$DEVELOPER_DIR/usr/bin/xcodebuild" ]] || { echo 'BLOCKED: Xcode 26.3 unavailable'; exit 2; }
[[ "$(shasum -a 256 "$archive" | awk '{print $1}')" == "$expected" ]] || { echo 'STOP: input hash drift'; exit 3; }
mkdir -p native-input evidence
unzip -q -n "$archive" -d native-input
project="$PWD/native-input/ios/App/App.xcodeproj"
[[ -f "$project/project.pbxproj" ]] || { echo 'STOP: project missing'; exit 3; }
sw_vers | tee evidence/macos.txt
uname -a | tee evidence/runner-architecture.txt
printf '%s\n' "${ImageOS:-unknown}" "${ImageVersion:-unknown}" | tee evidence/runner-image.txt
printf '%s\n' "$DEVELOPER_DIR" | tee evidence/developer-directory.txt
xcodebuild -version | tee evidence/xcode-version.txt
grep -qx 'Xcode 26.3' evidence/xcode-version.txt || { echo 'STOP: Xcode version mismatch'; exit 3; }
xcrun --sdk iphoneos --show-sdk-version | tee evidence/device-sdk.txt
xcodebuild -resolvePackageDependencies -project "$project" -scheme App \
  -clonedSourcePackagesDirPath "$PWD/SourcePackages" 2>&1 | tee evidence/package-resolution.log
xcodebuild -project "$project" -scheme App -configuration Release \
  -sdk iphoneos -destination 'generic/platform=iOS' \
  -archivePath "$PWD/evidence/Matchgoer-unsigned.xcarchive" \
  -derivedDataPath "$PWD/DerivedData-device" -clonedSourcePackagesDirPath "$PWD/SourcePackages" \
  -resultBundlePath "$PWD/evidence/DeviceArchive.xcresult" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO archive 2>&1 | tee evidence/device-archive.log
app="$PWD/evidence/Matchgoer-unsigned.xcarchive/Products/Applications/App.app"
[[ -d "$app" && -f "$app/Info.plist" ]] || { echo 'FAIL: archived application missing'; exit 4; }
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist" | tee evidence/bundle-id.txt
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleSupportedPlatforms:0' "$app/Info.plist")" == iPhoneOS ]] || { echo 'FAIL: not a device product'; exit 4; }
file "$app/App" | tee evidence/executable-architecture.txt
xcrun lipo -archs "$app/App" | tee evidence/device-architectures.txt
grep -qx arm64 evidence/device-architectures.txt || { echo 'FAIL: unexpected device architecture'; exit 4; }
[[ ! -e "$app/embedded.mobileprovision" && ! -d "$app/_CodeSignature" ]] || { echo 'STOP: application signing material present'; exit 4; }
ditto -c -k --sequesterRsrc --keepParent evidence/Matchgoer-unsigned.xcarchive evidence/Matchgoer-unsigned.xcarchive.zip
shasum -a 256 evidence/Matchgoer-unsigned.xcarchive.zip | tee evidence/archive-sha256.txt
printf 'PASS: unsigned Release device archive; signing, installation, native authentication and TestFlight remain unverified\n' | tee evidence/outcome.txt
