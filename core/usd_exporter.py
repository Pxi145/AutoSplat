"""
core/usd_exporter.py
Export de fichiers Gaussian Splatting via la commande LichtFeld Studio convert.

Particularité :
  - Utilise le sous-commande `convert` de LichtFeld Studio v0.5.1+
  - Formats supportés : usd, usda, usdc, spz, html
  - CREATE_NO_WINDOW pour ne pas faire apparaître de console
"""
import os
import re
import subprocess

from core.callbacks import PipelineCallbacks


def _render_bar(percent: int) -> str:
    filled = "█" * (percent // 5)
    empty  = "-" * (20 - len(filled))
    return f"[{filled}{empty}]"


def run_usd_export(
    lichtfeld_exe: str,
    ply_path:      str,
    output_dir:    str,
    export_format: str = "usd",
    cb:            PipelineCallbacks = None,
) -> str:
    """
    Convertit un fichier .ply en USD (ou autre format) via LichtFeld Studio convert.

    Args:
        lichtfeld_exe: Chemin vers LichtFeld-Studio.exe.
        ply_path:      Chemin vers le fichier .ply source.
        output_dir:    Dossier de destination.
        export_format: Format de sortie (usd, usda, usdc, spz, html).
        cb:            Callbacks UI.

    Returns:
        Chemin du fichier exporté.

    Raises:
        InterruptedError: Si l'utilisateur annule.
        RuntimeError:     Si la conversion échoue.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    # Construire le chemin de sortie
    ply_stem = os.path.splitext(os.path.basename(ply_path))[0]
    output_file = os.path.join(output_dir, f"{ply_stem}.{export_format}")

    command = [
        lichtfeld_exe, "convert",
        ply_path,
        output_file,
        "-y",   # écraser sans confirmation
    ]

    fmt_upper = export_format.upper()
    cb.log(f"Conversion PLY → {fmt_upper} via LichtFeld convert...")
    cb.log(f"⏳ [--------------------] 0% | Initialisation de l'export {fmt_upper}...")

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    cb.set_current_process(proc)

    percent = 0

    for line in proc.stdout:
        clean = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[convert] {clean}")

        # Détecter la progression par les messages de LichtFeld convert
        if "Loading" in clean or "Reading" in clean:
            percent = 30
            cb.log(f"⏳ {_render_bar(percent)} {percent}% | Lecture du fichier PLY...", replace=True)
        elif "Converting" in clean or "Processing" in clean:
            percent = 60
            cb.log(f"⏳ {_render_bar(percent)} {percent}% | Conversion en cours...", replace=True)
        elif "Writing" in clean or "Saving" in clean:
            percent = 85
            cb.log(f"⏳ {_render_bar(percent)} {percent}% | Écriture du fichier {fmt_upper}...", replace=True)
        elif "Done" in clean or "Success" in clean or "Complete" in clean:
            percent = 100
            cb.log(f"⏳ {_render_bar(percent)} {percent}% | Finalisation...", replace=True)
        elif "error" in clean.lower() or "fail" in clean.lower():
            cb.log(f"\n⚠️ Erreur Convert : {clean}")

    proc.wait()
    ret = proc.returncode
    cb.set_current_process(None)

    if ret != 0:
        raise RuntimeError(f"L'export {fmt_upper} a échoué (Code de retour : {ret}).")

    # Vérifier que le fichier a bien été créé
    if not os.path.exists(output_file):
        raise RuntimeError(
            f"LichtFeld convert s'est terminé mais le fichier {output_file} n'a pas été créé."
        )

    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    cb.log(
        f"✅ [████████████████████] 100% | "
        f"Export {fmt_upper} terminé ! ({file_size_mb:.1f} Mo)",
        replace=True,
    )
    return output_file
