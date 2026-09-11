param(
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DestinationRoot = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ev-purchase-customer-analytics-github-ready')
)

$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$desktop = [Environment]::GetFolderPath('Desktop')
$destination = [System.IO.Path]::GetFullPath($DestinationRoot)
$expectedName = 'ev-purchase-customer-analytics-github-ready'

if ([System.IO.Path]::GetDirectoryName($destination) -ne $desktop -or [System.IO.Path]::GetFileName($destination) -ne $expectedName) {
    throw "Destination must be the expected draft folder directly under Desktop: $expectedName"
}

if (Test-Path -LiteralPath $destination) {
    Remove-Item -LiteralPath $destination -Recurse -Force
}
New-Item -ItemType Directory -Path $destination | Out-Null

function Copy-SafeFile {
    param([string]$RelativePath)
    $from = Join-Path $source $RelativePath
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) {
        throw "Required source file is missing: $RelativePath"
    }
    $to = Join-Path $destination $RelativePath
    $parent = Split-Path -Parent $to
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $to -Force
}

foreach ($file in @(
    'README.md',
    'LICENSE',
    'requirements.txt',
    '.gitignore',
    '.env.example',
    'PUBLICATION_NOTICE.md',
    'data/README.md',
    'notebooks/EV_Purchase_Analytics_Final.ipynb',
    'tools/build_github_safe_package.ps1',
    'tools/sanitize_notebook.py',
    'tools/build_sql_docs.py',
    'tests/verify_public_package.py',
    'tests/verify_mysql_pipeline.py',
    'scripts/run_mysql_pipeline.py',
    'outputs/audit/audit_summary.json',
    'outputs/audit/data_quality_report.md',
    'outputs/audit/data_schema.csv',
    'outputs/audit/missing_values.csv',
    'outputs/audit/train_test_shift.csv',
    'outputs/dashboard/feature_driver.csv',
    'outputs/dashboard/segment_analysis.csv'
)) {
    Copy-SafeFile $file
}

foreach ($pattern in @(
    'src/*.py',
    'src/mysql/*.py',
    'sql/*.sql',
    'docs/sql/*.md',
    'docs/interview/*.md',
    'reports/*.md',
    'outputs/figures/*.png',
    'outputs/tables/*.csv',
    'outputs/sql/*.csv',
    'outputs/sql/*.md'
)) {
    Get-ChildItem -Path (Join-Path $source $pattern) -File | ForEach-Object {
        $relative = $_.FullName.Substring($source.Length + 1)
        Copy-SafeFile $relative
    }
}

python (Join-Path $destination 'tools/sanitize_notebook.py') (Join-Path $destination 'notebooks/EV_Purchase_Analytics_Final.ipynb')
python (Join-Path $destination 'tests/verify_public_package.py') $destination

$zip = "$destination.zip"
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -LiteralPath $destination -DestinationPath $zip -CompressionLevel Optimal
python (Join-Path $destination 'tests/verify_public_package.py') $zip

$fileCount = (Get-ChildItem -LiteralPath $destination -Recurse -File).Count
$totalBytes = (Get-ChildItem -LiteralPath $destination -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Output "Created: $destination"
Write-Output "Created: $zip"
Write-Output "Files: $fileCount"
Write-Output "Folder bytes: $totalBytes"
