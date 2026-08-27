' NeuroGraphIQ KG V3 - silent launcher for the desktop shortcut.
' Runs the PowerShell script in a fully hidden window (style 0) and returns
' immediately; start-workbench.ps1 spawns backend/frontend hidden + opens browser.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\scripts\start-workbench.ps1""", 0, False
