param(
  [switch]$CleanRemote = $false
)
$ErrorActionPreference = "Stop"
Write-Output "===== AO Versioner (Rules + Redaction) [SAFE CLEAN] ====="
if ($CleanRemote) { Write-Output ">>> CLEAN MODE ENABLED (remote history will be reset) <<<" }

# Prefilled credentials (as provided)
$env:REPO_SLUG = "jmdrumsgarrison-ux/agentic-orchestrator"
$env:GITHUB_TOKEN = "SecretStrippedByGitPush"
$env:DEFAULT_COMMITTER_NAME = "J. Morrissette"
$env:DEFAULT_COMMITTER_EMAIL = "jm.drums.garrison@gmail.com"

$RepoSlug       = $env:REPO_SLUG
$GitHubToken    = $env:GITHUB_TOKEN
$CommitterName  = $env:DEFAULT_COMMITTER_NAME
$CommitterEmail = $env:DEFAULT_COMMITTER_EMAIL

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git not installed/in PATH" }
if (-not $RepoSlug)    { throw "REPO_SLUG not set" }
if (-not $GitHubToken) { throw "GITHUB_TOKEN not set" }
if (-not $CommitterName)  { $CommitterName = $env:USERNAME }
if (-not $CommitterEmail) { $CommitterEmail = "$($env:USERNAME)@users.noreply.github.com" }

if (-not (Test-Path ".git")) { git init | Out-Null }
git config user.name "$CommitterName"
git config user.email "$CommitterEmail"
git config core.autocrlf true
if (-not (Test-Path ".gitignore")) { Set-Content -Path ".gitignore" -Value "secrets/`nrun_AO_rules_redact*.bat`nbuild_AO_rules_redact.ps1`n" }

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$RedactionReport = "Logs\\RedactionReport-$ts.txt"
New-Item -ItemType File -Path $RedactionReport -Force | Out-Null
Add-Content $RedactionReport "AO Versioner Redaction Report ($ts)"
Add-Content $RedactionReport "==================================="

$allZips = Get-ChildItem "Drops" -Filter *.zip -ErrorAction SilentlyContinue | Sort-Object Name
if (-not $allZips -or $allZips.Count -eq 0) { throw "No zips found in .\Drops" }

$reDrop = [regex]'(?i)(?:drop|space[_\-]?drop)\s*([0-9]+)'
$reSemver = [regex]'v(?<maj>\d+)\.(?<min>\d+)\.(?<pat>\d+)'

function Redact-File($path) {
  $binExt = @(".png",".jpg",".jpeg",".gif",".bmp",".pdf",".mp4",".mov",".avi",".mkv",".zip",".7z",".tar",".gz",".exe",".dll",".so",".bin",".pt",".pth",".onnx",".tflite",".woff",".woff2",".ttf")
  if ($binExt -contains ([System.IO.Path]::GetExtension($path).ToLower())) { return 0 }
  $fi = Get-Item $path -ErrorAction SilentlyContinue
  if (-not $fi -or $fi.Length -gt 5MB) { return 0 }
  try {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    for ($i=0; $i -lt [Math]::Min($bytes.Length, 8000); $i++) { if ($bytes[$i] -eq 0) { return 0 } }
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
  } catch { return 0 }

  $orig = $text
  $patterns = @(
    '(?im)^(?<k>[\w\.\-]*?(token|apikey|api_key|secret|password)[\w\.\-]*?)\s*[:=]\s*(?<q>["'']?)(?<v>[^"''\r\n#]+)(\k<q>)?',
    '(?i)"(?<k>[^"]*(token|apikey|api_key|secret|password)[^"]*)"\s*:\s*"(?<v>[^"]+)"',
    "(?i)'(?<k>[^']*(token|apikey|api_key|secret|password)[^']*)'\s*:\s*'(?<v>[^']+)'",
    '(?i)\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{30,}',
    '(?i)\bhf_[A-Za-z0-9]{30,}',
    '(?i)\bxox[abp]-[A-Za-z0-9-]{20,}',
    '(?i)\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}'
  )

  foreach ($p in $patterns) {
    $text = [System.Text.RegularExpressions.Regex]::Replace($text, $p, {
      param($m)
      if ($m.Groups['k'].Success -and $m.Groups['v'].Success) {
        return $m.Value -replace [System.Text.RegularExpressions.Regex]::Escape($m.Groups['v'].Value), 'SecretStrippedByGitPush'
      } else {
        return 'SecretStrippedByGitPush'
      }
    })
  }

  if ($text -ne $orig) {
    Set-Content -Path $path -Value $text -Encoding UTF8
    Add-Content $RedactionReport ("[REDACTED] " + $path)
    return 1
  }
  return 0
}
function Redact-Tree($root) {
  $total = 0
  Get-ChildItem -Path $root -Recurse -File | ForEach-Object { $total += (Redact-File $_.FullName) }
  return $total
}

