"""
core/pipeline.py
Orchestrateur du pipeline complet de photogrammétrie / Gaussian Splatting.

Responsabilités :
  - Coordonner les étapes dans le bon ordre selon le mode d'exécution
  - Gérer les 3 modes : nouveau projet, reprise Mapper, reprise Lichtfeld
  - Brancher dynamiquement entre le Mapper incrémental et le Global Mapper
  - Déléguer chaque étape à son runner spécialisé
  - Effectuer le nettoyage automatique si configuré
  - Retourner un dict de résultats à l'UI (project_path, final_ply, etc.)

COLMAP 4.0.2 — Nouveautés :
  - Mode "global" : View Graph Calibrator → GLOMAP (Global Mapper)
  - Mode "incremental" : Mapper classique (inchangé)
  - Feature type : SIFT (défaut) ou ALIKED (IA)
  - Matcher type : séquentiel (vidéos) ou exhaustif (photos)

Ce module ne contient AUCUN widget CustomTkinter.
Toute communication avec l'UI passe par PipelineCallbacks.
"""
import os
import shutil
import time
from datetime import datetime

from config import settings as cfg
from core import (
    callbacks as cb_module,
    colmap_runner,
    extractor,
    lichtfeld_runner,
    paths,
)
from core.callbacks import PipelineCallbacks


