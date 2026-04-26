Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' --- Chemin absolu du dossier courant ---
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' --- Lancement de l'application via le venv ---
WshShell.CurrentDirectory = scriptDir
WshShell.Run Chr(34) & scriptDir & "\venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & scriptDir & "\main.pyw" & Chr(34), 0, False