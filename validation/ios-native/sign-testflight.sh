#!/usr/bin/env bash
# One authorised internal TestFlight upload. Never publishes signing artifacts.
set -euo pipefail
set +x
umask 077
[[ "${GITHUB_REF:-}" == refs/heads/validation/ios-native-compilation-20261028 ]] || { echo 'STOP: signing branch mismatch'; exit 2; }
[[ "${DEVELOPER_DIR:-}" == /Applications/Xcode_26.3.app/Contents/Developer ]] || { echo 'STOP: Xcode selection mismatch'; exit 2; }
for name in IOS_P12_BASE64 IOS_P12_PASSWORD IOS_PROFILE_BASE64 IOS_ASC_P8_BASE64 IOS_ASC_KEY_ID IOS_ASC_ISSUER_ID; do
  [[ -n "${!name:-}" ]] || { echo "STOP: missing $name"; exit 2; }
done
[[ "$(shasum -a 256 native-input.zip | awk '{print $1}')" == b1169fd21e4773ea26517cb544b01ce7a34b8adc13a991e947137f41bdaf34d7 ]] || { echo 'STOP: input drift'; exit 2; }
private_dir="$RUNNER_TEMP/matchgoer-signing"
mkdir -p "$private_dir" evidence
keychain="$private_dir/signing.keychain-db"
profile_uuid=''
cleanup() {
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  if [[ -n "$profile_uuid" ]]; then
    rm -f "$HOME/Library/MobileDevice/Provisioning Profiles/$profile_uuid.mobileprovision"
    rm -f "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles/$profile_uuid.mobileprovision"
  fi
  rm -f "$private_dir/certificate.p12" "$private_dir/profile.mobileprovision"
  rm -f "$private_dir/private_keys/AuthKey_${IOS_ASC_KEY_ID}.p8"
}
trap cleanup EXIT
printf '%s' "$IOS_P12_BASE64" | base64 --decode > "$private_dir/certificate.p12"
printf '%s' "$IOS_PROFILE_BASE64" | base64 --decode > "$private_dir/profile.mobileprovision"
mkdir -p "$private_dir/private_keys"
printf '%s' "$IOS_ASC_P8_BASE64" | base64 --decode > "$private_dir/private_keys/AuthKey_${IOS_ASC_KEY_ID}.p8"
keychain_password="$(openssl rand -hex 24)"
printf '::add-mask::%s\n' "$keychain_password"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$private_dir/certificate.p12" -k "$keychain" -P "$IOS_P12_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security >/dev/null
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$keychain_password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain"
curl --fail --silent --show-error --location https://www.apple.com/certificateauthority/AppleWWDRCAG3.cer -o "$private_dir/wwdr.cer"
[[ "$(shasum -a 256 "$private_dir/wwdr.cer" | awk '{print $1}')" == dcf21878c77f4198e4b4614f03d696d89c66c66008d4244e1b99161aac91601f ]] || { echo 'STOP: Apple intermediate hash mismatch'; exit 3; }
security import "$private_dir/wwdr.cer" -k "$keychain" >/dev/null
security find-identity -v -p codesigning "$keychain" > "$private_dir/identities.txt"
export SIGNING_PRIVATE_DIR="$private_dir"
cert_sha1="$(python3 - <<'PY'
import os,re,pathlib
s=(pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'identities.txt').read_text()
rows=re.findall(r'\b([A-F0-9]{40})\s+"([^"]+)"',s)
assert len(rows)==1 and '1 valid identities found' in s, 'STOP: Apple keychain has no single valid signing identity'
assert '(R58JW38U27)' in rows[0][1], 'STOP: signing Team ID mismatch'
print('::add-mask::'+rows[0][1],file=__import__('sys').stderr)
print(rows[0][0])
PY
)"
export SIGNING_CERT_SHA1="$cert_sha1"
security cms -D -i "$private_dir/profile.mobileprovision" > "$private_dir/profile.plist"
profile_uuid="$(python3 - <<'PY'
import os,pathlib,plistlib,datetime,hashlib,uuid
p=plistlib.loads((pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'profile.plist').read_bytes());e=p['Entitlements']
assert p['TeamIdentifier']==['R58JW38U27'] and e['application-identifier']=='R58JW38U27.com.matchgoer.app', 'STOP: profile identity mismatch'
assert not p.get('ProvisionedDevices') and not p.get('ProvisionsAllDevices') and not e.get('get-task-allow'), 'STOP: requires App Store distribution profile'
assert p['ExpirationDate']>datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), 'STOP: expired profile'
assert os.environ['SIGNING_CERT_SHA1'] in [hashlib.sha1(c).hexdigest().upper() for c in p['DeveloperCertificates']], 'STOP: profile/certificate mismatch'
uuid.UUID(p['UUID']);print(p['UUID'])
PY
)"
profile_name="$(/usr/libexec/PlistBuddy -c 'Print :Name' "$private_dir/profile.plist")"
for directory in "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"; do
  mkdir -p "$directory"
  cp "$private_dir/profile.mobileprovision" "$directory/$profile_uuid.mobileprovision"
