$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root '.github'
$dst = Join-Path $root '.continue\rules'

New-Item -ItemType Directory -Force -Path $dst | Out-Null
Get-ChildItem -Path $dst -Filter 'github-*.md' -ErrorAction SilentlyContinue | Remove-Item

$count = 0
Get-ChildItem -Path $src -Recurse -Filter '*.md' -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length + 1) -replace '[\\/]', '-'
    Copy-Item -Path $_.FullName -Destination (Join-Path $dst ('github-' + $rel))
    $count++
}

Write-Output "Synced $count markdown file(s) from .github to .continue/rules"