function Safe-Clean-Workspace {
  $keepExact = @('README.txt','.gitignore','.git','Drops','Logs','secrets','build_AO_rules_redact.ps1')
  Get-ChildItem -Force | Where-Object {
    ($_.Name -notin $keepExact) -and
    ($_.Name -notlike 'run_AO_rules_redact*.bat')
  } | ForEach-Object {
    if ($_.PSIsContainer) { Remove-Item $_ -Recurse -Force } else { Remove-Item $_ -Force }
  }
}

# Ensure baseline v0.0.0 exists locally
$v000_exists = $false
try { if ((git tag -l v0.0.0).Trim() -eq 'v0.0.0') { $v000_exists = $true } } catch {}

if (-not $v000_exists) {
  $drop66 = $allZips | Where-Object { $reDrop.IsMatch($_.Name) -and [int]$reDrop.Match($_.Name).Groups[1].Value -eq 66 } | Select-Object -First 1
  if (-not $drop66) { throw "v0.0.0 not found AND Drop66 zip not supplied. Provide Drop66 in Drops." }

  Write-Output ("Baselining from: {0}" -f $drop66.Name)
  Safe-Clean-Workspace

  if (Test-Path "_extract") { Remove-Item "_extract" -Recurse -Force }
  New-Item -ItemType Directory -Path "_extract" | Out-Null
  try { Expand-Archive -LiteralPath $drop66.FullName -DestinationPath "_extract" -Force }
  catch { & tar -xf $drop66.FullName -C _extract }

  $top = Get-ChildItem _extract | Where-Object {$_.PSIsContainer} | Select-Object -First 1
  if ($top) { Copy-Item -Path (Join-Path $top.FullName '*') -Destination "." -Recurse -Force } else { Copy-Item -Path "_extract\*" -Destination "." -Recurse -Force }

  Redact-Tree "." | Out-Null
  git add -A
  git commit -m "[AO] Baseline from Drop66 (redacted)" | Out-Null
  git tag -a v0.0.0 -m "AO baseline from Drop66"
}

# Optional CLEAN
if ($CleanRemote) {
  git branch -M main
  try { git remote remove origin 2>$null } catch {}
  $remote = "https://$GitHubToken@github.com/$RepoSlug.git"
  git remote add origin $remote

  Write-Output ">>> CLEAN: resetting remote main to v0.0.0 and deleting remote tags (except v0.0.0)"
  git push origin +refs/tags/v0.0.0:refs/heads/main 2>&1 | Write-Output

  $remoteTags = git ls-remote --tags origin | ForEach-Object {
    $p = $_.Split("`t")[-1]
    if ($p) { $p.Trim() -replace 'refs/tags/','' }
  } | Where-Object { $_ -and ($_ -ne "v0.0.0") } | Sort-Object -Unique
  foreach ($t in $remoteTags) {
    Write-Output ("Deleting remote tag: {0}" -f $t)
    git push origin --delete "refs/tags/$t" 2>&1 | Write-Output
  }
  git push origin v0.0.0 2>&1 | Write-Output
}

