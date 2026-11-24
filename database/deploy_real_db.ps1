param([Parameter(Mandatory = $true)][int]$Port)

$ErrorActionPreference = "Stop"
$mysql = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
$reportPath = Join-Path $PSScriptRoot "deployment_report.txt"
$tempDir = Join-Path $env:TEMP ("banking_deploy_" + [guid]::NewGuid().ToString("N"))
$report = New-Object System.Collections.Generic.List[string]
$changed = $false
$ok = $false

$expectedTables = "account,accounttype,customer,merchant,transactiontype"
$expectedStructure = @(
    "check`t1`t3965989311", "column`t25`t273880238", "foreign_key`t2`t553555561",
    "index`t11`t4106244010", "table`t5`t3066246241"
) -join "|"

$structureQuery = @'
SELECT section, COUNT(*) AS items, BIT_XOR(CRC32(CONCAT(name, '=', detail))) AS fingerprint
FROM (
  SELECT 'table' AS section, CONVERT(TABLE_NAME USING utf8mb4) AS name,
         CONVERT(CONCAT_WS('|', ENGINE, TABLE_COLLATION) USING utf8mb4) AS detail
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = 'banking_fraud_detection'
    AND TABLE_NAME IN ('customer','accounttype','account','transactiontype','merchant')
  UNION ALL
  SELECT 'column', CONVERT(CONCAT(TABLE_NAME, '.', COLUMN_NAME) USING utf8mb4),
         CONVERT(CONCAT_WS('|', ORDINAL_POSITION, COLUMN_TYPE, IS_NULLABLE, IFNULL(COLUMN_DEFAULT, '<none>'), COLUMN_KEY, EXTRA) USING utf8mb4)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = 'banking_fraud_detection'
    AND TABLE_NAME IN ('customer','accounttype','account','transactiontype','merchant')
  UNION ALL
  SELECT 'index', CONVERT(CONCAT(TABLE_NAME, '.', INDEX_NAME) USING utf8mb4),
         CONVERT(CONCAT(NON_UNIQUE, '|', GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)) USING utf8mb4)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = 'banking_fraud_detection'
    AND TABLE_NAME IN ('customer','accounttype','account','transactiontype','merchant')
  GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE
  UNION ALL
  SELECT 'foreign_key', CONVERT(CONCAT(rc.TABLE_NAME, '.', rc.CONSTRAINT_NAME) USING utf8mb4),
         CONVERT(CONCAT_WS('|', k.COLUMN_NAME, k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME, rc.UPDATE_RULE, rc.DELETE_RULE) USING utf8mb4)
  FROM information_schema.REFERENTIAL_CONSTRAINTS rc
  JOIN information_schema.KEY_COLUMN_USAGE k
    ON k.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA AND k.CONSTRAINT_NAME = rc.CONSTRAINT_NAME AND k.TABLE_NAME = rc.TABLE_NAME
  WHERE rc.CONSTRAINT_SCHEMA = 'banking_fraud_detection'
    AND rc.TABLE_NAME IN ('customer','accounttype','account','transactiontype','merchant')
  UNION ALL
  SELECT 'check', CONVERT(CONCAT(t.TABLE_NAME, '.', t.CONSTRAINT_NAME) USING utf8mb4),
         CONVERT(c.CHECK_CLAUSE USING utf8mb4)
  FROM information_schema.TABLE_CONSTRAINTS t
  JOIN information_schema.CHECK_CONSTRAINTS c
    ON c.CONSTRAINT_SCHEMA = t.CONSTRAINT_SCHEMA AND c.CONSTRAINT_NAME = t.CONSTRAINT_NAME
  WHERE t.CONSTRAINT_SCHEMA = 'banking_fraud_detection' AND t.CONSTRAINT_TYPE = 'CHECK'
    AND t.TABLE_NAME IN ('customer','accounttype','account','transactiontype','merchant')
) s
GROUP BY section
ORDER BY section;
'@

function Write-Log([string]$Message) {
    Write-Host $Message
    $report.Add($Message)
}

function Invoke-SqlFile([string]$Path, [switch]$NoHeaders) {
    $out = Join-Path $tempDir "out.txt"
    $err = Join-Path $tempDir "err.txt"
    $cli = @("--no-defaults", "--host=127.0.0.1", "--port=$Port", "--user=root",
             "--default-character-set=utf8mb4", "--batch")
    if ($NoHeaders) { $cli += "--skip-column-names" }
    $p = Start-Process -FilePath $mysql -ArgumentList $cli -RedirectStandardInput $Path `
        -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
    [pscustomobject]@{ Code = $p.ExitCode; Out = @(Get-Content $out); Err = @(Get-Content $err) }
}

function Invoke-Query([string]$Sql) {
    $file = Join-Path $tempDir "query.sql"
    [IO.File]::WriteAllText($file, $Sql)
    $r = Invoke-SqlFile $file -NoHeaders
    if ($r.Code -ne 0) { throw ("Query failed: " + ($r.Err -join " ")) }
    return $r.Out
}

function Invoke-Step([string]$File) {
    $r = Invoke-SqlFile (Join-Path $PSScriptRoot $File)
    if ($r.Code -ne 0) { throw ("$File failed: " + (($r.Err | Select-Object -Last 2) -join " ")) }
    return $r
}

function Get-LegacySnapshot {
    $names = @(Invoke-Query "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='banking_fraud_db' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME;")
    if ($names.Count -eq 0) { return "no tables" }
    $sql = ($names | ForEach-Object { 'CHECKSUM TABLE `banking_fraud_db`.`' + $_ + '`;' }) -join "`n"
    return (@(Invoke-Query $sql) -join "|")
}

