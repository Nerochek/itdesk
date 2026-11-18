param([string]$InputFile = "analytics_data/clean.jsonl", [string]$OutputPath = "analytics_data/hadoop-output")
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $projectRoot
try {
    python -m analytics.mapreduce.run --input $InputFile --output $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "Hadoop failed: $LASTEXITCODE" }
} finally { Pop-Location }