# Partition zips
$dropZips = @()
$verZips  = @()
foreach ($z in $allZips) {
  $mDrop = $reDrop.Match($z.Name)
  $mSem  = $reSemver.Match($z.Name)
  if ($mSem.Success) {
    if ([int]$mSem.Groups['maj'].Value -eq 0) { $verZips += $z }
    continue
  }
  if ($mDrop.Success) {
    $n = [int]$mDrop.Groups[1].Value
    if ($n -ge 67) { $dropZips += $z }
  }
}
$dropZips = $dropZips | Sort-Object { [int]$reDrop.Match($_.Name).Groups[1].Value }
$verZips  = $verZips  | Sort-Object {
  $m = $reSemver.Match($_.Name)
  [int]$m.Groups['maj'].Value*1000000 + [int]$m.Groups['min'].Value*1000 + [int]$m.Groups['pat'].Value
}

$nextPatch = 1
try {
  $existing = git tag | Select-String -Pattern '^v0\.0\.(\d+)$' | ForEach-Object {
    $m = [regex]::Match($_.ToString(), '^v0\.0\.(\d+)$')
    if ($m.Success) { [int]$m.Groups[1].Value }
  }
  if ($existing) { $nextPatch = ([int]($existing | Measure-Object -Maximum).Maximum) + 1 }
} catch {}

function Apply-Archive($zipPath, $commitMsg) {
  Safe-Clean-Workspace

  if (Test-Path "_extract") { Remove-Item "_extract" -Recurse -Force }
  New-Item -ItemType Directory -Path "_extract" | Out-Null
  try { Expand-Archive -LiteralPath $zipPath -DestinationPath "_extract" -Force }
  catch { & tar -xf $zipPath -C _extract }

  $top = Get-ChildItem _extract | Where-Object {$_.PSIsContainer} | Select-Object -First 1
  if ($top) { Copy-Item -Path (Join-Path $top.FullName '*') -Destination "." -Recurse -Force } else { Copy-Item -Path "_extract\*" -Destination "." -Recurse -Force }

  Redact-Tree "." | Out-Null
  git add -A
  git commit -m $commitMsg | Out-Null
}

foreach ($z in $dropZips) {
  Write-Output ("Applying Drop>=67: {0}" -f $z.Name)
  Apply-Archive -zipPath $z.FullName -commitMsg ("[AO] Import " + $z.Name)
  $tag = ("v0.0.{0}" -f $nextPatch)
  git tag -a $tag -m ("AO " + $tag + " from " + $z.Name)
  Write-Output ("Tagged: {0}" -f $tag)
  $nextPatch += 1
}

foreach ($z in $verZips) {
  $m = $reSemver.Match($z.Name)
  $ver = ("v{0}.{1}.{2}" -f $m.Groups['maj'].Value, $m.Groups['min'].Value, $m.Groups['pat'].Value)
  Write-Output ("Applying explicit version: {0} -> {1}" -f $z.Name, $ver)
  Apply-Archive -zipPath $z.FullName -commitMsg ("[AO] Import " + $z.Name)
  $existingTag = git tag -l $ver
  if ($existingTag -and $existingTag.Trim()) {
    git tag -f $ver
  } else {
    git tag -a $ver -m ("AO " + $ver + " from " + $z.Name)
  }
  Write-Output ("Tagged: {0}" -f $ver)
}

git branch -M main
try { git remote remove origin 2>$null } catch {}
$remote = "https://$GitHubToken@github.com/$RepoSlug.git"
git remote add origin $remote

Write-Output "Pushing main (force)"
git push -u origin main --force 2>&1 | Write-Output
Write-Output "Pushing all tags"
git push origin --tags 2>&1 | Write-Output

Write-Output "Done."

