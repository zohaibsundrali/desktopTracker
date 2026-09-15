param([Parameter(Mandatory=$true)][string]$FilePath)
$ErrorActionPreference = 'Stop'
if ($env:DESKTOP_SIGNING_THUMBPRINT -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Signing publisher is not configured' }
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
if (!$signTool) { throw 'Windows SDK signing tool is unavailable' }
& $signTool.FullName sign /sha1 $env:DESKTOP_SIGNING_THUMBPRINT /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $FilePath
if ($LASTEXITCODE -ne 0) { throw 'Code signing failed' }
$signature = Get-AuthenticodeSignature -LiteralPath $FilePath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $env:DESKTOP_SIGNING_THUMBPRINT) {
    throw 'Signed file failed publisher verification'
}
