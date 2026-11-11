param(
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [Parameter(Mandatory=$true)][string]$IdentityFile,
    [string]$Image = 'matchgoer-postgres-backup:20261110'
)
$ErrorActionPreference = 'Stop'
# FOUNDER-RUN ONLY. Codex must not request or access the identity file.
# Inputs: database.dump.age, verification.json.age, receipt.json downloaded by
# the founder from one verified R2 recovery point. Never supply production URLs.
$backupPath = (Resolve-Path -LiteralPath $BackupDirectory).Path
$identityPath = (Resolve-Path -LiteralPath $IdentityFile).Path
foreach ($required in @('database.dump.age','verification.json.age','receipt.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $backupPath $required) -PathType Leaf)) {
        throw 'Required encrypted recovery-point file is missing.'
    }
}
$runTag = [guid]::NewGuid().ToString('N').Substring(0,12)
$network = 'matchgoer-disposable-restore-' + $runTag
$databaseContainer = 'matchgoer-disposable-db-' + $runTag
$restoreContainer = 'matchgoer-disposable-client-' + $runTag
$databaseName = 'matchgoer_restore_' + $runTag
$networkCreated = $false
$databaseCreated = $false
try {
    $null = & docker network create --internal $network
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Docker network creation failed.' }
    $networkCreated = $true
    $null = & docker run --detach --pull never --platform linux/amd64 --name $databaseContainer --network $network --network-alias restore-db --log-driver none --user root --entrypoint docker-entrypoint.sh --tmpfs /var/lib/postgresql:rw,size=1g --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_USER=postgres --env "POSTGRES_DB=$databaseName" $Image postgres
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL startup failed.' }
    $databaseCreated = $true
    $ready = $false
    for ($try = 0; $try -lt 45; $try++) {
        $null = & docker exec $databaseContainer pg_isready --quiet -U postgres -d $databaseName 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Disposable PostgreSQL readiness timed out.' }
    $output = & docker run --rm --pull never --platform linux/amd64 --name $restoreContainer --network $network --log-driver none --user root --tmpfs /tmp:rw,size=128m,mode=1777 --mount "type=bind,source=$backupPath,target=/recovery,readonly" --mount "type=bind,source=$identityPath,target=/run/recovery-identity,readonly" --env "RESTORE_DATABASE_URL=postgresql://postgres:disposable@restore-db/$databaseName" $Image python /app/restore_check.py --archive /recovery/database.dump.age --verification /recovery/verification.json.age --receipt /recovery/receipt.json --identity /run/recovery-identity
    if ($LASTEXITCODE -ne 0) { throw 'Disposable restore validation failed; private data and tool diagnostics were suppressed.' }
    $result = ($output | Select-Object -Last 1) | ConvertFrom-Json
    if ($result.event -ne 'DISPOSABLE_RESTORE_RESULT' -or $result.passed -ne $true) { throw 'Restore did not return a passing validation receipt.' }
    $receipt = [ordered]@{
        checked_at_utc = [DateTime]::UtcNow.ToString('o')
        passed = $result.passed
        recovery_seconds = $result.recovery_seconds
        tables_verified = $result.tables_verified
        all_row_fingerprints_match = $result.all_row_fingerprints_match
        production_connected = $false
        private_key_printed_or_copied = $false
        founder_executed = $true
        data_stored_in_disposable_tmpfs = $true
        limitation = 'Local restore duration excludes incident diagnosis, download and production cutover.'
    }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'founder-disposable-restore-receipt.json') -Encoding UTF8
    $receipt | ConvertTo-Json
}
finally {
    # Names are unique identifiers created by this script; never enumerate or
    # remove other Docker objects. PostgreSQL data lives only in tmpfs.
    if ($databaseCreated) { $null = & docker rm --force $databaseContainer 2>$null }
    $null = & docker rm --force $restoreContainer 2>$null
    if ($networkCreated) { $null = & docker network rm $network 2>$null }
}
