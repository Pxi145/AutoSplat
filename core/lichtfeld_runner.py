"""
core/lichtfeld_runner.py
Runner pour l'entraînement Gaussian Splatting via Lichtfeld Studio.

Particularités :
  - Lichtfeld émet des codes ANSI (couleurs, curseur) → nettoyage obligatoire
  - Pattern de progression unique : "Training [XXX%] X/N | Loss: X | Splats: X | [XXm:XXs]"
  - CREATE_NO_WINDOW pour ne pas faire apparaître de fenêtre console
  - Récupération du temps final et du nombre de splats pour le résumé
"""
import re
import subprocess

from core.callbacks import PipelineCallbacks


# Regex de nettoyage des séquences ANSI (couleurs, positions curseur, etc.)
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _render_bar(percent: int) -> str:
    filled = "█" * (percent // 5)
    empty  = "-" * (20 - len(filled))
    return f"[{filled}{empty}]"


def run_lichtfeld_training(
    lichtfeld_exe:    str,
    output_gs:        str,
    output_model_dir: str,
    iterations:       int,
    strategy:         str,   # ex: "mrnf (Standard)" ou "mcmc (Haute Qualité)"
    resize:           str,   # ex: "auto" ou "2 (Moitié)"
    use_mip:          bool,
    max_splats:       int,   # 0 = illimité
    tile_mode:        int = 1,   # 1, 2 ou 4
    use_gut:          bool = False,
    output_name:      str | None = None,
    cb:               PipelineCallbacks = None,
) -> int:
    """
    Lance l'entraînement Gaussian Splatting en mode headless.

    Les paramètres strategy et resize sont automatiquement nettoyés
    (on extrait uniquement le premier mot avant l'espace).

    Args:
        lichtfeld_exe:    Chemin absolu vers l'exécutable Lichtfeld.
        output_gs:        Dossier contenant les images undistortées (entrée).
        output_model_dir: Dossier de sortie du modèle .ply.
        iterations:       Nombre d'itérations d'entraînement.
        strategy:         Stratégie ("mrnf (Standard)" → "mrnf").
        resize:           Facteur de résolution ("2 (Moitié)" → "2").
        use_mip:          Active l'anti-aliasing MIP si True.
        max_splats:       Nombre max de Gaussiennes (0 = illimité).
        tile_mode:        Mode tuiles VRAM (1 = défaut, 2 = moyen, 4 = économe).
        use_gut:          Active le mode GUT (images distordues).
        output_name:      Nom personnalisé du fichier PLY de sortie (optionnel).
        cb:               Callbacks UI.

    Returns:
        Code de retour du processus (0 = succès).

    Raises:
        InterruptedError: Si l'utilisateur annule.
        RuntimeError:     Si le code de retour est non-nul.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    # Nettoyage des valeurs brutes (ex : "mrnf (Standard)" → "mrnf")
    strategy_raw = strategy.split(" ")[0]
    resize_raw   = resize.split(" ")[0]

    command = [
        lichtfeld_exe,
        "--data-path",     output_gs,
        "--output-path",   output_model_dir,
        "--iter",          str(iterations),
        "--headless",
        "--train",
        "--strategy",      strategy_raw,
        "--resize_factor", resize_raw,
    ]
    if use_mip:
        command.append("--enable-mip")
    if max_splats > 0:
        command.extend(["--max-cap", str(max_splats)])
    if tile_mode > 1:
        command.extend(["--tile-mode", str(tile_mode)])
    if use_gut:
        command.append("--gut")
    if output_name:
        command.extend(["--output-name", output_name])

    gut_label  = ", GUT: True" if use_gut else ""
    max_label  = f", max-cap: {max_splats}" if max_splats > 0 else ""
    tile_label = f", tiles: {tile_mode}" if tile_mode > 1 else ""
    name_label = f", nom: {output_name}" if output_name else ""
    cb.log(
        f"Lancement de Lichtfeld "
        f"({iterations} iters, stratégie: {strategy_raw}, "
        f"resize: {resize_raw}, MIP: {use_mip}{max_label}{tile_label}{gut_label}{name_label})..."
    )

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    cb.set_current_process(proc)
    cb.log("⏳ [--------------------] 0% | 0/? | Loss: ? | Splats: ? | [00m:00s]")

    # Variables de suivi parsées depuis stdout
    total_iters  = "?"
    loss         = "?"
    splats       = "?"
    time_str     = "00m:00s"
    final_time   = "?"
    final_splats = "?"

    for line in proc.stdout:
        # Étape 1 : nettoyage des codes ANSI avant tout parsing
        clean_line = _ANSI_ESCAPE.sub('', line.strip())
        if cb.log_to_file:
            cb.log_to_file(f"[lichtfeld] {clean_line}")

        # --- Ligne de progression principale ---
        # Format attendu : "Training [XXX%] X/N | Loss: 0.0123 | Splats: 45678 | [12m:34s]"
        if "Training [" in clean_line:

            # Pourcentage
            m_pct = re.search(r'\]\s*(\d+)%', clean_line)
            percent = int(m_pct.group(1)) if m_pct else 0

            # Temps écoulé (format : "12m:34s")
            m_time = re.search(r'(\d+m:\d+s)', clean_line)
            if m_time:
                time_str = m_time.group(1)

            # Itérations courante/totale
            m_iters = re.search(r'\]\s*(?:.*?)\s*(\d+)/(\d+)', clean_line)
            if m_iters:
                current     = m_iters.group(1)
                total_iters = m_iters.group(2)
            else:
                current = "?"

            # Loss
            m_loss = re.search(r'Loss:\s*([\d\.]+)', clean_line)
            if m_loss:
                loss = m_loss.group(1)

            # Nombre de Splats actuels
            m_splats = re.search(r'Splats:\s*(\d+)', clean_line)
            if m_splats:
                splats = m_splats.group(1)

            bar = _render_bar(percent)
            cb.log(
                f"⏳ {bar} {percent}% | {current}/{total_iters} | "
                f"Loss: {loss} | Splats: {splats} | [{time_str}]",
                replace=True,
            )

        # --- Résumé final : temps d'entraînement ---
        elif "Training completed in" in clean_line:
            m = re.search(r'completed in ([\d\.]+s)', clean_line)
            if m:
                final_time = m.group(1)

        # --- Résumé final : nombre de splats ---
        elif "Final splats:" in clean_line:
            m = re.search(r'Final splats:\s*(\d+)', clean_line)
            if m:
                final_splats = m.group(1)

        # --- Erreurs ---
        elif "[error]" in clean_line or "[critical]" in clean_line:
            cb.log(f"\n⚠️ Erreur Lichtfeld : {clean_line}")
            # Conseil spécifique pour l'erreur de distorsion
            if "Distorted images detected" in clean_line and not use_gut:
                cb.log(
                    "💡 Conseil : Activez l'option 'GUT (3DGUT)' dans les paramètres "
                    "Lichtfeld pour entraîner avec des images distordues."
                )
            cb.log("⏳ [Reprise...]")

    proc.wait()
    ret = proc.returncode
    cb.set_current_process(None)

    if ret != 0:
        raise RuntimeError(
            f"L'entraînement Lichtfeld a échoué (Code d'erreur : {ret})."
        )

    cb.log(
        f"✅ [████████████████████] 100% | "
        f"Entraînement terminé ! (Durée: {final_time}, Splats finaux: {final_splats})",
        replace=True,
    )
    return ret