class PipelineOrchestrator:
    """
    Chef d'orchestre du pipeline AutoSplat.

    Instance unique créée au démarrage de l'application et réutilisée
    pour chaque traitement. La configuration peut être mise à jour
    entre les runs via update_config().
    """

    def __init__(
        self,
        base_dir:     str,
        bin_dir:      str,
        projects_dir: str,
        config:       dict,
    ):
        self.base_dir     = base_dir
        self.bin_dir      = bin_dir
        self.projects_dir = projects_dir
        self.config       = config

        # Résolution des binaires au démarrage (une seule fois)
        self.colmap_exe    = paths.find_colmap_exe(bin_dir)
        self.lichtfeld_exe = paths.find_lichtfeld_exe(bin_dir)
        self.ffmpeg_exe    = os.path.join(bin_dir, "ffmpeg.exe")

    def update_config(self, new_config: dict) -> None:
        """Met à jour la configuration (appelé depuis la fenêtre Paramètres)."""
        self.config = new_config

    # -----------------------------------------------------------------------
    # Helpers de configuration COLMAP 4.0
    # -----------------------------------------------------------------------

    def _get_colmap_mode(self) -> str:
        """Retourne 'incremental' ou 'global'."""
        return str(self.config.get("colmap_mode", "incremental"))

    def _get_feature_type(self) -> str:
        """Retourne 'SIFT' ou 'ALIKED'."""
        return str(self.config.get("colmap_feature_type", "SIFT"))

    def _get_matching_type(self) -> str:
        """Retourne le --FeatureMatching.type déduit de la config."""
        return colmap_runner.resolve_matching_type(self._get_feature_type())

    def _get_matcher_mode(self) -> str:
        """Retourne 'sequential' ou 'exhaustive'."""
        return str(self.config.get("colmap_matcher_type", "sequential"))

    # -----------------------------------------------------------------------
    # Point d'entrée principal
    # -----------------------------------------------------------------------

    def run(
        self,
        source_path:   str,
        is_video:      bool,
        native_fps:    float,
        target_fps:    float,
        blur_threshold: float,
        resume_mode:   str | None,   # None | "mapper" | "lichtfeld"
        project_path:  str | None,
        cb:            PipelineCallbacks,
        project_name:  str | None = None,
    ) -> dict:
        """
        Lance le pipeline complet.

        Args:
            source_path:    Chemin vers la vidéo ou le dossier source.
            is_video:       True si source_path est une vidéo.
            native_fps:     FPS natif de la vidéo (ignoré pour les dossiers).
            target_fps:     FPS d'extraction souhaité.
            blur_threshold: Seuil du filtre anti-flou.
            resume_mode:    Mode de reprise ("mapper", "lichtfeld", ou None).
            project_path:   Chemin d'un projet existant (pour la reprise).
            cb:             Callbacks UI pour logs, progression, annulation.

        Returns:
            dict avec les clés :
              - "project_path" : chemin du projet traité
              - "final_ply"    : chemin du .ply généré (ou None)
              - "output_gs"    : chemin du dossier output_gs

        Raises:
            InterruptedError: Si l'utilisateur annule à n'importe quelle étape.
            RuntimeError:     Si une étape critique échoue.
        """
        # Config COLMAP 4.0
        colmap_mode   = self._get_colmap_mode()
        feature_type  = self._get_feature_type()
        matching_type = self._get_matching_type()
        matcher_mode  = self._get_matcher_mode()

        # Prépare l'environnement PATH pour COLMAP
        colmap_env = os.environ.copy()
        if self.colmap_exe:
            colmap_env["PATH"] = (
                os.path.dirname(self.colmap_exe) + os.pathsep + colmap_env["PATH"]
            )

        # Ajouter les DLLs NVIDIA (cuDNN, cuBLAS) du venv au PATH
        # Nécessaire pour ALIKED (ONNX Runtime CUDA)
        import sys
        venv_nvidia = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
        if os.path.isdir(venv_nvidia):
            for subdir in ("cudnn", "cublas", "cuda_nvrtc"):
                dll_dir = os.path.join(venv_nvidia, subdir, "bin")
                if os.path.isdir(dll_dir):
                    colmap_env["PATH"] = dll_dir + os.pathsep + colmap_env["PATH"]

        # ===================================================================
        # ÉTAPE 0 — INITIALISATION : résolution du dossier projet
        # ===================================================================
        if resume_mode in ("mapper", "lichtfeld"):
            # Reprise : on travaille dans le projet existant
            active_project = source_path
        else:
            cb.set_step(0, "doing")
            active_project = paths.resolve_project_path(
                self.projects_dir, project_path, project_name=project_name,
            )
            os.makedirs(os.path.join(active_project, "images"), exist_ok=True)
            cb.set_step(0, "done")

        # Activer le logging fichier complet dans le dossier projet
        os.makedirs(active_project, exist_ok=True)
        cb = self._init_file_logger(active_project, cb)

        try:
            return self._run_pipeline_steps(
                active_project=active_project,
                resume_mode=resume_mode,
                is_video=is_video,
                source_path=source_path,
                target_fps=target_fps,
                native_fps=native_fps,
                blur_threshold=blur_threshold,
                colmap_mode=colmap_mode,
                feature_type=feature_type,
                matching_type=matching_type,
                matcher_mode=matcher_mode,
                colmap_env=colmap_env,
                project_name=project_name,
                cb=cb,
            )
        finally:
            self._close_file_logger(cb)

    def _run_pipeline_steps(
        self,
        *,
        active_project: str,
        resume_mode: str | None,
        is_video: bool,
        source_path: str,
        target_fps: float,
        native_fps: float,
        blur_threshold: float,
        colmap_mode: str,
        feature_type: str,
        matching_type: str,
        matcher_mode: str,
        colmap_env: dict,
        project_name: str | None,
        cb: PipelineCallbacks,
    ) -> dict:
        """Corps principal du pipeline — extrait dans une méthode pour le try/finally du logger."""
        # Log du mode COLMAP actif
        mode_label = "GLOMAP (Global)" if colmap_mode == "global" else "Incrémental"
        cb.log(f"🔧 Mode COLMAP : {mode_label} | Features : {feature_type} | Matcher : {matcher_mode}")

        # Chemins communs à toutes les étapes
        img_dir     = os.path.join(active_project, "images")
        db_path     = os.path.join(active_project, "database.db")
        sparse_path = os.path.join(active_project, "sparse_raw")
        output_gs   = os.path.join(active_project, "output_gs")

        # ===================================================================
        # ÉTAPE 1 — EXTRACTION & TRI (nouveau projet uniquement)
        # ===================================================================
        if resume_mode not in ("mapper", "lichtfeld"):
            cb.log("\n--- MODE : NOUVEAU PROJET ---")
            cb.set_step(1, "doing")

            if is_video:
                cb.log(f"Début de l'extraction par paquets (Seuil netteté: {int(blur_threshold)})...")
                count = extractor.extract_from_video(
                    source_path, img_dir, target_fps, native_fps, blur_threshold, cb
                )
            else:
                cb.log(f"Analyse et tri intelligent des images (Seuil: {int(blur_threshold)})...")
                count = extractor.filter_images_by_blur(
                    source_path, img_dir, blur_threshold, cb
                )

            if count == 0:
                raise RuntimeError(
                    "0 image valide trouvée. Baissez le filtre Anti-Flou et recommencez."
                )
            if count < 5:
                cb.log("⚠️ Avertissement : Moins de 5 images conservées. On force le passage !")

            cb.set_step(1, "done")

            # ---------------------------------------------------------------
            # ÉTAPE 2 — COLMAP FEATURE EXTRACTOR (SIFT ou ALIKED)
            # ---------------------------------------------------------------
            self._check_cancel(cb)
            cb.set_step(2, "doing")
            cb.log(f"\nLancement de l'extraction des features ({feature_type})...")
            # single_camera=True pour les vidéos (même capteur physique)
            # single_camera=False pour les photos (objectifs/capteurs variés possibles)
            colmap_runner.run_feature_extractor(
                colmap_exe    = self.colmap_exe,
                db_path       = db_path,
                img_dir       = img_dir,
                camera_model  = str(self.config.get("colmap_camera_model", "SIMPLE_RADIAL")),
                feature_type  = feature_type,
                single_camera = is_video,
                env           = colmap_env,
                cb            = cb,
            )
            cb.set_step(2, "done")

            # ---------------------------------------------------------------
            # ÉTAPE 3 — COLMAP MATCHER (Séquentiel ou Exhaustif)
            # ---------------------------------------------------------------
            self._check_cancel(cb)
            cb.set_step(3, "doing")

            if matcher_mode == "exhaustive":
                cb.log(f"\nLancement du matching exhaustif ({matching_type})...")
                colmap_runner.run_exhaustive_matcher(
                    colmap_exe    = self.colmap_exe,
                    db_path       = db_path,
                    matching_type = matching_type,
                    env           = colmap_env,
                    cb            = cb,
                )
            else:
                cb.log(f"\nLancement du matching séquentiel ({matching_type})...")
                colmap_runner.run_sequential_matcher(
                    colmap_exe    = self.colmap_exe,
                    db_path       = db_path,
                    overlap       = int(self.config.get("colmap_overlap", 20)),
                    matching_type = matching_type,
                    env           = colmap_env,
                    cb            = cb,
                )
            cb.set_step(3, "done")

        # ===================================================================
        # ÉTAPE 4 — RECONSTRUCTION 3D (Incrémental ou Global GLOMAP)
        # ===================================================================
        if resume_mode != "lichtfeld":
            if resume_mode == "mapper":
                cb.log(f"\n--- MODE : REPRISE COLMAP ({mode_label}) ---")

            self._check_cancel(cb)
            os.makedirs(sparse_path, exist_ok=True)
            cb.set_step(4, "doing")

            img_count = len([
                f for f in os.listdir(img_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ])

            if colmap_mode == "global":
                # --- MODE GLOBAL : View Graph Calibrator → GLOMAP ---
                cb.log("\nCalibration du graphe de vues (pré-requis GLOMAP)...")
                colmap_runner.run_view_graph_calibrator(
                    colmap_exe = self.colmap_exe,
                    db_path    = db_path,
                    env        = colmap_env,
                    cb         = cb,
                )

                self._check_cancel(cb)
                cb.log("\nLancement de la reconstruction globale (GLOMAP)...")
                colmap_runner.run_global_mapper(
                    colmap_exe  = self.colmap_exe,
                    db_path     = db_path,
                    img_dir     = img_dir,
                    sparse_path = sparse_path,
                    img_count   = img_count,
                    env         = colmap_env,
                    cb          = cb,
                )
            else:
                # --- MODE INCRÉMENTAL : Mapper classique ---
                cb.log("\nLancement de la reconstruction 3D (COLMAP Mapper)...")
                colmap_runner.run_mapper(
                    colmap_exe  = self.colmap_exe,
                    db_path     = db_path,
                    img_dir     = img_dir,
                    sparse_path = sparse_path,
                    img_count   = img_count,
                    env         = colmap_env,
                    cb          = cb,
                )

            cb.set_step(4, "done")

            # ---------------------------------------------------------------
            # ÉTAPE 5 — SÉLECTION DU MEILLEUR MODÈLE SPARSE
            # ---------------------------------------------------------------
            cb.set_step(5, "doing")
            best_folder = paths.find_best_sparse_model(sparse_path)
            if not best_folder:
                raise RuntimeError(
                    "Échec de la reconstruction COLMAP : aucun modèle 3D généré."
                )
            cb.set_step(5, "done")

            # ---------------------------------------------------------------
            # ÉTAPE 6 — UNDISTORTION
            # ---------------------------------------------------------------
            self._check_cancel(cb)
            cb.set_step(6, "doing")
            cb.log("\nPréparation des images pour l'entraînement (Undistortion)...")
            os.makedirs(output_gs, exist_ok=True)
            colmap_runner.run_undistorter(
                colmap_exe = self.colmap_exe,
                img_dir    = img_dir,
                input_path = os.path.join(sparse_path, best_folder),
                output_gs  = output_gs,
                env        = colmap_env,
                cb         = cb,
            )

            # Validation post-undistortion : vérifie la cohérence du modèle
            self._validate_undistorted_model(output_gs, cb)
            cb.set_step(6, "done")

        # ===================================================================
        # ÉTAPE 7 — ENTRAÎNEMENT LICHTFELD (tous les modes)
        # ===================================================================
        if resume_mode == "lichtfeld":
            cb.log("\n--- MODE : REPRISE LICHTFELD DIRECTE ---")

        self._check_cancel(cb)

        final_ply = None

        if self.lichtfeld_exe and os.path.exists(self.lichtfeld_exe):
            cb.set_step(7, "doing")
            cb.log("\nLancement de l'entraînement Gaussian Splatting (Lichtfeld)...")

            output_model_dir = os.path.join(active_project, "splat_model")
            os.makedirs(output_model_dir, exist_ok=True)

            lichtfeld_runner.run_lichtfeld_training(
                lichtfeld_exe    = self.lichtfeld_exe,
                output_gs        = output_gs,
                output_model_dir = output_model_dir,
                iterations       = int(self.config.get("lichtfeld_iterations", 7000)),
                strategy         = str(self.config.get("lichtfeld_strategy", "mrnf (Standard)")),
                resize           = str(self.config.get("lichtfeld_resize", "auto")),
                use_mip          = bool(self.config.get("lichtfeld_mip", False)),
                max_splats       = int(self.config.get("lichtfeld_max_splats", 0)),
                tile_mode        = int(self.config.get("lichtfeld_tile_mode", 1)),
                use_gut          = bool(self.config.get("lichtfeld_gut", False)),
                output_name      = project_name,
                cb               = cb,
            )
            cb.set_step(7, "done")

            final_ply = paths.find_ply_in_dir(output_model_dir)

            if not final_ply:
                raise RuntimeError(
                    "Lichtfeld a terminé mais aucun fichier .ply n'a été trouvé dans "
                    f"{output_model_dir}"
                )

            cb.log(f"\n🎉 Succès ! Modèle PLY généré : {final_ply}")

            # Nettoyage automatique des fichiers intermédiaires
            if self.config.get("auto_cleanup", False):
                self._cleanup_intermediates(active_project, cb)

        else:
            cb.log("\n⚠️ Lichtfeld introuvable. Fin du pipeline après COLMAP.")

        return {
            "project_path": active_project,
            "final_ply":    final_ply,
            "output_gs":    output_gs,
        }

    # -----------------------------------------------------------------------
    # Logging fichier — log complet du projet
    # -----------------------------------------------------------------------

    @staticmethod
    def _init_file_logger(
        project_path: str,
        cb: PipelineCallbacks,
    ) -> PipelineCallbacks:
        """
        Active le logging complet dans un fichier pipeline.log du projet.
        - Wrape cb.log() pour écrire aussi chaque message dans le fichier
        - Définit cb.log_to_file() pour les lignes brutes des sous-processus
        - Retourne le cb modifié (avec le handle fichier ouvert)

        Le fichier doit être fermé avec _close_file_logger() en fin de run.
        """
        log_path = os.path.join(project_path, "pipeline.log")
        log_file = open(log_path, "a", encoding="utf-8")

        # Header de session
        log_file.write(f"\n{'='*80}\n")
        log_file.write(f"  AutoSplat Studio — Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"  Projet : {project_path}\n")
        log_file.write(f"{'='*80}\n\n")
        log_file.flush()

        # Sauvegarde du log UI original
        original_log = cb.log

        def wrapped_log(text: str, replace: bool = False):
            """Log UI + écriture dans le fichier projet."""
            original_log(text, replace)
            try:
                # On écrit sans les caractères de remplacement
                log_file.write(text + "\n")
                log_file.flush()
            except Exception:
                pass  # Ne pas bloquer l'UI si l'écriture échoue

        def file_only_log(text: str):
            """Écriture dans le fichier uniquement (lignes brutes subprocess)."""
            try:
                log_file.write(text + "\n")
                log_file.flush()
            except Exception:
                pass

        cb.log = wrapped_log
        cb.log_to_file = file_only_log
        # On stocke le handle dans le cb pour pouvoir le fermer plus tard
        cb._log_file_handle = log_file
        return cb

    @staticmethod
    def _close_file_logger(cb: PipelineCallbacks) -> None:
        """Ferme proprement le fichier de log du projet."""
        log_file = getattr(cb, "_log_file_handle", None)
        if log_file:
            try:
                log_file.write(f"\n{'='*80}\n")
                log_file.write(f"  Fin de session — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"{'='*80}\n")
                log_file.close()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Helpers privés
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_undistorted_model(output_gs: str, cb: PipelineCallbacks) -> None:
        """
        Vérifie la cohérence du modèle sparse undistorté avant Lichtfeld.

        Analyse cameras.bin pour détecter :
          - des résolutions d'images très variées (signe de single_camera=0)
          - un nombre anormal de caméras distinctes
          - des résolutions aberrantes (trop petites ou trop grandes)

        Émet des avertissements dans le log mais ne bloque pas le pipeline.
        """
        import struct

        cameras_bin = os.path.join(output_gs, "sparse", "cameras.bin")
        if not os.path.exists(cameras_bin):
            # Essayer aussi sparse/0/cameras.bin
            cameras_bin = os.path.join(output_gs, "sparse", "0", "cameras.bin")
        if not os.path.exists(cameras_bin):
            cb.log("⚠️ Validation : cameras.bin introuvable, vérification ignorée.")
            return

        try:
            resolutions = set()
            num_cameras = 0

            with open(cameras_bin, "rb") as f:
                # Format binaire COLMAP : uint64 num_cameras en tête
                num_cameras = struct.unpack("<Q", f.read(8))[0]

                for _ in range(num_cameras):
                    # camera_id (uint32), model_id (int32), width (uint64), height (uint64)
                    cam_id = struct.unpack("<I", f.read(4))[0]
                    model_id = struct.unpack("<i", f.read(4))[0]
                    width = struct.unpack("<Q", f.read(8))[0]
                    height = struct.unpack("<Q", f.read(8))[0]
                    resolutions.add((width, height))

                    # Nombre de paramètres par modèle caméra COLMAP
                    params_count = {
                        0: 3,   # SIMPLE_PINHOLE
                        1: 4,   # PINHOLE
                        2: 4,   # SIMPLE_RADIAL
                        3: 5,   # RADIAL
                        4: 8,   # OPENCV
                        5: 12,  # OPENCV_FISHEYE
                        6: 5,   # FULL_RADIAL
                        7: 3,   # SIMPLE_RADIAL_FISHEYE
                        8: 4,   # RADIAL_FISHEYE
                        9: 12,  # THIN_PRISM_FISHEYE
                    }.get(model_id, 4)
                    # Lire les paramètres (double chacun)
                    f.read(params_count * 8)

            # --- Diagnostic ---
            widths = [r[0] for r in resolutions]
            min_w, max_w = min(widths), max(widths)

            cb.log(
                f"📊 Validation undistortion : {num_cameras} caméra(s), "
                f"{len(resolutions)} résolution(s) unique(s)"
            )

            if len(resolutions) > 10:
                cb.log(
                    f"⚠️ ATTENTION : {len(resolutions)} résolutions différentes détectées "
                    f"({min_w}→{max_w} px).\n"
                    f"   Cela peut causer des erreurs Lichtfeld (mémoire ou distorsion).\n"
                    f"   Cause probable : single_camera=0 avec source vidéo.\n"
                    f"   Recommandation : relancer avec single_camera=1 (nouveau projet)."
                )
            elif len(resolutions) > 1:
                cb.log(
                    f"ℹ️ {len(resolutions)} résolutions détectées "
                    f"({min_w}→{max_w} px) — normal pour photos multi-objectifs."
                )

            if max_w > 4096 or min_w < 100:
                cb.log(
                    f"⚠️ Résolutions extrêmes détectées ({min_w}×...→{max_w}×...). "
                    f"Risque d'overflow mémoire dans Lichtfeld."
                )

        except Exception as e:
            cb.log(f"⚠️ Validation undistortion : erreur de lecture ({e})")

    @staticmethod
    def _check_cancel(cb: PipelineCallbacks) -> None:
        """Lève InterruptedError si l'utilisateur a demandé l'annulation."""
        if cb.is_cancelled():
            raise InterruptedError("Processus annulé par l'utilisateur.")

    @staticmethod
    def _cleanup_intermediates(project_path: str, cb: PipelineCallbacks) -> None:
        """
        Supprime les fichiers intermédiaires volumineux après l'entraînement :
          - images/          (les photos sources copiées)
          - sparse_raw/      (modèle COLMAP brut)
          - output_gs/       (images undistortées)
          - database.db      (base de données COLMAP)
        Ne touche pas au dossier splat_model/ (le résultat final).
        """
        cb.log("\n🗑️ Nettoyage automatique des fichiers intermédiaires...")
        time.sleep(1)  # Petite pause pour s'assurer que les handles sont libérés

        targets = [
            os.path.join(project_path, "images"),
            os.path.join(project_path, "sparse_raw"),
            os.path.join(project_path, "output_gs"),
            os.path.join(project_path, "database.db"),
        ]

        for p in targets:
            if not os.path.exists(p):
                continue
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                cb.log(f"  ✓ Supprimé : {os.path.basename(p)}")
            except Exception as e:
                cb.log(f"  ⚠️ Erreur lors de la suppression de {os.path.basename(p)} : {e}")

        cb.log("✅ Nettoyage terminé. Seul le modèle 3D (splat_model/) a été conservé.")
