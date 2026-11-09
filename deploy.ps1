# Sideloads out\TranquilReef.zip onto a Roku in developer mode (for development;
# users run the installer instead).
#
#   $env:ROKU_DEV_PASSWORD = "the developer password of the Roku"     (once per terminal)
#   .\deploy.ps1 -Ip 192.168.1.50
#
# The password is read from the environment so that it is in no file here.
param([Parameter(Mandatory = $true)][string]$Ip, [string]$Zip = "$PSScriptRoot\out\TranquilReef.zip")

if (-not $env:ROKU_DEV_PASSWORD) {
    Write-Host 'Set the password first:   $env:ROKU_DEV_PASSWORD = "..."'
    exit 1
}
if (-not (Test-Path $Zip)) {
    Write-Host "There is no $Zip - run build.py first."
    exit 1
}
$answer = & curl.exe --silent --show-error --digest --user "rokudev:$($env:ROKU_DEV_PASSWORD)" `
    -F "mysubmit=Install" -F "archive=@$Zip" "http://$Ip/plugin_install"
if ($LASTEXITCODE -ne 0) { Write-Host "Could not reach the Roku at $Ip."; exit 1 }
if ($answer -match "401|Unauthorized") { Write-Host "The Roku refused the password."; exit 1 }
$said = [regex]::Matches($answer, "(Install Success|Identical to previous version[^<']*|Install Failure[^<']*|Application Received[^<']*|Compilation Failed[^<']*)") |
        ForEach-Object { $_.Value } | Select-Object -Unique
if ($said) { $said | ForEach-Object { Write-Host "Roku: $_" } } else { Write-Host "Sent; the Roku gave no clear answer. Look at the television." }
