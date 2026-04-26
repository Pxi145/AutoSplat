"""
core/colmap_runner.py
Runners pour les étapes COLMAP du pipeline de photogrammétrie.

Chaque fonction lance un sous-processus COLMAP et parse sa sortie stdout
avec un parser regex dédié à l'étape — car chaque étape émet des patterns
différents. La barre ASCII est le seul rendu partagé (_render_bar).

Étapes couvertes :
  1. feature_extractor  → parse [X/Y] + "Processed file"  (SIFT ou ALIKED)
  2. sequential_matcher → parse [X/Y] + "Processing image" + timing
  2b. exhaustive_matcher → idem (alternative au séquentiel)
  3. mapper             → parse "Registering image #", "Image sees", BA count
  3b. view_graph_calibrator → pré-traitement global mapper
  3c. global_mapper     → parse progression GLOMAP
  4. image_undistorter  → parse [X/Y] + "Undistorting" + temps final en minutes

COLMAP 4.0.2 — Nouveautés intégrées :
  - CREATE_NO_WINDOW sur tous les Popen (pas de fenêtre console)
  - Support ALIKED (--FeatureExtraction.type ALIKED)
  - Support LightGlue (--FeatureMatching.type ALIKED_LIGHTGLUE / SIFT_LIGHTGLUE)
  - global_mapper (GLOMAP) + view_graph_calibrator
  - Nouveaux modèles caméra (DIVISION, SIMPLE_DIVISION, FISHEYE)
"""
import os
import re
import subprocess

from core.callbacks import PipelineCallbacks


# ---------------------------------------------------------------------------
# Helpers privés partagés entre les runners
# ---------------------------------------------------------------------------

