param(
    [Parameter(Mandatory=$true)][string]$DatabasePath,
    [string]$OutputDir = ".\access_export"
)

$ErrorActionPreference = "Stop"
$DatabasePath = (Resolve-Path $DatabasePath).Path
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

function New-DaoEngine {
    foreach ($progId in @("DAO.DBEngine.120", "DAO.DBEngine.36")) {
        try { return New-Object -ComObject $progId } catch { }
    }
    throw "No DAO engine found. Install Microsoft Access or the Microsoft Access Database Engine, then retry."
}

function Safe-Name([string]$name) {
    return ($name -replace '[\\/:*?"<>|]', '_')
}

function Csv-Cell($value) {
    if ($null -eq $value -or [System.DBNull]::Value.Equals($value)) { return '""' }
    if ($value -is [byte[]]) { return '"[BINARY]"' }
    $s = [string]$value
    return '"' + ($s -replace '"', '""') + '"'
}

$engine = New-DaoEngine
$db = $engine.OpenDatabase($DatabasePath, $true, $true)
$schema = [ordered]@{
    database = $DatabasePath
    tables = @()
    queries = @()
}

try {
    foreach ($table in $db.TableDefs) {
        if ($table.Name -like "MSys*") { continue }
        if (($table.Attributes -band 1) -ne 0) { continue }

        $fields = @()
        foreach ($field in $table.Fields) {
            $fields += [ordered]@{
                name = $field.Name
                type = $field.Type
                size = $field.Size
                required = $field.Required
            }
        }
        $schema.tables += [ordered]@{ name = $table.Name; fields = $fields }

        $csvPath = Join-Path $OutputDir ((Safe-Name $table.Name) + ".csv")
        $rs = $db.OpenRecordset("[" + ($table.Name -replace ']', ']]') + "]")
        try {
            $header = @()
            for ($i = 0; $i -lt $rs.Fields.Count; $i++) { $header += Csv-Cell $rs.Fields.Item($i).Name }
            Set-Content -Path $csvPath -Encoding UTF8 -Value ($header -join ',')
            while (-not $rs.EOF) {
                $row = @()
                for ($i = 0; $i -lt $rs.Fields.Count; $i++) { $row += Csv-Cell $rs.Fields.Item($i).Value }
                Add-Content -Path $csvPath -Encoding UTF8 -Value ($row -join ',')
                $rs.MoveNext()
            }
        }
        finally { $rs.Close() }
    }

    foreach ($query in $db.QueryDefs) {
        if ($query.Name -like "~*") { continue }
        $schema.queries += [ordered]@{ name = $query.Name; sql = $query.SQL }
    }

    $schema | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $OutputDir "schema.json") -Encoding UTF8
    Write-Host "Export complete: $OutputDir"
}
finally {
    $db.Close()
}
