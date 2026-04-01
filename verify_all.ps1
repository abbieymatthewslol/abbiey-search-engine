Write-Host "`n=== LOADING ENV ==="
Get-Content .env | ForEach-Object {
    if ($_ -match "^(.*?)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

# ---------- DB CHECK ----------
Write-Host "`n=== DB CHECK ==="
python -c "import psycopg2, os; 
conn=psycopg2.connect(os.getenv('SUPABASE_DB_URL')); 
cur=conn.cursor(); 
cur.execute('SELECT 1'); 
print('DB OK'); 
conn.close()" 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ DB FAILED"
} else {
    Write-Host "✅ DB PASSED"
}

# ---------- API CHECK ----------
Write-Host "`n=== API CHECK ==="
try {
    $api = Invoke-RestMethod https://abbieysearch.com/api/health -TimeoutSec 5
    Write-Host "✅ API PASSED"
} catch {
    Write-Host "❌ API FAILED"
}

# ---------- SITE CHECK ----------
Write-Host "`n=== SITE CHECK ==="
try {
    $site = Invoke-WebRequest https://abbieysearch.com -TimeoutSec 5
    if ($site.StatusCode -eq 200) {
        Write-Host "✅ SITE PASSED"
    } else {
        Write-Host "❌ SITE FAILED"
    }
} catch {
    Write-Host "❌ SITE FAILED"
}

# ---------- SSL CHECK ----------
Write-Host "`n=== SSL CHECK ==="
$ssl = Test-NetConnection abbieysearch.com -Port 443
if ($ssl.TcpTestSucceeded) {
    Write-Host "✅ SSL PASSED"
} else {
    Write-Host "❌ SSL FAILED"
}

# ---------- FINAL ----------
Write-Host "`n=== DONE ==="