def _render_bar(percent: int) -> str:
    """Génère une barre ASCII de 20 caractères pour un pourcentage donné."""
    filled = "█" * (percent // 5)
    empty  = "-" * (20 - len(filled))
    return f"[{filled}{empty}]"


def _popen(command: list[str], env: dict | None) -> subprocess.Popen:
    """
    Lance un sous-processus et redirige stdout+stderr vers PIPE.
    CREATE_NO_WINDOW empêche l'apparition de fenêtres console sous Windows.
    """
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _finalize(proc: subprocess.Popen, cb: PipelineCallbacks, step_name: str) -> int:
    """
    Attend la fin du processus, reset le processus actif dans les callbacks,
    et lève RuntimeError si le code de retour est non-nul.
    """
    proc.wait()
    ret = proc.returncode
    cb.set_current_process(None)
    if ret != 0:
        raise RuntimeError(
            f"{step_name} a échoué (Code d'erreur : {ret}). "
            "Consultez la console pour plus de détails."
        )
    return ret


def resolve_matching_type(feature_type: str) -> str:
    """
    Déduit le --FeatureMatching.type correct à partir du type de features.
    ALIKED (N16ROT, N32) utilise toujours LightGlue (meilleures performances).
    SIFT utilise BruteForce par défaut (le plus rapide en GPU).
    """
    if feature_type.startswith("ALIKED"):
        return "ALIKED_LIGHTGLUE"
    return "SIFT_BRUTEFORCE"


# ---------------------------------------------------------------------------
# 1. Feature Extractor (SIFT ou ALIKED)
#    Sortie COLMAP : "[X/Y] Processing file ..."
#                   "in X.XXs" pour le timing
# ---------------------------------------------------------------------------

def run_feature_extractor(
    colmap_exe:    str,
    db_path:       str,
    img_dir:       str,
    camera_model:  str,
    feature_type:  str = "SIFT",
    single_camera: bool = True,
    env:           dict | None = None,
    cb:            PipelineCallbacks = None,
) -> int:
    """
    Extrait les features (keypoints + descripteurs) de chaque image.
    Supporte SIFT (classique) et ALIKED (réseau de neurones via ONNX/CUDA).

    Args:
        single_camera: Si True, toutes les images partagent un même modèle
                       caméra (intrinsèques identiques). Indispensable pour
                       les sources vidéo afin d'éviter des résolutions
                       aberrantes après undistortion.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "feature_extractor",
        "--database_path",              db_path,
        "--image_path",                 img_dir,
        "--ImageReader.camera_model",   camera_model,
        "--ImageReader.single_camera",  "1" if single_camera else "0",
        "--FeatureExtraction.type",     feature_type,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)

    feature_label = f"Features {feature_type}"
    cb.log(f"⏳ [--------------------] 0% (Extraction {feature_label})")

    last_percent   = -1
    last_time_str  = ""

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[feature_extractor] {line}")

        # Timing optionnel : "in 0.42s"
        m_time = re.search(r'in (\d+\.\d+s)', line)
        if m_time:
            last_time_str = f" (en {m_time.group(1)})"

        # Progression : "[X/Y]" sur une ligne de traitement
        m_prog = re.search(r'\[(\d+)/(\d+)\]', line)
        if m_prog and "Process" in line:
            current = int(m_prog.group(1))
            total   = int(m_prog.group(2))
            if total > 0:
                percent = int((current / total) * 100)
                if percent > last_percent or m_time:
                    bar = _render_bar(percent)
                    cb.log(f"⏳ {bar} {percent}% | Image {current}/{total}{last_time_str}", replace=True)
                    last_percent = percent

        elif line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Feature Extractor : {clean}")
            cb.log("⏳ [Reprise du calcul...]")

    ret = _finalize(proc, cb, "Feature Extractor")
    cb.log(f"✅ [████████████████████] 100% | Extraction {feature_label} terminée !", replace=True)
    return ret


# ---------------------------------------------------------------------------
# 2a. Sequential Matcher
#     Sortie COLMAP : "[X/Y] Processing image ..."
# ---------------------------------------------------------------------------

def run_sequential_matcher(
    colmap_exe:    str,
    db_path:       str,
    overlap:       int,
    matching_type: str = "SIFT_BRUTEFORCE",
    env:           dict | None = None,
    cb:            PipelineCallbacks = None,
) -> int:
    """
    Matching séquentiel entre images adjacentes.
    Adapté aux vidéos et séquences ordonnées.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "sequential_matcher",
        "--database_path",                 db_path,
        "--SequentialMatching.overlap",    str(overlap),
        "--FeatureMatching.type",          matching_type,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)
    cb.log("⏳ [--------------------] 0% (Matching Séquentiel)")

    last_percent  = -1
    last_time_str = ""

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[sequential_matcher] {line}")

        m_time = re.search(r'in (\d+\.\d+s)', line)
        if m_time:
            last_time_str = f" (en {m_time.group(1)})"

        m_prog = re.search(r'\[(\d+)/(\d+)\]', line)
        if m_prog and "Process" in line:
            current = int(m_prog.group(1))
            total   = int(m_prog.group(2))
            if total > 0:
                percent = int((current / total) * 100)
                if percent > last_percent or m_time:
                    bar = _render_bar(percent)
                    cb.log(f"⏳ {bar} {percent}% | Image {current}/{total}{last_time_str}", replace=True)
                    last_percent = percent

        elif line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Matcher : {clean}")
            cb.log("⏳ [Reprise du calcul...]")

    ret = _finalize(proc, cb, "Sequential Matcher")
    cb.log("✅ [████████████████████] 100% | Matching Séquentiel terminé !", replace=True)
    return ret


# ---------------------------------------------------------------------------
# 2b. Exhaustive Matcher (COLMAP 4.0 — alternative pour photos non-ordonnées)
#     Sortie identique au sequential matcher
# ---------------------------------------------------------------------------

