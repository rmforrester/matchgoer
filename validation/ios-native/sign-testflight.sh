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
[[ "$(shasum -a 256 native-input.zip | awk '{print $1}')" == 20fd89430ba0fcb4b6bc9685bc0b73526e63744cf6127623b90c4e0c53ce0117 ]] || { echo 'STOP: input drift'; exit 2; }
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
assert e.get('com.apple.developer.applesignin')==['Default'], 'STOP: Apple entitlement missing from profile'
assert not p.get('ProvisionedDevices') and not p.get('ProvisionsAllDevices') and not e.get('get-task-allow'), 'STOP: requires App Store distribution profile'
assert p['ExpirationDate']>datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), 'STOP: expired profile'
assert os.environ['SIGNING_CERT_SHA1'] in [hashlib.sha1(c).hexdigest().upper() for c in p['DeveloperCertificates']], 'STOP: profile/certificate mismatch'
uuid.UUID(p['UUID']);print(p['UUID'])
PY
)"
profile_name="$(/usr/libexec/PlistBuddy -c 'Print :Name' "$private_dir/profile.plist")"
export SIGNING_PROFILE_NAME="$profile_name"
for directory in "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"; do
  mkdir -p "$directory"
  cp "$private_dir/profile.mobileprovision" "$directory/$profile_uuid.mobileprovision"
done
unzip -q -n native-input.zip -d native-input
project="$PWD/native-input/ios/App/App.xcodeproj"
python3 - <<'PY'
import pathlib,plistlib,json
p=pathlib.Path('native-input/ios/App/App/Info.plist');d=plistlib.loads(p.read_bytes());assert d['CFBundleDisplayName']=='Matchgoer'
c=json.loads((p.parent/'capacitor.config.json').read_text());assert c['appId']=='com.matchgoer.app' and c['appName']=='Matchgoer' and not c.get('server',{}).get('url')
PY

# Apply only four signing settings to the production App target's Release config.
python3 - <<'PY'
import pathlib,json,os,subprocess,copy,re,hashlib
# Begin pure target-signing helper.
def target_signing_patch(text,project,identity,profile):
    objects=project['objects']
    targets=[v for v in objects.values() if v.get('isa')=='PBXNativeTarget' and v.get('name')=='App' and v.get('productType')=='com.apple.product-type.application']
    assert len(targets)==1, 'Production App target missing or ambiguous'
    configs=objects[targets[0]['buildConfigurationList']]['buildConfigurations']
    releases=[i for i in configs if objects[i]['name']=='Release']
    assert len(releases)==1, 'App Release configuration missing or ambiguous'
    cid=releases[0];settings=objects[cid]['buildSettings']
    assert settings['PRODUCT_BUNDLE_IDENTIFIER']=='com.matchgoer.app' and str(settings['CURRENT_PROJECT_VERSION'])=='15' and str(settings['MARKETING_VERSION'])=='0.1.1', 'App identity/version drift'
    updates={'DEVELOPMENT_TEAM':'R58JW38U27','CODE_SIGN_STYLE':'Manual','CODE_SIGN_IDENTITY':identity,'PROVISIONING_PROFILE_SPECIFIER':profile}
    pattern=r'(?ms)(^\s*'+re.escape(cid)+r' /\* Release \*/ = \{.*?buildSettings = \{\n)(.*?)(^\t\t\t\};)'
    matches=list(re.finditer(pattern,text));assert len(matches)==1,'Release settings block ambiguous'
    m=matches[0];body=m.group(2)
    for key,value in updates.items():
        line='\t\t\t\t'+key+' = '+json.dumps(value)+';'
        key_pattern=r'(?m)^\s*'+key+r' = [^\n]*;'
        found=list(re.finditer(key_pattern,body));assert len(found)<=1,'Duplicate signing setting'
        body=re.sub(key_pattern,lambda _:line,body) if found else body+line+'\n'
    return text[:m.start(2)]+body+text[m.end(2):],cid,updates
