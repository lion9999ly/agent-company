@echo off
powershell -c "[System.Media.SystemSounds]::Exclamation.Play(); Start-Sleep -Milliseconds 500; [System.Media.SystemSounds]::Exclamation.Play()"