def run_exhaustive_matcher(
    colmap_exe:    str,
    db_path:       str,
    matching_type: str = "SIFT_BRUTEFORCE",
    env:           dict | None = None,
    cb:            PipelineCallbacks = None,
) -> int:
    """
    Matching exhaustif — teste toutes les paires d'images.
    Plus lent que le séquentiel mais nécessaire pour les photos
    prises depuis des angles variés (pas une séquence vidéo).
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "exhaustive_matcher",
        "--database_path",         db_path,
        "--FeatureMatching.type",  matching_type,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)
    cb.log("⏳ [--------------------] 0% (Matching Exhaustif)")

    last_percent  = -1
    last_time_str = ""

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[exhaustive_matcher] {line}")

        m_time = re.search(r'in (\d+\.\d+s)', line)
        if m_time:
            last_time_str = f" (en {m_time.group(1)})"

        m_prog = re.search(r'\[(\d+)/(\d+)\]', line)
        if m_prog and "Process" in line:
            current = int(m_prog.group(1))
            total   = int(m_prog.group(2))
            if total > 0:
                percent = int((current / total) * 100)
                if percent > last_percent or m_time:
                    bar = _render_bar(percent)
                    cb.log(f"⏳ {bar} {percent}% | Paire {current}/{total}{last_time_str}", replace=True)
                    last_percent = percent

        elif line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Matcher : {clean}")
            cb.log("⏳ [Reprise du calcul...]")

    ret = _finalize(proc, cb, "Exhaustive Matcher")
    cb.log("✅ [████████████████████] 100% | Matching Exhaustif terminé !", replace=True)
    return ret


# ---------------------------------------------------------------------------
# 3a. Mapper Incrémental (existant, inchangé dans la logique)
# ---------------------------------------------------------------------------

def run_mapper(
    colmap_exe:   str,
    db_path:      str,
    img_dir:      str,
    sparse_path:  str,
    img_count:    int,
    env:          dict | None = None,
    cb:           PipelineCallbacks = None,
) -> int:
    """
    Reconstruction 3D incrémentale via COLMAP Mapper.
    Parser spécifique : suit l'enregistrement des images une par une
    et les itérations de Bundle Adjustment.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "mapper",
        "--database_path",  db_path,
        "--image_path",     img_dir,
        "--output_path",    sparse_path,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)

    # État interne du parser Mapper
    total_images = img_count
    current_reg  = 0
    current_id   = "?"
    sees_str     = "?/?"
    ba_count     = 0

    def _update_ui():
        percent = min(100, int((current_reg / total_images) * 100)) if total_images > 0 else 0
        bar = _render_bar(percent)
        cb.log(
            f"⏳ {bar} {percent}% | Reg. {current_reg}/{total_images} "
            f"(ID #{current_id}) | Sees: {sees_str} | BA #{ba_count}",
            replace=True,
        )

    cb.log(f"⏳ [--------------------] 0% | Reg. 0/{total_images} (ID #?) | Sees: ?/? | BA #0")

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[mapper] {line}")

        m = re.search(r'\(connected (\d+)\)', line)
        if m:
            total_images = int(m.group(1))
            _update_ui()

        elif "Global bundle adjustment" in line:
            ba_count += 1
            _update_ui()

        elif "Registering image #" in line:
            m2 = re.search(r'Registering image #(\d+) \(num_reg_frames=(\d+)\)', line)
            if m2:
                current_id  = m2.group(1)
                current_reg = int(m2.group(2))
                _update_ui()

        elif "=> Image sees" in line:
            m3 = re.search(r'=> Image sees (\d+) / (\d+) points', line)
            if m3:
                sees_str = f"{m3.group(1)}/{m3.group(2)}"
                _update_ui()

        elif line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Mapper : {clean}")
            cb.log("⏳ [Reprise du tracking...]")

    ret = _finalize(proc, cb, "Mapper")
    cb.log(
        f"✅ [████████████████████] 100% | Mapper terminé ! (BA total: {ba_count})",
        replace=True,
    )
    return ret


# ---------------------------------------------------------------------------
# 3b. View Graph Calibrator (COLMAP 4.0 — pré-requis pour Global Mapper)
#     Modifie database.db sur place. Pas de progression [X/Y].
# ---------------------------------------------------------------------------

