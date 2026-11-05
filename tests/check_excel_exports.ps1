param(
    [Parameter(Mandatory = $true)][string]$EvidenceDirectory
)

# Windows + installed Microsoft Excel. Uses a separate hidden instance and never saves files.
$ErrorActionPreference = 'Stop'
$directory = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
$expected = Get-Content -LiteralPath (Join-Path $directory 'observations.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$summary = $expected.summary
$excel = $null
$workbook = $null
$checks = @()
function Assert-Equal($actual, $wanted, [string]$label) {
    if ($actual -ne $wanted) { throw "$label`: expected '$wanted', received '$actual'" }
}
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AutomationSecurity = 3
    foreach ($format in @('xlsx', 'csv')) {
        $path = Join-Path $directory "order.$format"
        if ($format -eq 'xlsx') {
            # Normal read-only open, no repair mode or link updates.
            $workbook = $excel.Workbooks.Open($path, 0, $true)
            Assert-Equal $workbook.Worksheets.Count 2 'Sheet count'
            Assert-Equal $workbook.Worksheets.Item(1).Name 'Блюда' 'First sheet'
            Assert-Equal $workbook.Worksheets.Item(2).Name 'По сотрудникам' 'Second sheet'
            $people = $workbook.Worksheets.Item(2)
            Assert-Equal $people.UsedRange.Rows.Count ($summary.by_employee.Count + 1) 'Employee row count'
            for ($i = 0; $i -lt $summary.by_employee.Count; $i++) {
                $person = $summary.by_employee[$i]
                Assert-Equal $people.Cells.Item($i + 2, 2).Value2 $person.full_name 'Employee name'
                Assert-Equal $people.Cells.Item($i + 2, 5).Value2 $person.actual_total_kopecks 'Employee total'
            }
        } else {
            # UTF-8, delimited, double-quoted fields, comma delimiter; independent of regional settings.
            $excel.Workbooks.OpenText($path, 65001, 1, 1, 1, $false, $false, $false, $true)
            $workbook = $excel.ActiveWorkbook
        }
        $sheet = $workbook.Worksheets.Item(1)
        Assert-Equal $sheet.UsedRange.Columns.Count 5 'Dish column count'
        Assert-Equal $sheet.UsedRange.Rows.Count ($summary.items.Count + 1) 'Dish row count'
        Assert-Equal $sheet.Cells.Item(1, 5).Value2 'line_total_kopecks' 'Money header'
        $total = 0L
        for ($i = 0; $i -lt $summary.items.Count; $i++) {
            $dish = $summary.items[$i]
            Assert-Equal $sheet.Cells.Item($i + 2, 2).Value2 $dish.name 'Cyrillic dish name'
            Assert-Equal $sheet.Cells.Item($i + 2, 3).Value2 $dish.qty 'Quantity'
            Assert-Equal $sheet.Cells.Item($i + 2, 4).Value2 $dish.unit_price_kopecks 'Unit price'
            Assert-Equal $sheet.Cells.Item($i + 2, 5).Value2 $dish.line_total_kopecks 'Line total'
            if ($sheet.Cells.Item($i + 2, 5).Value2 -isnot [double]) { throw 'Excel total cell is not numeric' }
            $total += $sheet.Cells.Item($i + 2, 5).Value2
        }
        Assert-Equal $total $summary.totals.actual_kopecks 'Total versus API'
        $checks += [ordered]@{
            format = $format
            opening = if ($format -eq 'xlsx') { 'normal read-only, no repair' } else { 'UTF-8 comma import' }
            dish_rows = $summary.items.Count
            total_kopecks = $total
            cyrillic_and_numeric_cells = 'PASS'
        }
        $workbook.Close($false)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
        $workbook = $null
    }
    $result = [ordered]@{ checked_at = (Get-Date).ToUniversalTime().ToString('o'); excel_version = $excel.Version; delivery_date = $summary.delivery_date; result = 'PASS'; checks = $checks }
    $json = ($result | ConvertTo-Json -Depth 8) -replace "`r`n", "`n"
    [IO.File]::WriteAllText((Join-Path $directory 'excel-results.json'), $json + "`n", [Text.UTF8Encoding]::new($false))
    Write-Output $json
} finally {
    if ($null -ne $workbook) { $workbook.Close($false) }
    if ($null -ne $excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
