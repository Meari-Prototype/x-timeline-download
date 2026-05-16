param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[a-p]{32}$')]
  [string]$ExtensionId
)

$ErrorActionPreference = 'Stop'

$hostName = 'com.master.x_tweet_fetcher'
$hostDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$hostPath = Join-Path $hostDir 'x_capture_host.bat'
$manifestPath = Join-Path $hostDir "$hostName.json"
$registryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName"

if (-not (Test-Path -LiteralPath $hostPath)) {
  throw "Native host launcher not found: $hostPath"
}

$manifest = [ordered]@{
  name = $hostName
  description = 'Native host for X Timeline Local Capture'
  path = $hostPath
  type = 'stdio'
  allowed_origins = @("chrome-extension://$ExtensionId/")
}

$manifestJson = $manifest | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)
New-Item -Path $registryPath -Force | Out-Null
Set-Item -Path $registryPath -Value $manifestPath

Write-Host "Registered $hostName"
Write-Host "Manifest: $manifestPath"
Write-Host "Allowed extension: chrome-extension://$ExtensionId/"