def run_view_graph_calibrator(
    colmap_exe:  str,
    db_path:     str,
    env:         dict | None = None,
    cb:          PipelineCallbacks = None,
) -> int:
    """
    Calibre les focales à partir du graphe de vues.
    Pré-traitement obligatoire avant le Global Mapper si les focales
    ne sont pas connues/fiables (ex : pas d'EXIF).
    Modifie database.db sur place.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "view_graph_calibrator",
        "--database_path", db_path,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)
    cb.log("⏳ [----------⟳---------] Calibration du graphe de vues...")

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[view_graph_calibrator] {line}")
        if line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Calibrator : {clean}")

    ret = _finalize(proc, cb, "View Graph Calibrator")
    cb.log("✅ [████████████████████] 100% | Calibration du graphe terminée !", replace=True)
    return ret


# ---------------------------------------------------------------------------
# 3c. Global Mapper — GLOMAP (COLMAP 4.0 — reconstruction globale)
#     Plus rapide, moins sensible aux dérives sur les boucles.
#     Génère un seul modèle dans output_path/0/
# ---------------------------------------------------------------------------

def run_global_mapper(
    colmap_exe:   str,
    db_path:      str,
    img_dir:      str,
    sparse_path:  str,
    img_count:    int,
    env:          dict | None = None,
    cb:           PipelineCallbacks = None,
) -> int:
    """
    Reconstruction 3D globale via GLOMAP (Global Mapper).
    Plus rapide que le mapper incrémental pour les grands jeux de données
    et les trajectoires en boucle.
    
    Pipeline GLOMAP (basé sur les logs réels) :
      1. rotation averaging       → filtrage des paires incohérentes
      2. track establishment      → création + filtrage des tracks 3D
      3. global positioning       → Ceres solver (convergence)
      4. iterative BA             → X/Y itérations × (fixed-rotation + full)
      5. retriangulation          → affinement final
      6. écriture du modèle
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "global_mapper",
        "--database_path",  db_path,
        "--image_path",     img_dir,
        "--output_path",    sparse_path,
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)
    cb.log(f"⏳ [--------------------] 0% | GLOMAP : Chargement de {img_count} images...")

    # --- État du parser ---
    phase           = "Chargement"
    percent         = 0
    ba_current      = 0
    ba_total        = 3
    ba_sub          = ""
    pairs_total     = 0
    pairs_rejected  = 0
    info_extra      = ""

    def _update_ui():
        bar = _render_bar(percent)
        parts = [f"⏳ {bar} {percent}% | GLOMAP : {phase}"]
        if info_extra:
            parts.append(info_extra)
        if ba_current > 0:
            ba_idx = (ba_current - 1) * 2 + (1 if ba_sub == "rotation" else 2)
            parts.append(f"BA #{ba_idx}/{ba_total * 2}")
        cb.log(" | ".join(parts), replace=True)

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[global_mapper] {line}")

        m_edges = re.search(r'Loaded (\d+) edges into pose graph', line)
        if m_edges:
            pairs_total = int(m_edges.group(1))

        elif "=== Running rotation averaging ===" in line:
            phase   = "Moyennage des rotations"
            percent = 5
            info_extra = ""
            _update_ui()

        elif "Marked" in line and "image pairs as invalid" in line:
            m = re.search(r'Marked (\d+) image pairs', line)
            if m:
                pairs_rejected += int(m.group(1))
                if pairs_total > 0:
                    valid_pct = round((1 - pairs_rejected / pairs_total) * 100, 1)
                    info_extra = f"{valid_pct}% des paires valides"
                else:
                    info_extra = f"{pairs_rejected} paires filtrées"
                _update_ui()

        elif "Rotation averaging done" in line:
            percent = 10
            phase = "Rotations terminées"
            _update_ui()

        elif "=== Running track establishment ===" in line:
            phase   = "Établissement des tracks"
            percent = 12
            info_extra = ""
            _update_ui()

        elif "Established" in line and "tracks from" in line:
            m = re.search(r'Established (\d+) tracks from (\d+) observations', line)
            if m:
                info_extra = f"{int(m.group(1)):,} tracks"
                _update_ui()

        elif "Kept" in line and "tracks" in line and "discarded" in line:
            m = re.search(r'Kept (\d+) tracks, discarded (\d+)', line)
            if m:
                info_extra = f"{int(m.group(1)):,} tracks conservées"
                _update_ui()

        elif "Track establishment done" in line:
            percent = 18
            _update_ui()

        elif "=== Running global positioning ===" in line:
            phase   = "Positionnement global"
            percent = 20
            info_extra = ""
            _update_ui()

        elif "Ceres Solver Report" in line and "CONVERGENCE" in line:
            m = re.search(r'Iterations: (\d+)', line)
            iters = m.group(1) if m else "?"
            info_extra = f"Ceres convergé ({iters} iter.)"
            percent = 28
            _update_ui()

        elif "Global positioning done" in line:
            m = re.search(r'in (\d+\.?\d*) seconds', line)
            t = f" en {float(m.group(1)):.0f}s" if m else ""
            percent = 30
            phase = "Positionnement terminé"
            info_extra = t.strip()
            _update_ui()

        elif "=== Running iterative bundle adjustment ===" in line:
            phase   = "Bundle Adjustment"
            percent = 32
            info_extra = ""
            _update_ui()

        elif "bundle adjustment iteration" in line.lower() and "fixed-rotation stage finished" in line:
            m = re.search(r'iteration (\d+) / (\d+)', line)
            if m:
                ba_current = int(m.group(1))
                ba_total   = int(m.group(2))
                ba_sub     = "rotation"
                ba_range = 85 - 32
                step_pct = ba_range / (ba_total * 2)
                sub_index = (ba_current - 1) * 2
                percent = int(32 + step_pct * (sub_index + 1))
                phase = f"BA {ba_current}/{ba_total} (rotations fixées)"
                info_extra = ""
                _update_ui()

        elif "bundle adjustment iteration" in line.lower() and "finished" in line and "fixed-rotation" not in line:
            m = re.search(r'iteration (\d+) / (\d+)', line)
            if m:
                ba_current = int(m.group(1))
                ba_total   = int(m.group(2))
                ba_sub     = "complet"
                ba_range = 85 - 32
                step_pct = ba_range / (ba_total * 2)
                sub_index = (ba_current - 1) * 2 + 1
                percent = int(32 + step_pct * (sub_index + 1))
                phase = f"BA {ba_current}/{ba_total} terminée"
                info_extra = ""
                _update_ui()

        elif "Filtering tracks by reprojection" in line:
            phase = f"BA {ba_current}/{ba_total} (filtrage tracks)"
            _update_ui()

        elif "Iterative bundle adjustment done" in line:
            m = re.search(r'in (\d+\.?\d*) seconds', line)
            t = f"en {float(m.group(1)):.0f}s" if m else ""
            percent = 85
            phase = "Bundle Adjustment terminé"
            info_extra = t
            _update_ui()

        elif "=== Running iterative retriangulation" in line:
            phase   = "Re-triangulation & affinement"
            percent = 87
            info_extra = ""
            _update_ui()

        elif "Writing" in line and ("reconstruction" in line.lower() or "model" in line.lower()):
            phase   = "Écriture du modèle"
            percent = 97
            info_extra = ""
            _update_ui()

        elif line.startswith("E202"):
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur GLOMAP : {clean}")

    ret = _finalize(proc, cb, "Global Mapper (GLOMAP)")

    final_ba = ba_current * 2 if ba_sub == "complet" else max(0, ba_current * 2 - 1)
    valid_info = ""
    if pairs_total > 0 and pairs_rejected > 0:
        valid_pct = round((1 - pairs_rejected / pairs_total) * 100, 1)
        valid_info = f" | {valid_pct}% paires valides"

    cb.log(
        f"✅ [████████████████████] 100% | GLOMAP terminé | BA #{final_ba}{valid_info}",
        replace=True,
    )
    return ret


