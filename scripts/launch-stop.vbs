' NeuroGraphIQ KG V3 - silent stop for the desktop shortcut (hidden, then a
' confirmation popup so the user knows it finished).
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\scripts\stop-workbench.ps1""", 0, True
MsgBox "NeuroGraphIQ services stopped.", vbInformation, "NeuroGraphIQ"
