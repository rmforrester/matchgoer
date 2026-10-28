#!/usr/bin/env bash
# Founder-approved unsigned simulator compilation only; never launches the app.
set -euo pipefail
archive="${1:-native-input.zip}"
expected="17daadc73fbd843cb6748990b6ee0b4caa819ebe5a0325fc531601914c265204"
[[ "$(uname -s)" == Darwin ]] || { echo 'BLOCKED: macOS/Xcode required'; exit 2; }
command -v xcodebuild >/dev/null || { echo 'BLOCKED: Xcode unavailable'; exit 2; }
[[ "$(shasum -a 256 "$archive" | awk '{print $1}')" == "$expected" ]] || { echo 'STOP: input hash drift'; exit 3; }
mkdir -p native-input evidence
unzip -q -n "$archive" -d native-input
project="$PWD/native-input/ios/App/App.xcodeproj"
[[ -f "$project/project.pbxproj" ]] || { echo 'STOP: project missing'; exit 3; }
sw_vers | tee evidence/macos.txt
uname -a | tee evidence/runner-architecture.txt
printf '%s\n' "${ImageOS:-unknown}" "${ImageVersion:-unknown}" | tee evidence/runner-image.txt
xcode-select -p | tee evidence/developer-directory.txt
xcodebuild -version | tee evidence/xcode-version.txt
xcrun --sdk iphonesimulator --show-sdk-version | tee evidence/simulator-sdk.txt
xcodebuild -list -project "$project" 2>&1 | tee evidence/project-schemes.log
xcodebuild -resolvePackageDependencies -project "$project" -scheme App \
  -clonedSourcePackagesDir "$PWD/SourcePackages" 2>&1 | tee evidence/package-resolution.log
xcodebuild -project "$project" -scheme App -configuration Debug \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$PWD/DerivedData" -clonedSourcePackagesDir "$PWD/SourcePackages" \
  -resultBundlePath "$PWD/evidence/NativeBuild.xcresult" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build 2>&1 | tee evidence/native-build.log
app="$PWD/DerivedData/Build/Products/Debug-iphonesimulator/App.app"
[[ -d "$app" && -f "$app/Info.plist" ]] || { echo 'FAIL: simulator product missing'; exit 4; }
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist" | tee evidence/bundle-id.txt
file "$app/App" | tee evidence/executable-architecture.txt
ditto -c -k --sequesterRsrc --keepParent "$app" evidence/App-simulator.zip
shasum -a 256 evidence/App-simulator.zip | tee evidence/app-sha256.txt
printf 'PASS: actual unsigned simulator compilation; signing/device/auth remain unverified\n' | tee evidence/outcome.txt