# End pure target-signing helper.
p=pathlib.Path('native-input/ios/App/App.xcodeproj/project.pbxproj')
def read_project():return json.loads(subprocess.check_output(['plutil','-convert','json','-o','-',str(p)]))
before=read_project();original=p.read_text();fixed,cid,updates=target_signing_patch(original,before,os.environ['SIGNING_CERT_SHA1'],os.environ['SIGNING_PROFILE_NAME']);p.write_text(fixed)
after=read_project();expected=copy.deepcopy(before);expected['objects'][cid]['buildSettings'].update(updates)
assert after==expected,'Non-signing or non-App-target project changes'
# Ensure no parent-level profile can flow into another target; package sources stay untouched.
for oid,obj in after['objects'].items():
    if obj.get('isa')=='XCBuildConfiguration' and oid!=cid:
        assert not obj.get('buildSettings',{}).get('PROVISIONING_PROFILE_SPECIFIER') and not obj.get('buildSettings',{}).get('PROVISIONING_PROFILE'),'App profile inherited by another configuration'
pathlib.Path('evidence/signing-scope-receipt.json').write_text(json.dumps({'scope':'App target Release only','signing_keys':list(updates),'other_project_settings_unchanged':True,'non_app_profile_assignments':0,'global_signing_overrides':False,'third_party_source_modified':False},indent=2))
PY

xcodebuild -version | tee evidence/xcode-version.txt
grep -qx 'Xcode 26.3' evidence/xcode-version.txt || { echo 'STOP: toolchain mismatch'; exit 3; }
xcrun --sdk iphoneos --show-sdk-version | tee evidence/device-sdk.txt
xcodebuild -resolvePackageDependencies -project "$project" -scheme App -clonedSourcePackagesDirPath "$PWD/SourcePackages"
xcodebuild -project "$project" -scheme App -configuration Release -sdk iphoneos \
  -destination 'generic/platform=iOS' -archivePath "$private_dir/Matchgoer.xcarchive" \
  -derivedDataPath "$PWD/DerivedData-signed" -clonedSourcePackagesDirPath "$PWD/SourcePackages" \
  PRODUCT_BUNDLE_IDENTIFIER=com.matchgoer.app MARKETING_VERSION=0.1.1 CURRENT_PROJECT_VERSION=15 \
  archive
app="$private_dir/Matchgoer.xcarchive/Products/Applications/App.app"
codesign --verify --deep --strict "$app"
codesign -d --entitlements :- "$app" > "$private_dir/signed-entitlements.plist" 2>/dev/null
export SIGNING_APP_PATH="$app"
python3 - <<'PY'
import pathlib,os,plistlib,json
p=pathlib.Path(os.environ['SIGNING_APP_PATH']);d=plistlib.loads((p/'Info.plist').read_bytes())
ent=plistlib.loads((pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'signed-entitlements.plist').read_bytes());assert ent.get('com.apple.developer.applesignin')==['Default']
assert d['UIDeviceFamily']==[1] and (p/'PrivacyInfo.xcprivacy').is_file()
assert d['CFBundleIdentifier']=='com.matchgoer.app' and d['CFBundleDisplayName']=='Matchgoer'

config=plistlib.loads((p/'GoogleService-Info.plist').read_bytes())
assert config['BUNDLE_ID']=='com.matchgoer.app' and config['PROJECT_ID']=='matchgoer-40103'
assert config['GOOGLE_APP_ID']=='1:158177709083:ios:50df43974431810e64fcbe'
assert all(d.get(k) is False for k in ['FIREBASE_ANALYTICS_COLLECTION_ENABLED','GOOGLE_ANALYTICS_IDFV_COLLECTION_ENABLED','GOOGLE_ANALYTICS_DEFAULT_ALLOW_ANALYTICS_STORAGE','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_STORAGE','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_USER_DATA','GOOGLE_ANALYTICS_DEFAULT_ALLOW_AD_PERSONALIZATION_SIGNALS','GOOGLE_ANALYTICS_REGISTRATION_WITH_AD_NETWORK_ENABLED','GOOGLE_ADS_ON_DEVICE_CONVERSION_EVENT_DATA_ENABLED','FirebaseAutomaticScreenReportingEnabled'])
assert (p/'native-analytics-rules.json').is_file()

assert d['CFBundleShortVersionString']=='0.1.1' and d['CFBundleVersion']=='15'

