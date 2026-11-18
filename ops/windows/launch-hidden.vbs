' Launch start.ps1 without a console window (from Task Scheduler) and wait for it.
' Keep this file ASCII-only: wscript reads .vbs in the ANSI code page.
Dim fso, dir, shell, rc
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
rc = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\start.ps1""", 0, True)
WScript.Quit rc