try {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    Write-Log "Banking Fraud DB recovery - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - port $Port"

    if (-not $env:MYSQL_PWD) {
        $secure = Read-Host "Enter your MySQL root password" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $env:MYSQL_PWD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }

    Write-Log "--- Safety checks (read-only) ---"
    $version = @(Invoke-Query "SELECT VERSION();")[0]
    if ([version]($version -replace '[^0-9.].*$', '') -lt [version]"8.0.29") { throw "MySQL $version is older than 8.0.29" }
    Write-Log "PASS  MySQL version $version"

    $tables = (@(Invoke-Query "SELECT LOWER(TABLE_NAME) FROM information_schema.TABLES WHERE TABLE_SCHEMA='banking_fraud_detection' ORDER BY 1;") -join ",")
    if ($tables -ne $expectedTables) { throw "Unexpected tables: $tables" }
    Write-Log "PASS  Exactly the 5 expected tables exist"

    $rows = @(Invoke-Query "SELECT (SELECT COUNT(*) FROM banking_fraud_detection.customer)+(SELECT COUNT(*) FROM banking_fraud_detection.accounttype)+(SELECT COUNT(*) FROM banking_fraud_detection.account)+(SELECT COUNT(*) FROM banking_fraud_detection.transactiontype)+(SELECT COUNT(*) FROM banking_fraud_detection.merchant);")[0]
    if ($rows -ne "0") { throw "Existing tables are not empty ($rows rows)" }
    Write-Log "PASS  All 5 tables are empty"

    $routines = @(Invoke-Query "SELECT (SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='banking_fraud_detection')+(SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='banking_fraud_detection');")[0]
    if ($routines -ne "0") { throw "Found $routines existing procedure(s)/trigger(s)" }
    Write-Log "PASS  No old procedures or triggers"

    $structure = (@(Invoke-Query $structureQuery) -join "|")
    if ($structure -ne $expectedStructure) { throw "Table structure differs from schema.sql: $structure" }
    Write-Log "PASS  Columns, keys, indexes and constraints match schema.sql"

    $legacyBefore = Get-LegacySnapshot

    Write-Log "--- Phase 1 ---"
    $changed = $true
    Invoke-Step "schema.sql" | Out-Null
    Write-Log "PASS  schema.sql"
    Invoke-Step "master_data.sql" | Out-Null
    Write-Log "PASS  master_data.sql"
    $upgrade = Invoke-Step "upgrade_existing_schema.sql"
    if (-not ($upgrade.Out -match "Schema already current: nothing changed")) { throw "upgrade_existing_schema.sql reported changes" }
    Write-Log "PASS  upgrade_existing_schema.sql (nothing to change)"
    $verify = Invoke-Step "verification.sql"
    $i = [array]::IndexOf($verify.Out, "total_tests`tpassed`tfailed")
    if ($i -lt 0 -or $verify.Out[$i + 1] -ne "92`t92`t0") { throw "verification.sql did not pass 92/92" }
    if (-not ($verify.Out -match "PASS: nothing persisted")) { throw "verification.sql rollback check failed" }
    Write-Log "PASS  verification.sql 92/92, nothing persisted"

    Write-Log "--- Phase 2 ---"
    Invoke-Step "seed_data.sql" | Out-Null
    Write-Log "PASS  seed_data.sql"
    $validate = Invoke-Step "validate_seed_data.sql"
    $passed = @($validate.Out | Where-Object { $_ -match "`tPASS$" }).Count
    $failed = @($validate.Out | Where-Object { $_ -match "`tFAIL$" }).Count
    if ($passed -ne 55 -or $failed -ne 0) { throw "validate_seed_data.sql: $passed passed, $failed failed" }
    Write-Log "PASS  validate_seed_data.sql 55/55"

    $counts = @(Invoke-Query "SELECT CONCAT_WS(',',(SELECT COUNT(*) FROM banking_fraud_detection.customer),(SELECT COUNT(*) FROM banking_fraud_detection.account),(SELECT COUNT(*) FROM banking_fraud_detection.merchant),(SELECT COUNT(*) FROM banking_fraud_detection.``transaction``),(SELECT COUNT(*) FROM banking_fraud_detection.fraud_alert),(SELECT COUNT(*) FROM banking_fraud_detection.investigation));")[0]
    if ($counts -ne "500,800,60,20000,0,0") { throw "Unexpected row counts: $counts" }
    Write-Log "PASS  Row counts $counts"

    if ((Get-LegacySnapshot) -ne $legacyBefore) { throw "banking_fraud_db checksum changed" }
    Write-Log "PASS  banking_fraud_db unchanged"
    $ok = $true
}
catch {
    Write-Log "STOPPED: $($_.Exception.Message)"
    if (-not $changed) { Write-Log "No changes were made to any database." }
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Log $(if ($ok) { "RESULT: SUCCESS" } else { "RESULT: NOT COMPLETED" })
    [IO.File]::WriteAllLines($reportPath, $report)
    Write-Host "Report saved to $reportPath"
}
if (-not $ok) { exit 1 }
