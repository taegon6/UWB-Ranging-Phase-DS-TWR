param(
    [string]$TagPort = "COM8",
    [int]$Baud = 115200,
    [double]$BaselineM = 2.5,
    [int]$DurationS = 60,
    [int]$MedianWindow = 1,
    [string]$Tag = "",
    [string]$OutDir = "logs\phase_distance_run",
    [Nullable[double]]$TargetACm = $null,
    [Nullable[double]]$TargetBCm = $null
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = "phase_ds_twr_" + (Get-Date -Format "yyyyMMdd_HHmmss")
}

Write-Host "== UWB phase-corrected DS-TWR experiment set =="
Write-Host "Tag UART: $TagPort @ $Baud"
Write-Host "Anchor A1: (0, 0)"
Write-Host "Anchor B2: ($BaselineM, 0)"
Write-Host "Duration: $DurationS s"
Write-Host "Median window: $MedianWindow"
Write-Host "Run tag: $Tag"
Write-Host "Output dir: $OutDir"
Write-Host ""

$availablePorts = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
if ($availablePorts -notcontains $TagPort) {
    Write-Host "Available serial ports: $($availablePorts -join ', ')"
    throw "Tag port $TagPort is not available. Reconnect the tag board or pass -TagPort COMx."
}

$before = Get-ChildItem -Path $OutDir -Filter "*.position.csv" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName

python tools\collect_tag_two_anchor_position.py `
    --tag-port $TagPort `
    --baud $Baud `
    --duration $DurationS `
    --baseline-m $BaselineM `
    --position-median-window $MedianWindow `
    --tag $Tag `
    --out-dir $OutDir

$after = Get-ChildItem -Path $OutDir -Filter "*.position.csv" |
    Sort-Object LastWriteTime -Descending

$positionCsv = $after |
    Where-Object { $before -notcontains $_.FullName } |
    Select-Object -First 1

if ($null -eq $positionCsv) {
    $positionCsv = $after | Select-Object -First 1
}

if ($null -eq $positionCsv) {
    throw "No position CSV was produced."
}

$positionCsvPath = $positionCsv.FullName
$rawPath = $positionCsvPath -replace "\.position\.csv$", ".raw.txt"
$metaPath = $positionCsvPath -replace "\.position\.csv$", ".meta.json"
$mapPng = $positionCsvPath -replace "\.position\.csv$", ".map.png"
$wavePng = $positionCsvPath -replace "\.position\.csv$", ".distance_wave.png"
$summaryMd = $positionCsvPath -replace "\.position\.csv$", ".summary.md"

$plotArgs = @(
    "tools\plot_distance_waveform.py",
    $positionCsvPath,
    "--out",
    $wavePng,
    "--title",
    "NEW DS-TWR Phase Distance"
)
if ($null -ne $TargetACm) {
    $plotArgs += @("--target-a-cm", "$TargetACm")
}
if ($null -ne $TargetBCm) {
    $plotArgs += @("--target-b-cm", "$TargetBCm")
}

python @plotArgs

$rows = Import-Csv -LiteralPath $positionCsvPath
$validRows = @($rows | Where-Object { $_.status -eq "ok" })
$aDistances = @($rows | ForEach-Object { [double]$_.d_anchor_a_m })
$bDistances = @($rows | ForEach-Object { [double]$_.d_anchor_b_m })

function Mean([double[]]$Values) {
    if ($Values.Count -eq 0) { return [double]::NaN }
    return ($Values | Measure-Object -Average).Average
}

function Std([double[]]$Values) {
    if ($Values.Count -lt 2) { return 0.0 }
    $m = Mean $Values
    $sum = 0.0
    foreach ($v in $Values) { $sum += [Math]::Pow($v - $m, 2) }
    return [Math]::Sqrt($sum / ($Values.Count - 1))
}

$aMeanCm = (Mean $aDistances) * 100.0
$aStdCm = (Std $aDistances) * 100.0
$bMeanCm = (Mean $bDistances) * 100.0
$bStdCm = (Std $bDistances) * 100.0

$summary = @()
$summary += "# UWB Phase DS-TWR Experiment Summary"
$summary += ""
$summary += "- Generated: $(Get-Date -Format s)"
$summary += "- Tag UART: $TagPort @ $Baud"
$summary += "- Baseline: $BaselineM m"
$summary += "- Duration: $DurationS s"
$summary += "- Median window: $MedianWindow"
$summary += "- Total paired samples: $($rows.Count)"
$summary += "- Valid positive-y samples: $($validRows.Count)"
$summary += "- A1 distance mean/std: $($aMeanCm.ToString('F2')) cm / $($aStdCm.ToString('F2')) cm"
$summary += "- B2 distance mean/std: $($bMeanCm.ToString('F2')) cm / $($bStdCm.ToString('F2')) cm"
$summary += ""
$summary += "## Outputs"
$summary += ""
$summary += "- Raw UART log: ``" + $rawPath + "``"
$summary += "- Position CSV: ``" + $positionCsvPath + "``"
$summary += "- Metadata JSON: ``" + $metaPath + "``"
$summary += "- 2D map PNG: ``" + $mapPng + "``"
$summary += "- Distance waveform PNG: ``" + $wavePng + "``"

Set-Content -LiteralPath $summaryMd -Value ($summary -join "`r`n") -Encoding UTF8

Write-Host ""
Write-Host "== Outputs =="
Write-Host "Raw UART log: $rawPath"
Write-Host "Position CSV: $positionCsvPath"
Write-Host "Metadata JSON: $metaPath"
Write-Host "2D map PNG: $mapPng"
Write-Host "Distance waveform PNG: $wavePng"
Write-Host "Summary: $summaryMd"
Write-Host ""
Write-Host "Done."
