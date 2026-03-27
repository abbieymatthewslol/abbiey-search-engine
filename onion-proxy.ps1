# Onion Proxy Server — routes .onion requests through Tor SOCKS5
# Requires: Tor running on port 9050 (Tor Browser or standalone tor.exe)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File onion-proxy.ps1
#
# This is OPTIONAL — abbiey.search has a built-in /api/onion-proxy endpoint
# that does the same thing. This standalone script is for advanced users
# who want a dedicated proxy outside of Flask.

$TorSocks = "socks5://127.0.0.1:9050"
$Port = 8080

Add-Type -AssemblyName System.Web

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")

try {
    $listener.Start()
} catch {
    Write-Host "ERROR: Port $Port already in use. Is another proxy running?" -ForegroundColor Red
    exit 1
}

Write-Host "Onion Proxy running on http://localhost:$Port/" -ForegroundColor Green
Write-Host "Tor SOCKS: $TorSocks" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

while ($true) {
    $context = $listener.GetContext()
    $request = $context.Request
    $response = $context.Response

    $path = $request.Url.LocalPath
    $query = $request.QueryString

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $($request.HttpMethod) $path" -ForegroundColor Gray

    if ($path -eq "/proxy") {
        $targetUrl = [System.Web.HttpUtility]::UrlDecode($query["url"])

        if (-not $targetUrl) {
            $buffer = [System.Text.Encoding]::UTF8.GetBytes("No URL specified")
            $response.ContentType = "text/plain"
            $response.StatusCode = 400
        }
        elseif ($targetUrl -notmatch '\.onion') {
            $buffer = [System.Text.Encoding]::UTF8.GetBytes("Only .onion URLs allowed")
            $response.ContentType = "text/plain"
            $response.StatusCode = 400
        }
        else {
            Write-Host "  -> Proxying: $targetUrl" -ForegroundColor Magenta
            try {
                $webRequest = [System.Net.WebRequest]::Create($targetUrl)
                $webRequest.Proxy = New-Object System.Net.WebProxy($TorSocks)
                $webRequest.Method = "GET"
                $webRequest.Timeout = 30000
                $webRequest.UserAgent = "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"

                $webResponse = $webRequest.GetResponse()
                $stream = $webResponse.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $content = $reader.ReadToEnd()
                $reader.Close()
                $stream.Close()
                $webResponse.Close()

                # Rewrite internal .onion links to route through proxy
                $content = $content -replace 'href="(https?://[^"]*\.onion[^"]*)"', 'href="/proxy?url=$1"'
                $content = $content -replace 'src="(https?://[^"]*\.onion[^"]*)"', 'src="/proxy?url=$1"'

                $buffer = [System.Text.Encoding]::UTF8.GetBytes($content)
                $response.ContentType = "text/html; charset=utf-8"
                Write-Host "  <- OK (${$buffer.Length} bytes)" -ForegroundColor Green
            }
            catch {
                $errMsg = $_.Exception.Message
                Write-Host "  <- ERROR: $errMsg" -ForegroundColor Red
                $errorHtml = @"
<!DOCTYPE html>
<html><head><title>Proxy Error</title></head>
<body style="background:#0a0a0a;color:#e4e4e7;font-family:system-ui;padding:2rem">
<h2 style="color:#f87171">Cannot reach .onion site</h2>
<p><strong>URL:</strong> <code>$targetUrl</code></p>
<p><strong>Error:</strong> $errMsg</p>
<p style="color:#a1a1aa">Make sure Tor is running on port 9050.</p>
</body></html>
"@
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorHtml)
                $response.ContentType = "text/html; charset=utf-8"
                $response.StatusCode = 502
            }
        }
    }
    else {
        $html = @"
<!DOCTYPE html>
<html><head><title>Onion Proxy</title></head>
<body style="background:#0a0a0a;color:#6ee7b7;font-family:system-ui;padding:2rem">
<h2>Onion Link Proxy</h2>
<p style="color:#a1a1aa">Routes .onion requests through Tor SOCKS5.</p>
<p>Status: <span style="color:#4ade80">Running</span></p>
<p style="color:#a1a1aa">Usage: <code>/proxy?url=http://example.onion/</code></p>
</body></html>
"@
        $buffer = [System.Text.Encoding]::UTF8.GetBytes($html)
        $response.ContentType = "text/html; charset=utf-8"
    }

    # CORS headers for abbiey.search
    $response.Headers.Add("Access-Control-Allow-Origin", "http://localhost:8000")

    $response.ContentLength64 = $buffer.Length
    $response.OutputStream.Write($buffer, 0, $buffer.Length)
    $response.Close()
}
