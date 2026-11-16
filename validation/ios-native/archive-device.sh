#!/usr/bin/env bash
# Unsigned physical-device archive only. No signing, installation or upload.
set -euo pipefail
archive="${1:-native-input.zip}"
expected="eca0bfbd6b503f9a69ce3bb858e5822c70701691dcc12b2cab2616ed28a56fe8"
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
  PRODUCT_BUNDLE_IDENTIFIER=com.matchgoer.app MARKETING_VERSION=0.1.1 CURRENT_PROJECT_VERSION=15 \
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
assert info['CFBundleVersion']=='15' and info['CFBundleShortVersionString']=='0.1.1'
assert info['UIDeviceFamily']==[1]
assert info.get('NSCameraUsageDescription') and info.get('NSLocationWhenInUseUsageDescription')
assert (app/'PrivacyInfo.xcprivacy').is_file()
privacy=plistlib.loads((app/'PrivacyInfo.xcprivacy').read_bytes());assert privacy['NSPrivacyTracking'] is False
ent=plistlib.loads(pathlib.Path('native-input/ios/App/App/App.entitlements').read_bytes());assert ent['com.apple.developer.applesignin']==['Default']

config=plistlib.loads((app/'GoogleService-Info.plist').read_bytes())
assert config['BUNDLE_ID']=='com.matchgoer.app'
assert config['PROJECT_ID']=='matchgoer-40103'
assert config['GOOGLE_APP_ID']=='1:158177709083:ios:50df43974431810e64fcbe'
import hashlib,subprocess
assert hashlib.sha256((app/'GoogleService-Info.plist').read_bytes()).hexdigest()=='d1a71a73ee41c79184b7c1a1ae01579f510813f0917ccce825ea7bb6f4013613'
flags=['FIREBASE_ANALYTICS_COLLECTION_ENABLED','GOOGLE_ANALYTICS_IDFV_COLLECTION_ENABLED','GOOGLE_ANALYTICS_DEFAULT_ALLOW_ANALYTICS_STORAGE','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_STORAGE','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_USER_DATA','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_PERSONALIZATION_SIGNALS','GOOGLE_ANALYTICS_REGISTRATION_WITH_AD_NETWORK_ENABLED','GOOGLE_ADS_ON_DEVICE_CONVERSION_EVENT_DATA_ENABLED','FirebaseAutomaticScreenReportingEnabled']
assert all(info.get(key) is False for key in flags)
assert (app/'native-analytics-rules.json').is_file()
assert 'attendance_recorded' not in json.loads((app/'native-analytics-rules.json').read_text())
symbols=subprocess.check_output(['xcrun','nm',str(app/'App')],stderr=subprocess.DEVNULL).decode(errors='replace')
assert 'FIRAnalytics' in symbols and 'MatchgoerAnalyticsPlugin' in symbols
linked=subprocess.check_output(['otool','-L',str(app/'App')]).decode()
assert 'AdSupport.framework' not in linked
pathlib.Path('evidence/native-analytics-build-verification.json').write_text(json.dumps({'bundle_id':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'build':info['CFBundleVersion'],'firebase_config_sha256':hashlib.sha256((app/'GoogleService-Info.plist').read_bytes()).hexdigest(),'production_bundle_verified':True,'bridge_and_sdk_linked':True,'consent_and_ad_flags_default_false':True,'direct_AdSupport_link':False,'sdk_runtime_initialisation':'NOT_EXECUTED','app_executed':False,'real_events_sent':0,'ga4_property_link':'PENDING_SEPARATE_VERIFICATION'},indent=2))

pathlib.Path('evidence/build12-validation.json').write_text(json.dumps({'bundle_id':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'build':info['CFBundleVersion'],'iphone_only':True,'app_privacy_manifest_present':True,'apple_source_entitlement_present':True,'signing':'NOT PERFORMED','native_authentication':'NOT TESTED'},indent=2))
PY
ditto -c -k --sequesterRsrc --keepParent evidence/Matchgoer-unsigned.xcarchive evidence/Matchgoer-unsigned.xcarchive.zip
shasum -a 256 evidence/Matchgoer-unsigned.xcarchive.zip | tee evidence/archive-sha256.txt
printf 'PASS: unsigned Release device archive; signing, installation, native authentication and TestFlight remain unverified\n' | tee evidence/outcome.txt
