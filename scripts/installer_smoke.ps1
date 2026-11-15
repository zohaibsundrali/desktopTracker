# Exercise the actual installer on the disposable Windows CI runner.
# This is offline packaging evidence; it does not certify employee capture.
$ErrorActionPreference = 'Stop'
if ($env:CI -ne 'true' -or !$env:RUNNER_TEMP) {
    throw 'Run this installer test only on a disposable CI runner.'
}
$output = Join-Path $PWD 'Output'
$installDir = Join-Path $env:RUNNER_TEMP ('Verisade Installer Smoke ' + [guid]::NewGuid().ToString('N'))
$diagnosticsPath = Join-Path $output 'installed-desktop-diagnostics.json'
$reportPath = Join-Path $output 'installer-smoke.json'
$uninstaller = Join-Path $installDir 'unins000.exe'
$report = [ordered]@{
    scope = 'ci_installer_and_offline_diagnostics'
    windows_10_11_acceptance = $false
    install = 'not_run'
    installed_diagnostics = 'not_run'
    uninstall = 'not_run'
}

function Invoke-CheckedProcess([string]$File, [string[]]$Arguments, [int]$Timeout = 120000) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    if (!$process.WaitForExit($Timeout)) {
        $process.Kill()
        throw 'Installer smoke process timed out.'
    }
    if ($process.ExitCode -ne 0) { throw "Installer smoke process failed: exit $($process.ExitCode)" }
}

try {
    Invoke-CheckedProcess (Join-Path $output 'DeveloperTracker-Setup.exe') @(
        '/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RESTARTEXITCODE=3010',
        '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/NOICONS',
        "/DIR=`"$installDir`"", "/LOG=`"$(Join-Path $output 'install-smoke.log')`""
    )
    $exe = Join-Path $installDir 'DeveloperTracker.exe'
    if (!(Test-Path $exe) -or !(Test-Path $uninstaller)) { throw 'Installed application or uninstaller is missing.' }
    $report.install = 'pass'
    Invoke-CheckedProcess $exe @('--diagnostics', "`"$diagnosticsPath`"") 60000
    $diagnostics = Get-Content $diagnosticsPath -Raw | ConvertFrom-Json
    $manifest = Get-Content (Join-Path $output 'release-manifest.json') -Raw | ConvertFrom-Json
    if (!$diagnostics.ready_for_manual_test -or $diagnostics.app_version -ne $manifest.version) {
        throw 'Installed diagnostics or version verification failed.'
    }
    $report.installed_diagnostics = 'pass'
} finally {
    try {
        if (Test-Path $uninstaller) {
            Invoke-CheckedProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
            if (Test-Path (Join-Path $installDir 'DeveloperTracker.exe')) { throw 'Uninstall left the application executable behind.' }
            $report.uninstall = 'pass'
        }
    } finally {
        $report | ConvertTo-Json | Set-Content $reportPath -Encoding utf8
    }
}
