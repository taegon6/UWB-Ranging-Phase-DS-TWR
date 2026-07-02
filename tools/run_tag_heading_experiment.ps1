param(
    [string]$TagPort = "COM8",
    [int]$Baud = 115200,
    [double]$BaselineM = 2.5,
    [ValidateSet("Static", "Moving")]
    [string]$Mode = "Moving",
    [int]$DurationS = 60,
    [string]$Tag = "",
    [int]$StaticMedianWindow = 90,
    [int]$MovingMedianWindow = 10,
    [double]$PcaWindowS = 1.0,
    [double]$MeasurementStdX = 0.10,
    [double]$MeasurementStdY = 0.08,
    [double]$AccelStd = 0.4,
    [double]$MovingSpeedThreshold = 0.15,
    [string]$OutDir = "logs\tag_heading_run"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Tag = ("{0}_{1}" -f $Mode.ToLowerInvariant(), $stamp)
}

if ($Mode -eq "Static") {
    $medianWindow = $StaticMedianWindow
} else {
    $medianWindow = $MovingMedianWindow
}

Write-Host "== UWB tag-side two-anchor experiment =="
Write-Host "Mode: $Mode"
Write-Host "Tag UART: $TagPort @ $Baud"
Write-Host "Anchor A1: (0, 0)"
Write-Host "Anchor B2: ($BaselineM, 0)"
Write-Host "Duration: $DurationS s"
Write-Host "Position median window: $medianWindow"
Write-Host "Run tag: $Tag"
Write-Host "Output dir: $OutDir"
Write-Host ""

$availablePorts = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
if ($availablePorts -notcontains $TagPort) {
    Write-Host "Available serial ports: $($availablePorts -join ', ')"
    throw "Tag port $TagPort is not available. Reconnect the tag board or pass the current port with -TagPort COMx."
}

$before = Get-ChildItem -Path $OutDir -Filter "*.position.csv" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName

python tools\collect_tag_two_anchor_position.py `
    --tag-port $TagPort `
    --baud $Baud `
    --duration $DurationS `
    --baseline-m $BaselineM `
    --position-median-window $medianWindow `
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

Write-Host ""
Write-Host "Position CSV: $($positionCsv.FullName)"

if ($Mode -eq "Moving") {
    $headingCsv = [System.IO.Path]::ChangeExtension($positionCsv.FullName, ".heading_kalman.csv")
    $headingPng = [System.IO.Path]::ChangeExtension($positionCsv.FullName, ".heading_kalman.png")
    $positionArg = Resolve-Path -Relative $positionCsv.FullName
    $headingCsvArg = Resolve-Path -Relative (Split-Path -Parent $headingCsv)
    $headingCsvArg = Join-Path $headingCsvArg (Split-Path -Leaf $headingCsv)
    $headingPngArg = Resolve-Path -Relative (Split-Path -Parent $headingPng)
    $headingPngArg = Join-Path $headingPngArg (Split-Path -Leaf $headingPng)

    Write-Host ""
    Write-Host "== Kalman + heading analysis =="
    python tools\analyze_heading_kalman.py $positionArg `
        --out-csv $headingCsvArg `
        --plot $headingPngArg `
        --measurement-source raw `
        --pca-window-s $PcaWindowS `
        --measurement-std-x $MeasurementStdX `
        --measurement-std-y $MeasurementStdY `
        --accel-std $AccelStd `
        --moving-speed-threshold $MovingSpeedThreshold

    Write-Host ""
    Write-Host "Heading CSV: $headingCsv"
    Write-Host "Heading PNG: $headingPng"
} else {
    Write-Host ""
    Write-Host "Static mode finished. Use the map PNG and position CSV for repeatability/std analysis."
}

Write-Host ""
Write-Host "Done."
