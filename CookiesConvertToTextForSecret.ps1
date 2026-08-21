# Windows PowerShell
$folder = "C:\"

[Convert]::ToBase64String(
    [IO.File]::ReadAllBytes("$folder\yahoo_cookies.json")
) | Set-Content -NoNewline -Encoding ascii "$folder\yahoo_cookies_b64.txt"
