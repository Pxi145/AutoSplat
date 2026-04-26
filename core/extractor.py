"""
core/extractor.py
Extraction d'images depuis une vidéo et filtrage anti-flou via OpenCV.

Responsabilités :
  - Extraire les meilleures images d'une vidéo par paquets (packet picking)
  - Filtrer un dossier d'images statiques par variance du Laplacien
  - Générer des miniatures pour l'aperçu temps réel
  - Aucun import CustomTkinter direct — communication via PipelineCallbacks

Algorithme de sélection (packet picking) :
    On divise la vidéo en paquets de N frames (N = fps_natif / fps_cible).
    Pour chaque paquet, on garde uniquement la frame avec la variance la plus
    haute (= la plus nette). Si sa variance est >= seuil, on la sauvegarde.
"""
import os
import shutil

import cv2
from PIL import Image

from core.callbacks import PipelineCallbacks


# ---------------------------------------------------------------------------
# Helper partagé : rendu ASCII de la barre de progression
# ---------------------------------------------------------------------------

def _render_bar(current: int, total: int) -> tuple[str, int]:
    """
    Retourne (barre_ascii, pourcentage) pour un avancement current/total.
    Exemple : _render_bar(3, 10) → ("[██████--------------]", 30)
    """
    percent = int((current / total) * 100) if total > 0 else 0
    filled  = "█" * (percent // 5)
    empty   = "-" * (20 - len(filled))
    return f"[{filled}{empty}]", percent


# ---------------------------------------------------------------------------
# Helper privé : création de miniature CTkImage pour le moniteur
# ---------------------------------------------------------------------------

def _make_ctk_thumbnail(frame_bgr, max_dim: int = 240):
    """
    Convertit une frame OpenCV (BGR) en CTkImage redimensionnée.
    Conserve le ratio en mode paysage ET portrait (vidéos iPhone, etc.).
    Retourne None si CTkImage n'est pas disponible ou en cas d'erreur.
    """
    try:
        import customtkinter as ctk  # Import local : core ne dépend pas de ctk
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        orig_w, orig_h = pil_img.size

        if orig_w >= orig_h:  # Paysage
            new_w = max_dim
            new_h = int(max_dim * orig_h / orig_w)
        else:                  # Portrait (iPhone, TikTok…)
            new_h = max_dim
            new_w = int(max_dim * orig_w / orig_h)

        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extraction depuis une vidéo
# ---------------------------------------------------------------------------

def extract_from_video(
    source_path:     str,
    img_dir:         str,
    target_fps:      float,
    native_fps:      float,
    blur_threshold:  float,
    cb:              PipelineCallbacks,
) -> int:
    """
    Extrait les meilleures images d'une vidéo en appliquant le packet picking.

    Args:
        source_path:    Chemin vers la vidéo source (.mp4, .mov, .avi).
        img_dir:        Dossier de destination des images extraites.
        target_fps:     FPS d'extraction souhaité (choisi par l'utilisateur).
        native_fps:     FPS natif de la vidéo (détecté par OpenCV).
        blur_threshold: Variance minimale du Laplacien pour garder une image.
        cb:             Callbacks UI (log, progression, aperçu, annulation).

    Returns:
        Nombre d'images sauvegardées dans img_dir.

    Raises:
        InterruptedError: Si l'utilisateur annule pendant l'extraction.
    """
    frames_per_packet = max(1, int(native_fps / target_fps))
    video             = cv2.VideoCapture(source_path)
    total_frames      = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    cb.log(f"🎬 Vidéo chargée : {total_frames} images totales à analyser.")
    if cb.log_to_file:
        cb.log_to_file(f"[extractor] Source vidéo : {source_path}")
        cb.log_to_file(f"[extractor] FPS cible: {target_fps}, FPS natif: {native_fps}, Seuil flou: {blur_threshold}")
        cb.log_to_file(f"[extractor] Frames par paquet: {frames_per_packet}, Total frames: {total_frames}")
    cb.log("⏳ [--------------------] 0% (0/0)")

    packet: list         = []
    frame_idx            = 0
    count_saved          = 0
    last_percent_logged  = -1

    while True:
        if cb.is_cancelled():
            video.release()
            raise InterruptedError("Processus annulé par l'utilisateur.")

        ret, frame = video.read()
        if not ret:
            break

        # --- Barre de progression (met à jour uniquement si % change) ---
        if total_frames > 0:
            bar, percent = _render_bar(frame_idx, total_frames)
            if percent > last_percent_logged:
                cb.log(f"⏳ {bar} {percent}% ({frame_idx}/{total_frames})", replace=True)
                last_percent_logged = percent

        # --- Aperçu temps réel (1 frame sur 3 pour les perfs) ---
        if frame_idx % 3 == 0:
            thumb = _make_ctk_thumbnail(frame)
            if thumb:
                cb.update_monitor(thumb)

        # --- Calcul de la variance (= netteté) ---
        gray     = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        packet.append((variance, frame))

        # --- Fin du paquet → sélection de la meilleure frame ---
        if len(packet) == frames_per_packet or frame_idx == total_frames - 1:
            best_variance, best_frame = max(packet, key=lambda x: x[0])
            if best_variance >= blur_threshold:
                cv2.imwrite(
                    os.path.join(img_dir, f"frame_{count_saved:04d}.jpg"),
                    best_frame,
                )
                count_saved += 1
            packet = []

        frame_idx += 1

    video.release()

    # Barre finale à 100% + signal de masquage du moniteur
    cb.log(f"✅ [████████████████████] 100% ({total_frames}/{total_frames})", replace=True)
    cb.log(f"Extraction terminée : {count_saved} images nettes conservées.")
    if cb.log_to_file:
        cb.log_to_file(f"[extractor] Extraction terminée : {count_saved} images sauvegardées sur {total_frames} analysées")
    cb.update_monitor(None)  # → l'UI masque le moniteur après l'extraction

    return count_saved


# ---------------------------------------------------------------------------
# Filtrage d'un dossier d'images existant
# ---------------------------------------------------------------------------

def filter_images_by_blur(
    source_dir:      str,
    img_dir:         str,
    blur_threshold:  float,
    cb:              PipelineCallbacks,
) -> int:
    """
    Analyse un dossier d'images et copie uniquement les images nettes
    (variance du Laplacien >= blur_threshold) dans img_dir.

    Args:
        source_dir:     Dossier source contenant les images originales.
        img_dir:        Dossier de destination pour les images sélectionnées.
        blur_threshold: Seuil de netteté (0 = tout garder, 100 = très strict).
        cb:             Callbacks UI.

    Returns:
        Nombre d'images copiées dans img_dir.

    Raises:
        InterruptedError: Si l'utilisateur annule.
    """
    valid_files = [
        f for f in os.listdir(source_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    total = len(valid_files)

    cb.log(f"📁 Dossier chargé : {total} images totales à analyser.")
    if cb.log_to_file:
        cb.log_to_file(f"[extractor] Source dossier : {source_dir}")
        cb.log_to_file(f"[extractor] Seuil flou : {blur_threshold}, Nb fichiers : {total}")
    cb.log("⏳ [--------------------] 0% (0/0)")

    count_saved         = 0
    last_percent_logged = -1

    for idx, filename in enumerate(valid_files):
        if cb.is_cancelled():
            raise InterruptedError("Processus annulé par l'utilisateur.")

        # --- Progression ---
        bar, percent = _render_bar(idx, total)
        if percent > last_percent_logged:
            cb.log(f"⏳ {bar} {percent}% ({idx}/{total})", replace=True)
            last_percent_logged = percent

        # --- Lecture image ---
        path = os.path.join(source_dir, filename)
        img  = cv2.imread(path)
        if img is None:
            continue  # Fichier corrompu ou non lisible

        # --- Aperçu temps réel (1 image sur 3) ---
        if idx % 3 == 0:
            thumb = _make_ctk_thumbnail(img)
            if thumb:
                cb.update_monitor(thumb)

        # --- Filtre netteté ---
        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        if variance >= blur_threshold:
            shutil.copy2(path, os.path.join(img_dir, filename))
            count_saved += 1

    # Barre finale + masquage moniteur
    cb.log(f"✅ [████████████████████] 100% ({total}/{total})", replace=True)
    cb.log(f"Tri terminé : {count_saved} images conservées (floues ignorées).")
    if cb.log_to_file:
        cb.log_to_file(f"[extractor] Tri terminé : {count_saved} images conservées sur {total}")
    cb.update_monitor(None)  # → l'UI masque le moniteur

    return count_saved
