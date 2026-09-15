$ErrorActionPreference = 'Stop'
# Explicit signed builds only. The private certificate is never bundled/uploaded.
if (!$env:DESKTOP_SIGNING_PFX -or !$env:DESKTOP_SIGNING_PASSWORD) { throw 'A signing certificate and password are required' }
$path = Join-Path $env:RUNNER_TEMP 'devtrack-signing.pfx'
try {
    [IO.File]::WriteAllBytes($path, [Convert]::FromBase64String($env:DESKTOP_SIGNING_PFX))
    $password = ConvertTo-SecureString $env:DESKTOP_SIGNING_PASSWORD -AsPlainText -Force
    $cert = Import-PfxCertificate -FilePath $path -CertStoreLocation Cert:\CurrentUser\My -Password $password | Where-Object HasPrivateKey | Select-Object -First 1
    if (!$cert -or !$cert.HasPrivateKey) { throw 'The certificate cannot sign releases' }
    $env:DESKTOP_SIGNING_THUMBPRINT = $cert.Thumbprint
    "DESKTOP_SIGNING_THUMBPRINT=$($cert.Thumbprint)" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
    python -c "import os; from app_version import TRUSTED_SIGNERS; assert os.environ['DESKTOP_SIGNING_THUMBPRINT'].upper() in {s.upper() for s in TRUSTED_SIGNERS}, 'Pin the public signing thumbprint in app_version.py before release'"
    if ($LASTEXITCODE -ne 0) { throw 'The signing publisher is not trusted by this build' }
} finally {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}
