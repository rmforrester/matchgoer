#!/usr/bin/env bash
# Unsigned physical-device archive only. No signing, installation or upload.
set -euo pipefail
archive="${1:-native-input.zip}"
expected="b4b7716af772844e2812ac4c8811afa8a42386af898f65ecc4a07c63bf1ba5b6"
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
  PRODUCT_BUNDLE_IDENTIFIER=com.matchgoer.app MARKETING_VERSION=0.1.0 CURRENT_PROJECT_VERSION=8 \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO archive 2>&1 | tee evidence/device-archive.log
app="$PWD/evidence/Matchgoer-unsigned.xcarchive/Products/Applications/App.app"
[[ -d "$app" && -f "$app/Info.plist" ]] || { echo 'FAIL: archived application missing'; exit 4; }
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Info.plist" | tee evidence/bundle-id.txt
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleSupportedPlatforms:0' "$app/Info.plist")" == iPhoneOS ]] || { echo 'FAIL: not a device product'; exit 4; }
file "$app/App" | tee evidence/executable-architecture.txt
xcrun lipo -archs "$app/App" | tee evidence/device-architectures.txt
grep -qx arm64 evidence/device-architectures.txt || { echo 'FAIL: unexpected device architecture'; exit 4; }
[[ ! -e "$app/embedded.mobileprovision" && ! -d "$app/_CodeSignature" ]] || { echo 'STOP: application signing material present'; exit 4; }
python3 - "$app" <<'PY'
import pathlib,plistlib,sys,json
app=pathlib.Path(sys.argv[1]);info=plistlib.loads((app/'Info.plist').read_bytes())
assert info['CFBundleIdentifier']=='com.matchgoer.app'
assert info['CFBundleVersion']=='8' and info['CFBundleShortVersionString']=='0.1.0'
assert info['UIDeviceFamily']==[1]
assert info.get('NSCameraUsageDescription') and info.get('NSLocationWhenInUseUsageDescription')
assert (app/'PrivacyInfo.xcprivacy').is_file()
privacy=plistlib.loads((app/'PrivacyInfo.xcprivacy').read_bytes());assert privacy['NSPrivacyTracking'] is False
ent=plistlib.loads(pathlib.Path('native-input/ios/App/App/App.entitlements').read_bytes());assert ent['com.apple.developer.applesignin']==['Default']
pathlib.Path('evidence/build8-validation.json').write_text(json.dumps({'bundle_id':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'build':info['CFBundleVersion'],'iphone_only':True,'app_privacy_manifest_present':True,'apple_source_entitlement_present':True,'signing':'NOT PERFORMED','native_authentication':'NOT TESTED'},indent=2))
PY
ditto -c -k --sequesterRsrc --keepParent evidence/Matchgoer-unsigned.xcarchive evidence/Matchgoer-unsigned.xcarchive.zip
shasum -a 256 evidence/Matchgoer-unsigned.xcarchive.zip | tee evidence/archive-sha256.txt
printf 'PASS: unsigned Release device archive; signing, installation, native authentication and TestFlight remain unverified\n' | tee evidence/outcome.txt
