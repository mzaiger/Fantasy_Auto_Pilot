# Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("yahoo_cookies.json")) | Set-Content -NoNewline -Encoding ascii yahoo_cookies_b64.txt