# ---------------------------------------------------------------------------
# 4. Image Undistorter
# ---------------------------------------------------------------------------

def run_undistorter(
    colmap_exe:   str,
    img_dir:      str,
    input_path:   str,
    output_gs:    str,
    env:          dict | None = None,
    cb:           PipelineCallbacks = None,
) -> int:
    """
    Undistortion des images pour préparer la phase Gaussian Splatting.
    Parser : cherche [X/Y] sur les lignes "Undistorting" + temps final en minutes.
    """
    if cb.is_cancelled():
        raise InterruptedError("Processus annulé par l'utilisateur.")

    command = [
        colmap_exe, "image_undistorter",
        "--image_path",   img_dir,
        "--input_path",   input_path,
        "--output_path",  output_gs,
        "--output_type",  "COLMAP",
    ]

    proc = _popen(command, env)
    cb.set_current_process(proc)
    cb.log("⏳ [--------------------] 0% | Undistortion 0/0")

    last_percent  = -1
    total_images  = 0
    elapsed_time  = "inconnu"

    for line in proc.stdout:
        line = line.strip()
        if cb.log_to_file:
            cb.log_to_file(f"[undistorter] {line}")

        m = re.search(r'\[(\d+)/(\d+)\]', line)
        if m and "Undistorting" in line:
            current      = int(m.group(1))
            total        = int(m.group(2))
            total_images = total
            if total > 0:
                percent = int((current / total) * 100)
                if percent > last_percent:
                    bar = _render_bar(percent)
                    cb.log(f"⏳ {bar} {percent}% | Undistortion {current}/{total}", replace=True)
                    last_percent = percent

        m_time = re.search(r'Elapsed time: (\d+\.\d+) \[minutes\]', line)
        if m_time:
            elapsed_time = m_time.group(1)

        elif line.startswith("E202") or "Error" in line:
            clean = line.split("]", 1)[-1].strip() if "]" in line else line
            cb.log(f"\n⚠️ Erreur Undistortion : {clean}")
            cb.log("⏳ [Reprise...]")

    ret = _finalize(proc, cb, "Undistorter")
    cb.log(
        f"✅ [████████████████████] 100% | "
        f"Undistortion {total_images}/{total_images} terminé ! en {elapsed_time} min",
        replace=True,
    )
    return ret
