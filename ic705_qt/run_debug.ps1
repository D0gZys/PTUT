param(
  [ValidateSet("Debug", "Release")]
  [string]$Config = "Debug",
  [string]$QtPrefix = "C:\\Qt\\6.11.0\\msvc2022_64"
)

$exe = Join-Path $PSScriptRoot ("build\\{0}\\ic705_qt.exe" -f $Config)
if (-not (Test-Path $exe)) {
  Write-Error "Executable not found: $exe"
  exit 1
}

$qtBin = Join-Path $QtPrefix "bin"
if (Test-Path $qtBin) {
  $env:Path = "$qtBin;$env:Path"
} else {
  Write-Warning "Qt bin not found at: $qtBin (continuing without PATH update)"
}

Write-Host "Running: $exe"
& $exe
Write-Host "ExitCode: $LASTEXITCODE"

