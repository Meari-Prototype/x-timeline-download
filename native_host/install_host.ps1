param(
  [string]$ExtensionId
)

$ErrorActionPreference = 'Stop'

function Normalize-PathForCompare {
  param([string]$Path)

  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $null
  }

  try {
    $normalized = (Resolve-Path -LiteralPath $Path).Path
  } catch {
    try {
      $normalized = [System.IO.Path]::GetFullPath($Path)
    } catch {
      $normalized = $Path
    }
  }

  return $normalized.TrimEnd([char[]]@('\', '/'))
}

function Find-ChromeExtensionId {
  param([Parameter(Mandatory = $true)][string]$ExtensionPath)

  $targetPath = Normalize-PathForCompare $ExtensionPath
  $chromeUserData = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'
  if (-not (Test-Path -LiteralPath $chromeUserData)) {
    return $null
  }

  $foundExtensions = @()
  foreach ($profile in Get-ChildItem -LiteralPath $chromeUserData -Directory) {
    foreach ($preferencesFile in @('Preferences', 'Secure Preferences')) {
      $preferencesPath = Join-Path $profile.FullName $preferencesFile
      if (-not (Test-Path -LiteralPath $preferencesPath)) {
        continue
      }

      try {
        $preferences = Get-Content -Raw -Encoding UTF8 -LiteralPath $preferencesPath | ConvertFrom-Json
      } catch {
        continue
      }

      $settings = $preferences.extensions.settings
      if ($null -eq $settings) {
        continue
      }

      foreach ($property in $settings.PSObject.Properties) {
        if ($property.Name -notmatch '^[a-p]{32}$') {
          continue
        }

        $installedPath = Normalize-PathForCompare $property.Value.path
        if ($installedPath -and [string]::Equals($installedPath, $targetPath, [System.StringComparison]::OrdinalIgnoreCase)) {
          $foundExtensions += [pscustomobject]@{
            Id = $property.Name
            Profile = "$($profile.Name)/$preferencesFile"
          }
        }
      }
    }
  }

  $uniqueIds = @($foundExtensions | Select-Object -ExpandProperty Id -Unique)
  if ($uniqueIds.Count -eq 1) {
    return $uniqueIds[0]
  }

  if ($uniqueIds.Count -gt 1) {
    $detail = ($foundExtensions | ForEach-Object { "$($_.Id)（$($_.Profile)）" }) -join '、'
    throw "找到多个已加载的本项目扩展 ID：$detail。请使用 -ExtensionId 指定其中一个。"
  }

  return $null
}

$hostName = 'com.master.x_tweet_fetcher'
$hostDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $hostDir
$extensionDir = Join-Path $projectDir 'extension'
$hostPath = Join-Path $hostDir 'x_capture_host.bat'
$manifestPath = Join-Path $hostDir "$hostName.json"
$registryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName"

if (-not (Test-Path -LiteralPath $hostPath)) {
  throw "Native host launcher not found: $hostPath"
}

if ($ExtensionId -and $ExtensionId -notmatch '^[a-p]{32}$') {
  throw "扩展 ID 格式不正确：$ExtensionId。Chrome 扩展 ID 必须是 32 位 a-p 小写字母。"
}

$resolvedExtensionId = $ExtensionId

if (-not $resolvedExtensionId) {
  Write-Host "正在从 Chrome 配置自动查找本项目扩展 ID..."
  $resolvedExtensionId = Find-ChromeExtensionId -ExtensionPath $extensionDir
}

if (-not $resolvedExtensionId) {
  throw "未能自动找到本项目扩展 ID。请先在 chrome://extensions 加载 $extensionDir，或使用 -ExtensionId 手动指定。"
}

$manifest = [ordered]@{
  name = $hostName
  description = 'X 时间线下载 Native Messaging host'
  path = $hostPath
  type = 'stdio'
  allowed_origins = @("chrome-extension://$resolvedExtensionId/")
}

$manifestJson = $manifest | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)
New-Item -Path $registryPath -Force | Out-Null
Set-Item -Path $registryPath -Value $manifestPath

Write-Host "已注册 $hostName"
Write-Host "Manifest: $manifestPath"
Write-Host "允许的扩展: chrome-extension://$resolvedExtensionId/"

