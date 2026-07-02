param(
    [Parameter(Mandatory=$true)]
    [string]$PortA,

    [Parameter(Mandatory=$true)]
    [string]$PortB,

    [double]$BaselineM = 2.5,
    [ValidateSet("ss-twr", "ds-twr")]
    [string]$RangingMode = "ds-twr",
    [int]$DurationS = 60,
    [int]$MedianWindow = 30,
    [string]$Tag = "two_anchor_main",
    [int]$Baud = 115200
)

$ErrorActionPreference = "Stop"

Write-Host "== UWB two-anchor main experiment =="
Write-Host "Anchor A: $PortA -> (0, 0)"
Write-Host "Anchor B: $PortB -> ($BaselineM, 0)"
Write-Host "Ranging mode: $RangingMode"
Write-Host "Duration: $DurationS s"
Write-Host "Position median window: $MedianWindow"
Write-Host "Tag: $Tag"
Write-Host ""

python tools\collect_two_anchor_position.py `
    --port-a $PortA `
    --port-b $PortB `
    --baud $Baud `
    --baseline-m $BaselineM `
    --ranging-mode $RangingMode `
    --duration $DurationS `
    --position-median-window $MedianWindow `
    --tag $Tag

Write-Host ""
Write-Host "== Analyzing two-anchor position logs =="
python tools\analyze_two_anchor_positions.py --log-dir logs --out-dir analysis

Write-Host ""
Write-Host "Done."
Write-Host "Map images: logs\*.map.png"
Write-Host "Position CSV: logs\*.position.csv"
Write-Host "Summary: analysis\two_anchor_position_summary.md"
