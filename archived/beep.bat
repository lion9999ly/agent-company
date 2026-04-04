@echo off
:: 使用 Windows 内置扬声器蜂鸣
powershell -c "[console]::Beep(800, 200); [console]::Beep(1000, 300)"