import hashlib,subprocess
source=pathlib.Path('native-input/ios/App/App')
source_config_bytes=(source/'GoogleService-Info.plist').read_bytes()
assert hashlib.sha256(source_config_bytes).hexdigest()=='d1a71a73ee41c79184b7c1a1ae01579f510813f0917ccce825ea7bb6f4013613'
assert plistlib.loads((p/'GoogleService-Info.plist').read_bytes())==plistlib.loads(source_config_bytes)
assert (p/'public/bundle.js').read_bytes()==(source/'public/bundle.js').read_bytes()
assert json.loads((p/'native-analytics-rules.json').read_text())==json.loads((source/'native-analytics-rules.json').read_text())
assert 'attendance_recorded' not in json.loads((p/'native-analytics-rules.json').read_text())
# Release linkage: use defined code in the UUID-matched archive dSYM.
def validate_release_linkage(binary_uuid, dsym_uuid, symbols):
    import re
    def identities(output):
        return re.findall(r'UUID:\s*([0-9A-Fa-f-]+)\s+\(([^)]+)\)',output)
    a=identities(binary_uuid);b=identities(dsym_uuid)
    assert len(a)==len(b)==1 and a[0][1]==b[0][1]=='arm64' and a[0][0].lower()==b[0][0].lower(), 'App/dSYM UUID or architecture mismatch'
    methods={
        'firebase_log_event':r'\+\[FIRAnalytics logEventWithName:parameters:\]',
        'firebase_consent_control':r'\+\[FIRAnalytics setAnalyticsCollectionEnabled:\]',
        'bridge_log_event':r'.*MatchgoerAnalyticsPlugin.*logEvent.*',
        'bridge_consent_control':r'.*MatchgoerAnalyticsPlugin.*setState.*',
        'bridge_load':r'.*MatchgoerAnalyticsPlugin.*load.*',
    }
    for label,method in methods.items():
        matches=re.findall(r'(?m)^\s*([0-9a-fA-F]+)\s+[tT]\s+'+method+r'\s*$',symbols)
        assert any(int(address,16)>0 for address in matches), 'Missing defined linked code: '+label
    return {'matched_uuid':a[0][0].lower(),'architecture':'arm64','defined_functions_verified':list(methods)}
# End pure release-linkage validator.
dsym=pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'Matchgoer.xcarchive/dSYMs/App.app.dSYM/Contents/Resources/DWARF/App'
assert dsym.is_file(), 'Archived dSYM missing'
app_uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(p/'App')]).decode()
dsym_uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(dsym)]).decode()
symbols=subprocess.check_output(['xcrun','nm','-n',str(dsym)],stderr=subprocess.DEVNULL).decode(errors='replace')
linkage=validate_release_linkage(app_uuid,dsym_uuid,symbols)
pathlib.Path('evidence/linkage-receipt.json').write_text(json.dumps(linkage,indent=2))

linked=subprocess.check_output(['otool','-L',str(p/'App')]).decode();assert 'AdSupport.framework' not in linked

config=json.loads((p/'capacitor.config.json').read_text());assert config['plugins']['CapacitorHttp']['enabled'] is True and config['plugins']['CapacitorCookies']['enabled'] is False
assert d['ITSAppUsesNonExemptEncryption'] is False
assert d['CFBundleURLTypes']==[{'CFBundleURLName':'com.matchgoer.app.auth','CFBundleURLSchemes':['com.matchgoer.app']}]
assert b'com.matchgoer.app://auth/callback' in (p/'public/bundle.js').read_bytes()
assert d['CFBundleSupportedPlatforms']==['iPhoneOS'] and (p/'embedded.mobileprovision').is_file()
options={'method':'app-store-connect','destination':'export','teamID':'R58JW38U27','signingStyle':'manual','signingCertificate':os.environ['SIGNING_CERT_SHA1'],'provisioningProfiles':{'com.matchgoer.app':plistlib.loads((pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'profile.plist').read_bytes())['Name']},'manageAppVersionAndBuildNumber':False,'testFlightInternalTestingOnly':True}
help_result=subprocess.run(['xcodebuild','-help'],capture_output=True,text=True)
assert 'testFlightInternalTestingOnly' in help_result.stdout+help_result.stderr, 'Internal-only export option unavailable; stop before upload'
(pathlib.Path(os.environ['SIGNING_PRIVATE_DIR'])/'ExportOptions.plist').write_bytes(plistlib.dumps(options))
pathlib.Path('evidence/signing-receipt.json').write_text(json.dumps({'bundle_id':'com.matchgoer.app','version':'0.1.1','build':'15','commit':os.environ['GITHUB_SHA'],'signed_archive':'PASS','codesign_verification':'PASS','upload':'NOT YET ATTEMPTED'},indent=2)+'\n')
PY
xcodebuild -exportArchive -archivePath "$private_dir/Matchgoer.xcarchive" -exportOptionsPlist "$private_dir/ExportOptions.plist" -exportPath "$private_dir/export"
ipa_count="$(find "$private_dir/export" -maxdepth 1 -name '*.ipa' | wc -l | tr -d ' ')"
[[ "$ipa_count" == 1 ]] || { echo 'STOP: expected one exported IPA'; exit 4; }
ipa="$(find "$private_dir/export" -maxdepth 1 -name '*.ipa')"