done
unzip -q -n native-input.zip -d native-input
project="$PWD/native-input/ios/App/App.xcodeproj"
python3 - <<'PY'
import pathlib,plistlib,json
p=pathlib.Path('native-input/ios/App/App/Info.plist');d=plistlib.loads(p.read_bytes());d['CFBundleDisplayName']='Matchgoer';p.write_bytes(plistlib.dumps(d))
p=p.parent/'capacitor.config.json';d=json.loads(p.read_text());d.update(appId='com.matchgoer.app',appName='Matchgoer');p.write_text(json.dumps(d,indent=2)+'\n')
PY
xcodebuild -version | tee evidence/xcode-version.txt
grep -qx 'Xcode 26.3' evidence/xcode-version.txt || { echo 'STOP: toolchain mismatch'; exit 3; }
xcrun --sdk iphoneos --show-sdk-version | tee evidence/device-sdk.txt
xcodebuild -resolvePackageDependencies -project "$project" -scheme App -clonedSourcePackagesDirPath "$PWD/SourcePackages"
xcodebuild -project "$project" -scheme App -configuration Release -sdk iphoneos \
  -destination 'generic/platform=iOS' -archivePath "$private_dir/Matchgoer.xcarchive" \
  -derivedDataPath "$PWD/DerivedData-signed" -clonedSourcePackagesDirPath "$PWD/SourcePackages" \
  PRODUCT_BUNDLE_IDENTIFIER=com.matchgoer.app MARKETING_VERSION=0.1.0 CURRENT_PROJECT_VERSION=3 \
  DEVELOPMENT_TEAM=R58JW38U27 CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY="$cert_sha1" \
  PROVISIONING_PROFILE_SPECIFIER="$profile_name" archive
app="$private_dir/Matchgoer.xcarchive/Products/Applications/App.app"
codesign --verify --deep --strict "$app"
export SIGNING_APP_PATH="$app"
python3 - <<'PY'
import pathlib,os,plistlib,json
p=pathlib.Path(os.environ['SIGNING_APP_PATH']);d=plistlib.loads((p/'Info.plist').read_bytes())
assert d['CFBundleIdentifier']=='com.matchgoer.app' and d['CFBundleDisplayName']=='Matchgoer'
assert d['CFBundleShortVersionString']=='0.1.0' and d['CFBundleVersion']=='3'
config=json.loads((p/'capacitor.config.json').read_text());assert config['plugins']['CapacitorHttp']['enabled'] is True and config['plugins']['CapacitorCookies']['enabled'] is False
assert d['CFBundleSupportedPlatforms']==['iPhoneOS'] and (p/'embedded.mobileprovision').is_file()
options={'method':'app-store-connect','destination':'export','teamID':'R58JW38U27','signingStyle':'manual','signingCertificate':os.environ['SIGNING_CERT_SHA1'],'provisioningProfiles':{'com.matchgoer.app':plistlib.loads((pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'profile.plist').read_bytes())['Name']},'manageAppVersionAndBuildNumber':False}
(pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'ExportOptions.plist').write_bytes(plistlib.dumps(options))
pathlib.Path('evidence/signing-receipt.json').write_text(json.dumps({'bundle_id':'com.matchgoer.app','version':'0.1.0','build':'3','commit':os.environ['GITHUB_SHA'],'signed_archive':'PASS','codesign_verification':'PASS','upload':'NOT YET ATTEMPTED'},indent=2)+'\n')
PY
xcodebuild -exportArchive -archivePath "$private_dir/Matchgoer.xcarchive" -exportOptionsPlist "$private_dir/ExportOptions.plist" -exportPath "$private_dir/export"
ipa_count="$(find "$private_dir/export" -maxdepth 1 -name '*.ipa' | wc -l | tr -d ' ')"
[[ "$ipa_count" == 1 ]] || { echo 'STOP: expected one exported IPA'; exit 4; }
ipa="$(find "$private_dir/export" -maxdepth 1 -name '*.ipa')"
evidence="$PWD/evidence"
# The App Store Connect P8 is discovered only inside this temporary directory.
(
  cd "$private_dir"
  xcrun altool --upload-app -f "$ipa" -t ios --apiKey "$IOS_ASC_KEY_ID" --apiIssuer "$IOS_ASC_ISSUER_ID" --output-format json > upload-result.json 2> upload-error.txt
) || {
  python3 - <<'PY'
import os,pathlib,json,re
p=pathlib.Path(os.environ['SIGNING_PRIVATE_DIR']);messages=[]
try:
 d=json.loads((p/'upload-result.json').read_text())
 for e in d.get('product-errors',[]):messages.append({'code':e.get('code'),'message':str(e.get('message',''))})
except (ValueError,FileNotFoundError):pass
def clean(s):
 for k,v in os.environ.items():
  if k.startswith('IOS_') and v:s=s.replace(v,'[REDACTED]')
 for _,cn in re.findall(r'\b([A-F0-9]{40})\s+"([^"]+)"',(p/'identities.txt').read_text()):s=s.replace(cn,'[SIGNING IDENTITY]')
 return re.sub(r'[A-Za-z0-9_+/=-]{48,}','[REDACTED]',s)
receipt={'upload':'FAIL','errors':[{'code':e['code'],'message':clean(e['message'])} for e in messages]}
pathlib.Path('evidence/upload-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
PY
  echo 'FAIL: Apple upload rejected; review the receipt before any retry'
  exit 5
}
python3 - <<'PY'
import os,pathlib,json,hashlib
p=pathlib.Path(os.environ['SIGNING_PRIVATE_DIR']);result=json.loads((p/'upload-result.json').read_text());assert not result.get('product-errors'), 'STOP: upload returned errors'
ipa=next((p/'export').glob('*.ipa'));r={'bundle_id':'com.matchgoer.app','version':'0.1.0','build':'3','commit':os.environ['GITHUB_SHA'],'signed_archive':'PASS','ipa_sha256':hashlib.sha256(ipa.read_bytes()).hexdigest(),'upload':'PASS','apple_processing':'PENDING','physical_installation':'PENDING FOUNDER TEST'}
pathlib.Path('evidence/upload-receipt.json').write_text(json.dumps(r,indent=2)+'\n')
PY
printf 'PASS: signed archive exported and uploaded; Apple processing and physical installation still require verification\n' | tee "$evidence/outcome.txt"