# Independently verify the actual exported IPA before any upload.
unzip -q "$ipa" -d "$private_dir/ipa-check"
ipa_app_count="$(find "$private_dir/ipa-check/Payload" -maxdepth 1 -name '*.app' | wc -l | tr -d ' ')"
[[ "$ipa_app_count" == 1 ]] || { echo 'STOP: exported IPA application count mismatch'; exit 4; }
ipa_app="$(find "$private_dir/ipa-check/Payload" -maxdepth 1 -name '*.app')"
codesign --verify --deep --strict "$ipa_app"
codesign -d --entitlements :- "$ipa_app" > "$private_dir/ipa-entitlements.plist" 2>/dev/null
security cms -D -i "$ipa_app/embedded.mobileprovision" > "$private_dir/ipa-profile.plist"
codesign -d --extract-certificates "$private_dir/ipa-signing-cert-" "$ipa_app" 2>/dev/null
export SIGNING_IPA_APP="$ipa_app"
python3 - <<'PY'
import pathlib,plistlib,os,json,hashlib,datetime,subprocess
private=pathlib.Path(os.environ['SIGNING_PRIVATE_DIR']);app=pathlib.Path(os.environ['SIGNING_IPA_APP'])
info=plistlib.loads((app/'Info.plist').read_bytes());ent=plistlib.loads((private/'ipa-entitlements.plist').read_bytes());profile=plistlib.loads((private/'ipa-profile.plist').read_bytes());expected=plistlib.loads((private/'profile.plist').read_bytes())
assert info['CFBundleIdentifier']=='com.matchgoer.app' and info['CFBundleShortVersionString']=='0.1.1' and info['CFBundleVersion']=='15'
assert ent['application-identifier']=='R58JW38U27.com.matchgoer.app' and ent['com.apple.developer.team-identifier']=='R58JW38U27' and ent.get('com.apple.developer.applesignin')==['Default'] and not ent.get('get-task-allow')
assert profile['UUID']==expected['UUID'] and profile['TeamIdentifier']==['R58JW38U27'] and not profile.get('ProvisionedDevices') and not profile.get('ProvisionsAllDevices')
assert profile['ExpirationDate']>datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
cert=(private/'ipa-signing-cert-0').read_bytes();assert hashlib.sha1(cert).hexdigest().upper()==os.environ['SIGNING_CERT_SHA1'];assert cert in profile['DeveloperCertificates']
source=pathlib.Path('native-input/ios/App/App')
assert plistlib.loads((app/'GoogleService-Info.plist').read_bytes())==plistlib.loads((source/'GoogleService-Info.plist').read_bytes())
assert (app/'public/bundle.js').read_bytes()==(source/'public/bundle.js').read_bytes()
assert json.loads((app/'native-analytics-rules.json').read_text())==json.loads((source/'native-analytics-rules.json').read_text())
archive_app=private/'Matchgoer.xcarchive/Products/Applications/App.app'
def identity(p):return subprocess.check_output(['xcrun','dwarfdump','--uuid',str(p/'App')]).decode().split('UUID: ',1)[1].split(')')[0]
assert identity(app)==identity(archive_app),'Exported code UUID differs from validated signed archive'
pathlib.Path('evidence/ipa-validation-receipt.json').write_text(json.dumps({'bundle_id':'com.matchgoer.app','version':'0.1.1','build':'15','codesign_verification':'PASS','existing_signing_certificate_match':True,'existing_profile_match':True,'entitlements':'PASS','compiled_candidate_resources_unchanged':True,'archive_executable_uuid_match':True},indent=2))
PY

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
ipa=next((p/'export').glob('*.ipa'));r={'bundle_id':'com.matchgoer.app','version':'0.1.1','build':'15','commit':os.environ['GITHUB_SHA'],'signed_archive':'PASS','ipa_sha256':hashlib.sha256(ipa.read_bytes()).hexdigest(),'upload':'PASS','apple_processing':'PENDING','physical_installation':'PENDING FOUNDER TEST'}
pathlib.Path('evidence/upload-receipt.json').write_text(json.dumps(r,indent=2)+'\n')
PY
printf 'PASS: signed archive exported and uploaded; Apple processing and physical installation still require verification\n' | tee "$evidence/outcome.txt"
