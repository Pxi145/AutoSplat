"""
ui/app.py
Classe principale AutoSplatApp — Interface utilisateur CustomTkinter.

Responsabilités :
  - Construire et gérer tous les widgets de l'interface
  - Créer les PipelineCallbacks qui font le pont vers le core
  - Déléguer tout le traitement à PipelineOrchestrator
  - Gérer les états UI (boutons, progression, console)
  - Aucune logique métier directe (COLMAP, OpenCV, etc.)

Architecture des callbacks (pont UI ↔ Core) :
  L'App crée un objet PipelineCallbacks à chaque run_process().
  Le pipeline appelle ces callbacks pour logger, mettre à jour la
  progression et signaler les états — sans jamais toucher aux widgets.
"""
import ctypes
import os
import subprocess
import threading

import customtkinter as ctk
from tkinter import filedialog

from config import settings as cfg
from core.callbacks import PipelineCallbacks
from core.pipeline import PipelineOrchestrator
from ui.settings_window import SettingsWindow
from ui.theme import THEME_ACCENT, THEME_BG, THEME_CARD, THEME_TEXT, THEME_TEXT_GRAY, BentoCard

# --- Drag & Drop (optionnel) ---
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False
    print("Info : Drag & Drop non disponible (tkinterdnd2 manquant).")

# --- Détection FPS vidéo ---
try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


# ---------------------------------------------------------------------------
# BaseApp : gère la compatibilité Drag & Drop / CustomTkinter
# ---------------------------------------------------------------------------

if _DND_AVAILABLE:
    class _BaseApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _BaseApp(ctk.CTk):
        pass


# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

class AutoSplatApp(_BaseApp):
    """
    Fenêtre principale d'AutoSplat Studio.
    Orchestre l'UI et délègue le traitement au PipelineOrchestrator.
    """

    # --- Constantes UI ---
    @staticmethod
    def _build_steps(config: dict) -> list[str]:
        """Construit la liste des étapes en fonction du mode COLMAP actif."""
        mode = config.get("colmap_mode", "incremental")
        feature = config.get("colmap_feature_type", "SIFT")
        matcher = config.get("colmap_matcher_type", "sequential")

        # Nom court lisible pour les labels (ALIKED_N16ROT → ALIKED)
        feature_short = "ALIKED" if feature.startswith("ALIKED") else feature
        matcher_label = "Séquentiel" if matcher == "sequential" else "Exhaustif"
        mapper_label  = "Colmap GLOMAP" if mode == "global" else "Colmap Mapper"

        return [
            "Initialisation",
            "Extraction & Tri Intelligent",
            f"Features ({feature_short})",
            f"Matching ({matcher_label})",
            mapper_label,
            "Choix Modèle",
            "Undistortion",
            "Entraînement Lichtfeld",
        ]

    def __init__(self):
        super().__init__()
        self._init_window()
        self._init_paths()
        self._init_state()
        self._init_pipeline()
        self.STEPS = self._build_steps(self.config)
        self.setup_ui()

    # -----------------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------------

    def _init_window(self):
        """Configure la fenêtre principale (icône, titre, dimensions)."""
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "bycn.autosplat.studio.1.0"
            )
            icon_path = os.path.join("bin", "Icone.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"[App] Erreur d'icône : {e}")

        self.title("AutoSplat Studio")
        self.geometry("900x800")
        self.configure(fg_color=THEME_BG)

    def _init_paths(self):
        """Résout les chemins critiques de l'application."""
        self.base_dir     = os.path.dirname(os.path.abspath(__file__))
        # On remonte d'un niveau car app.py est dans ui/
        self.base_dir     = os.path.dirname(self.base_dir)
        self.bin_dir      = os.path.join(self.base_dir, "bin")
        self.projects_dir = os.path.join(self.base_dir, "temp_projects")
        os.makedirs(self.projects_dir, exist_ok=True)

    def _init_state(self):
        """Initialise les variables d'état de l'application."""
        self.config          = cfg.load_config(self.bin_dir)
        self.source_path     = None
        self.is_video        = False
        self.native_fps      = 30.0
        self.resume_mode     = None      # None | "mapper" | "lichtfeld"
        self.project_path    = None
        self.project_name    = None       # Nom personnalisé du projet
        self.is_cancelled    = False
        self._current_process = None     # Popen actif (pour le kill)
        self.console_visible = True

    def _init_pipeline(self):
        """Crée l'orchestrateur du pipeline avec la config actuelle."""
        self.pipeline = PipelineOrchestrator(
            base_dir     = self.base_dir,
            bin_dir      = self.bin_dir,
            projects_dir = self.projects_dir,
            config       = self.config,
        )

    # -----------------------------------------------------------------------
    # Construction de l'interface
    # -----------------------------------------------------------------------

    def setup_ui(self):
        """Point d'entrée pour la construction complète de l'UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_left_column()
        self._build_right_column()

    def _build_header(self):
        """Header : titre, statut Lichtfeld, badge mode COLMAP."""
        lf_ok    = bool(self.pipeline.lichtfeld_exe)
        lf_label = "Lichtfeld ✅" if lf_ok else "Lichtfeld ❌"
        lf_color = THEME_ACCENT if lf_ok else "red"

        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.grid(row=0, column=0, columnspan=2, pady=(15, 5), sticky="ew")

        ctk.CTkLabel(
            self.frame_header, text="AutoSplat Studio",
            font=("Roboto Medium", 28), text_color=THEME_TEXT,
        ).pack()

        # Sous-titre avec le mode COLMAP actif
        self.lbl_subtitle = ctk.CTkLabel(
            self.frame_header,
            text=self._make_subtitle_text(lf_label),
            font=("Roboto", 12), text_color=lf_color,
        )
        self.lbl_subtitle.pack()

        # Toolbar
        toolbar = ctk.CTkFrame(self.frame_header, fg_color="transparent")
        toolbar.pack(pady=(10, 0))

        btn_style = {"fg_color": THEME_CARD, "hover_color": "#333333"}
        ctk.CTkButton(toolbar, text="Importer Dossier Images",  width=150, command=self.shortcut_load_images,      **btn_style).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Reprendre COLMAP (Mapper)", width=170, command=self.shortcut_resume_mapper,    **btn_style).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Entrainement Lichtfeld",    width=150, command=self.shortcut_resume_lichtfeld, **btn_style).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Convertir PLY en USD",      width=150, command=self.shortcut_convert_ply,      **btn_style).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="⚙️ Réglages", width=70,  fg_color="#333333",  hover_color="#555555", command=self.open_settings_window).pack(side="left", padx=(25, 5))
        ctk.CTkButton(toolbar, text="📁 Dossier",  width=70,  fg_color="#eba300",  hover_color="#b77f00", text_color="#302d2d", command=self.open_project_folder).pack(side="left", padx=5)

    def _build_left_column(self):
        """Colonne gauche : zone de drop, paramètres FPS/flou, console."""
        self.left_col = ctk.CTkFrame(self, fg_color="transparent")
        self.left_col.grid(row=1, column=0, padx=15, pady=5, sticky="nsew")

        # Zone Drag & Drop
        self.card_drop = BentoCard(self.left_col)
        self.card_drop.pack(fill="x", pady=(0, 10))

        self.lbl_drop_icon = ctk.CTkLabel(self.card_drop, text="📂", font=("Segoe UI Emoji", 34))
        self.lbl_drop_icon.pack(pady=(20, 0))

        self.lbl_drop_text = ctk.CTkLabel(
            self.card_drop, text="Glisser Vidéo ou Dossier ici",
            font=("Roboto", 14), text_color=THEME_TEXT_GRAY,
        )
        self.lbl_drop_text.pack(pady=(5, 20))

        self.card_drop.bind("<Button-1>",     lambda e: self.select_source())
        self.lbl_drop_text.bind("<Button-1>", lambda e: self.select_source())

        if _DND_AVAILABLE:
            self.card_drop.drop_target_register(DND_FILES)
            self.card_drop.dnd_bind("<<Drop>>", self.on_drop)

        # Paramètres FPS + Flou
        self.card_settings = BentoCard(self.left_col)
        self.card_settings.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            self.card_settings, text="Extraction Vidéo (FPS)",
            font=("Roboto", 12, "bold"), text_color=THEME_ACCENT,
        ).pack(anchor="w", padx=15, pady=(10, 0))

        self.slider_freq = ctk.CTkSlider(
            self.card_settings, from_=1, to=30, number_of_steps=29,
            progress_color=THEME_ACCENT, button_color=THEME_ACCENT,
            command=self.update_fps,
        )
        self.slider_freq.set(30)
        self.slider_freq.pack(fill="x", padx=15, pady=5)

        self.lbl_freq_val = ctk.CTkLabel(
            self.card_settings, text="30 FPS", text_color=THEME_TEXT_GRAY, font=("Roboto", 11)
        )
        self.lbl_freq_val.pack(anchor="e", padx=15, pady=(0, 5))

        ctk.CTkLabel(
            self.card_settings, text="Filtre Anti-Flou",
            font=("Roboto", 12, "bold"), text_color=THEME_ACCENT,
        ).pack(anchor="w", padx=15)

        self.slider_blur = ctk.CTkSlider(
            self.card_settings, from_=0, to=100, number_of_steps=100,
            progress_color=THEME_ACCENT, button_color=THEME_ACCENT,
            command=self.update_blur,
        )
        blur_val = self.config.get("default_blur_threshold", 30)
        self.slider_blur.set(blur_val)
        self.slider_blur.pack(fill="x", padx=15, pady=5)

        self.lbl_blur_val = ctk.CTkLabel(
            self.card_settings, text=f"Seuil : {blur_val}",
            text_color=THEME_TEXT_GRAY, font=("Roboto", 11)
        )
        self.lbl_blur_val.pack(anchor="e", padx=15, pady=(0, 10))

        # Console
        ctk.CTkButton(
            self.left_col, text="Afficher / Masquer Console",
            fg_color="#333333", command=self.toggle_console, height=25,
        ).pack(fill="x", pady=(0, 5))

        self.card_console = BentoCard(self.left_col)
        self.console_text = ctk.CTkTextbox(
            self.card_console, font=("Consolas", 10),
            fg_color="#1a1a1a", text_color="#cccccc",
        )
        self.console_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.card_console.pack(fill="both", expand=True)

    def _build_right_column(self):
        """Colonne droite : progression, bouton RUN, moniteur vidéo."""
        self.right_col = ctk.CTkFrame(self, fg_color="transparent")
        self.right_col.grid(row=1, column=1, padx=15, pady=5, sticky="nsew")

        # Use grid inside right_col so the monitor can fill remaining space
        self.right_col.grid_columnconfigure(0, weight=1)
        self.right_col.grid_rowconfigure(0, weight=0)  # progress card
        self.right_col.grid_rowconfigure(1, weight=0)  # run button
        self.right_col.grid_rowconfigure(2, weight=0)  # lichtfeld button
        self.right_col.grid_rowconfigure(3, weight=1)  # monitor (expands)

        # Carte progression
        self.card_progress = BentoCard(self.right_col)
        self.card_progress.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        ctk.CTkLabel(
            self.card_progress, text="Avancement",
            font=("Roboto", 16, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 5))

        self.progress_bar = ctk.CTkProgressBar(
            self.card_progress, height=12, corner_radius=10, progress_color=THEME_ACCENT
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 15))

        # Labels des étapes
        self.frame_steps = ctk.CTkFrame(self.card_progress, fg_color="transparent")
        self.frame_steps.pack(fill="x", padx=20, pady=(0, 15))
        self.step_labels: dict[int, ctk.CTkLabel] = {}

        for i, step_name in enumerate(self.STEPS):
            lbl = ctk.CTkLabel(
                self.frame_steps, text=f"○ {step_name}",
                font=("Roboto", 13), text_color=THEME_TEXT_GRAY, anchor="w",
            )
            lbl.pack(fill="x", pady=1)
            self.step_labels[i] = lbl

        # Bouton RUN
        self.btn_run = ctk.CTkButton(
            self.right_col,
            text="LANCER LE TRAITEMENT",
            font=("Roboto", 16, "bold"),
            height=50, corner_radius=25,
            fg_color=THEME_ACCENT, hover_color="#ff7b3b",
            command=self.start_thread,
            state="disabled",
            text_color="black",
            text_color_disabled="#333333",
        )
        self.btn_run.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Bouton "Ouvrir dans Lichtfeld" (masqué par défaut)
        self.btn_open_lf = ctk.CTkButton(
            self.right_col,
            text="OUVRIR DANS LICHTFELD",
            font=("Roboto", 14, "bold"),
            height=40, corner_radius=20,
            fg_color="#2b2b2b", hover_color="#444444",
        )
        # btn_open_lf n'est pas gridé ici → affiché uniquement en fin de traitement

        # Moniteur vidéo (masqué par défaut) — no fixed height, will fill space
        self.lbl_monitor = ctk.CTkLabel(
            self.right_col, text="Moniteur en attente...",
            fg_color="#1a1a1a", corner_radius=10,
        )
        # lbl_monitor n'est pas gridé ici → affiché pendant l'extraction
        # Cached monitor area size — updated only on real window resizes
        self._monitor_cached_size = (0, 0)
        self._monitor_pil_img = None
        self._monitor_active = False
        self._monitor_resize_after_id = None  # debounce timer for resize

    # -----------------------------------------------------------------------
    # Gestion de la fenêtre Paramètres
    # -----------------------------------------------------------------------

    def open_settings_window(self):
        """Ouvre la fenêtre modale de paramètres."""
        SettingsWindow(
            master   = self,
            config   = self.config,
            on_save  = self._on_settings_saved,
            on_error = lambda msg: self.log(msg),
        )

    def _on_settings_saved(self, new_config: dict):
        """Appelé par SettingsWindow après validation — met à jour config + pipeline + slider + bannière."""
        cfg.save_config(self.bin_dir, new_config)
        self.config = new_config
        self.pipeline.update_config(new_config)

        # Mise à jour du slider flou sans déclencher le callback
        new_blur = new_config.get("default_blur_threshold", 30)
        self.slider_blur.set(new_blur)
        self.update_blur(new_blur)

        # Rafraîchir la bannière et les labels des étapes
        self._refresh_mode_ui()

        self.log("⚙️ Paramètres sauvegardés avec succès !")

    # -----------------------------------------------------------------------
    # Raccourcis (Toolbar)
    # -----------------------------------------------------------------------

    def shortcut_load_images(self):
        """Importe un dossier d'images (ou un dossier projet existant)."""
        folder = filedialog.askdirectory(title="Sélectionner un dossier Images ou Projet")
        if not folder:
            return
        # Si le dossier contient un sous-dossier "images", on l'utilise directement
        images_sub = os.path.join(folder, "images")
        if os.path.exists(images_sub):
            folder = images_sub
        self.load_source(folder)

    def shortcut_resume_mapper(self):
        """Reprend un projet existant à partir du COLMAP Mapper."""
        folder = filedialog.askdirectory(title="Sélectionner le dossier du Projet")
        if not folder:
            return

        # Correction si l'utilisateur sélectionne le sous-dossier images/
        if os.path.basename(folder).lower() == "images":
            folder = os.path.dirname(folder)

        db_file  = os.path.join(folder, "database.db")
        img_dir  = os.path.join(folder, "images")

        if not os.path.exists(db_file) or not os.path.exists(img_dir):
            self.log(f"ERREUR : 'database.db' introuvable dans {folder}")
            self.btn_run.configure(text="ERREUR (database manquant)", fg_color="red", state="disabled")
            return

        self.source_path  = folder
        self.project_path = folder
        self.resume_mode  = "mapper"
        self._reset_steps_ui()

        for i in range(4):
            self.set_step_status(i, "done")

        self.lbl_drop_text.configure(text=f"REPRISE COLMAP\n{os.path.basename(folder)}", text_color=THEME_ACCENT)
        self.lbl_drop_icon.configure(text="🔄")
        self.slider_freq.configure(state="disabled")
        self.slider_blur.configure(state="disabled")
        self.btn_run.configure(state="normal", text="REPRENDRE AU MAPPER", fg_color=THEME_ACCENT, command=self.start_thread)
        self.progress_bar.set(0)
        self.log(f"Projet chargé pour reprise COLMAP Mapper : {folder}")

    def shortcut_resume_lichtfeld(self):
        """Reprend un projet existant directement à l'entraînement Lichtfeld."""
        folder = filedialog.askdirectory(title="Sélectionner le dossier du Projet")
        if not folder:
            return

        if os.path.basename(folder).lower() == "output_gs":
            folder = os.path.dirname(folder)

        output_gs = os.path.join(folder, "output_gs")
        if not os.path.exists(output_gs):
            self.log(f"ERREUR : 'output_gs' introuvable dans {folder}")
            self.btn_run.configure(text="ERREUR (output_gs manquant)", fg_color="red", state="disabled")
            return

        self.source_path  = folder
        self.project_path = folder
        self.resume_mode  = "lichtfeld"
        self._reset_steps_ui()

        for i in range(7):
            self.set_step_status(i, "done")

        self.lbl_drop_text.configure(text=f"REPRISE LICHTFELD\n{os.path.basename(folder)}", text_color=THEME_ACCENT)
        self.lbl_drop_icon.configure(text="✨")
        self.slider_freq.configure(state="disabled")
        self.slider_blur.configure(state="disabled")
        self.btn_run.configure(state="normal", text="LANCER ENTRAÎNEMENT", fg_color=THEME_ACCENT, command=self.start_thread)
        self.progress_bar.set(0)
        self.log(f"Projet chargé pour reprise Lichtfeld : {folder}")

    def shortcut_convert_ply(self):
        """Convertit directement un .ply en USD via LichtFeld convert."""
        folder = filedialog.askdirectory(title="Sélectionner le dossier Projet (ou contenant le .ply)")
        if not folder:
            return

        # Recherche récursive du dernier .ply
        final_ply = None
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".ply"):
                    final_ply = os.path.join(root, f)

        if not final_ply:
            self.log(f"ERREUR : Aucun fichier .ply trouvé dans {os.path.basename(folder)}.")
            return

        self.progress_bar.set(1)
        self.lbl_drop_text.configure(text=f"PLY TROUVÉ\n{os.path.basename(final_ply)}", text_color=THEME_ACCENT)
        self.lbl_drop_icon.configure(text="📦")
        self.log(f"Fichier PLY détecté : {final_ply}")
        self.launch_usd_export(final_ply)

    # -----------------------------------------------------------------------
    # Gestion de la source (vidéo ou dossier)
    # -----------------------------------------------------------------------

    def on_drop(self, event):
        path = event.data
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        self.load_source(path)

    def select_source(self):
        path = filedialog.askopenfilename(
            filetypes=[("Media", "*.mp4 *.mov *.avi *.jpg *.png")]
        )
        if path:
            self.load_source(path)

    def load_source(self, path: str):
        """Analyse la source (vidéo ou dossier), met à jour l'UI en conséquence."""
        if not os.path.exists(path):
            return

        self.source_path  = path
        self.resume_mode  = None
        self.project_path = None
        self.progress_bar.set(0)
        self.btn_open_lf.grid_forget()
        self.btn_run.configure(command=self.start_thread)

        video_exts = (".mp4", ".mov", ".avi")

        if os.path.isfile(path) and path.lower().endswith(video_exts):
            # --- Source vidéo ---
            self.is_video  = True
            self.native_fps = 30.0

            if _CV2_AVAILABLE:
                import cv2
                cap = cv2.VideoCapture(path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                if 0 < fps <= 120:
                    self.native_fps = fps

            max_fps = int(self.native_fps)
            self.slider_freq.configure(
                from_=1, to=max_fps,
                number_of_steps=max(1, max_fps - 1),
                state="normal",
            )
            self.slider_freq.set(max_fps)
            self.update_fps(max_fps)
            display = f"VIDÉO PRÊTE\n{os.path.basename(path)} (~{max_fps} FPS natif)"

        else:
            # --- Source dossier d'images ---
            self.is_video = False
            if os.path.isfile(path):
                path = os.path.dirname(path)
            self.source_path = path
            self.slider_freq.configure(state="disabled")
            display = f"DOSSIER IMAGES\n{os.path.basename(path)}"

        self.lbl_drop_text.configure(text=display, text_color=THEME_ACCENT)
        self.lbl_drop_icon.configure(text="✅")
        self.btn_run.configure(state="normal", text="LANCER LE TRAITEMENT")

    # -----------------------------------------------------------------------
    # Contrôle du traitement
    # -----------------------------------------------------------------------

    def start_thread(self):
        """Affiche la boîte de dialogue de nommage puis lance le pipeline."""
        if self.resume_mode:
            # Reprise → pas de dialogue de nommage
            self.project_name = None
            self._do_start_thread()
        else:
            self._show_naming_dialog()

    def _show_naming_dialog(self):
        """Dialogue compact centré pour nommer le projet."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nom du Projet")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Centrer sur la fenêtre parente
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"400x180+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="Nommer votre projet",
            font=("Roboto", 16, "bold"), text_color=THEME_ACCENT,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog, text="Laissez vide pour un nom généré automatiquement",
            font=("Roboto", 10), text_color=THEME_TEXT_GRAY,
        ).pack(pady=(0, 10))

        entry = ctk.CTkEntry(
            dialog, width=300, placeholder_text="ex: salon_maison_bleue",
            font=("Roboto", 13),
        )
        entry.pack(pady=(0, 15))
        entry.focus()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def _on_confirm():
            name = entry.get().strip()
            self.project_name = name if name else None
            dialog.destroy()
            self._do_start_thread()

        def _on_skip():
            self.project_name = None
            dialog.destroy()
            self._do_start_thread()

        ctk.CTkButton(
            btn_frame, text="Lancer", width=120,
            fg_color=THEME_ACCENT, hover_color="#ff7b3b", text_color="black",
            command=_on_confirm,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="Sans nom", width=120,
            fg_color="#333333", hover_color="#555555",
            command=_on_skip,
        ).pack(side="left", padx=10)

        # Entrée valide avec Enter
        entry.bind("<Return>", lambda e: _on_confirm())

    def _do_start_thread(self):
        """Lance effectivement le pipeline dans un thread de fond."""
        self.is_cancelled = False
        self.btn_run.configure(
            state="normal", text="ANNULER LE TRAITEMENT",
            fg_color="#ef4444", hover_color="#dc2626",
            command=self.cancel_process,
        )
        self._reset_steps_ui()
        threading.Thread(target=self._run_process, daemon=True).start()

    def cancel_process(self):
        """Demande l'annulation et tue le processus actif si nécessaire."""
        self.log("\n[!] ARRÊT DEMANDÉ. Annulation en cours...")
        self.is_cancelled = True
        self.btn_run.configure(state="disabled", text="ANNULATION...", fg_color="gray")
        if self._current_process:
            try:
                self._current_process.kill()
            except Exception:
                pass

    def _run_process(self):
        """Exécute dans le thread de fond — appelle le pipeline et gère les résultats."""
        cb = self._make_callbacks()

        # Résoudre le project_path AVANT le pipeline pour que le bouton Dossier
        # puisse l'utiliser pendant le traitement
        if not self.resume_mode and not self.project_path:
            from core.paths import resolve_project_path
            self.project_path = resolve_project_path(
                self.projects_dir, project_name=self.project_name,
            )
            os.makedirs(self.project_path, exist_ok=True)

        try:
            result = self.pipeline.run(
                source_path    = self.source_path,
                is_video       = self.is_video,
                native_fps     = self.native_fps,
                target_fps     = float(self.slider_freq.get()),
                blur_threshold = float(self.slider_blur.get()),
                resume_mode    = self.resume_mode,
                project_path   = self.project_path,
                cb             = cb,
                project_name   = self.project_name,
            )

            # Mise à jour de l'état depuis le résultat
            self.project_path = result["project_path"]
            final_ply  = result["final_ply"]
            output_gs  = result["output_gs"]

            if final_ply:
                # Succès complet : on propose l'export et l'ouverture Lichtfeld
                export_fmt = self.config.get("export_format", "usd").upper()
                self.btn_run.configure(
                    text=f"EXPORTER EN {export_fmt}",
                    fg_color=THEME_ACCENT, text_color="white", state="normal",
                    command=lambda p=final_ply: self.launch_usd_export(p),
                )
                self.btn_open_lf.configure(
                    command=lambda p=final_ply: self.launch_lichtfeld_viewer(p)
                )
                self.btn_open_lf.grid(row=2, column=0, sticky="ew", pady=(0, 10))
            else:
                # Pipeline partiel (Lichtfeld absent)
                self.btn_run.configure(
                    text="TERMINÉ (Ouvrir Dossier)",
                    fg_color="#4ade80", text_color="black", state="normal",
                    command=lambda p=output_gs: os.startfile(p),
                )

        except InterruptedError as e:
            self.log(f"\n🛑 {e}")
            self.btn_run.configure(text="TRAITEMENT ANNULÉ", fg_color="#333333", state="disabled")

        except RuntimeError as e:
            self.log(f"\n❌ ERREUR : {e}")
            self.btn_run.configure(text="ERREUR (Voir Console)", fg_color="red", state="normal")

        except Exception as e:
            self.log(f"\n💥 ERREUR CRITIQUE : {e}")
            self.btn_run.configure(text="ERREUR FATALE", fg_color="red", state="normal")

    # -----------------------------------------------------------------------
    # Création des Callbacks (pont UI ↔ Core)
    # -----------------------------------------------------------------------

    def _make_callbacks(self) -> PipelineCallbacks:
        """Construit l'objet PipelineCallbacks avec les méthodes UI de cette instance."""
        return PipelineCallbacks(
            log                = self.log,
            set_step           = self.set_step_status,
            update_monitor     = self._cb_update_monitor,
            is_cancelled       = lambda: self.is_cancelled,
            set_current_process= lambda p: setattr(self, "_current_process", p),
        )

    def _cb_update_monitor(self, ctk_img):
        """
        Callback pour le moniteur vidéo temps réel.
        - ctk_img = None → masquer le moniteur
        - ctk_img = CTkImage → afficher/mettre à jour
        """
        if ctk_img is None:
            self._monitor_pil_img = None
            self._monitor_active = False
            def _hide():
                self.lbl_monitor.grid_forget()
                try:
                    self.lbl_monitor.unbind("<Configure>")
                except Exception:
                    pass
            self.lbl_monitor.after(0, _hide)
        else:
            # Store the raw PIL image for fitting to cached size
            try:
                self._monitor_pil_img = ctk_img._light_image
            except AttributeError:
                self._monitor_pil_img = None

            def _update():
                # First time: show the label and bind the resize listener
                if not self._monitor_active:
                    self._monitor_active = True
                    self.lbl_monitor.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
                    self.lbl_monitor.bind("<Configure>", self._on_monitor_configure)

                # Fit the new frame to the known monitor area
                fitted = self._fit_image_to_monitor(self._monitor_pil_img)
                if fitted is not None:
                    self.lbl_monitor.configure(image=fitted, text="")
                else:
                    self.lbl_monitor.configure(image=ctk_img, text="")
            self.lbl_monitor.after(0, _update)

    def _fit_image_to_monitor(self, pil_img):
        """
        Scale a PIL image to fit inside the cached monitor dimensions.
        Returns a CTkImage sized to fit, or None if dimensions unknown.
        """
        if pil_img is None:
            return None
        w, h = self._monitor_cached_size
        if w < 20 or h < 20:
            return None
        try:
            import customtkinter as ctk
            orig_w, orig_h = pil_img.size
            scale = min(w / orig_w, h / orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            return ctk.CTkImage(
                light_image=pil_img, dark_image=pil_img,
                size=(new_w, new_h),
            )
        except Exception:
            return None

    def _on_monitor_configure(self, event):
        """
        Called by tkinter when the monitor label's allocated area changes
        (i.e. the user resizes the window). Debounced: only re-fits the
        image 150ms after the last resize event to keep dragging smooth.
        """
        new_size = (event.width, event.height)
        if new_size == self._monitor_cached_size:
            return  # Nothing changed — don't touch anything
        self._monitor_cached_size = new_size

        # Cancel any pending resize timer
        if self._monitor_resize_after_id is not None:
            self.lbl_monitor.after_cancel(self._monitor_resize_after_id)

        # Schedule the actual re-fit after 150ms of no further resize events
        def _deferred_fit():
            self._monitor_resize_after_id = None
            if self._monitor_pil_img is not None:
                fitted = self._fit_image_to_monitor(self._monitor_pil_img)
                if fitted is not None:
                    self.lbl_monitor.configure(image=fitted, text="")

        self._monitor_resize_after_id = self.lbl_monitor.after(150, _deferred_fit)

    # -----------------------------------------------------------------------
    # Lancement des outils externes
    # -----------------------------------------------------------------------

    def launch_lichtfeld_viewer(self, ply_path: str):
        """Ouvre le fichier .ply dans Lichtfeld Studio en mode visionneuse."""
        self.log(f"\nOuverture de Lichtfeld avec : {os.path.basename(ply_path)}")
        try:
            lf_dir = os.path.dirname(self.pipeline.lichtfeld_exe)
            flags  = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            subprocess.Popen(
                [self.pipeline.lichtfeld_exe, "--view", ply_path],
                cwd=lf_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        except Exception as e:
            self.log(f"Erreur ouverture Lichtfeld : {e}")

    def launch_usd_export(self, ply_path: str):
        """Lance l'export via LichtFeld convert dans un thread séparé."""
        output_dir    = os.path.dirname(ply_path)
        export_format = self.config.get("export_format", "usd")
        fmt_upper     = export_format.upper()

        if not self.pipeline.lichtfeld_exe:
            self.log("\n⚠️ LichtFeld introuvable — export impossible.")
            return

        self.log(f"\nLancement de l'export {fmt_upper}...")
        self.btn_run.configure(state="disabled", text=f"CONVERSION {fmt_upper} EN COURS...")

        def _export_thread():
            from core.usd_exporter import run_usd_export
            cb = self._make_callbacks()
            try:
                output_file = run_usd_export(
                    lichtfeld_exe = self.pipeline.lichtfeld_exe,
                    ply_path      = ply_path,
                    output_dir    = output_dir,
                    export_format = export_format,
                    cb            = cb,
                )
                result_dir = os.path.dirname(output_file)
                self.btn_run.configure(
                    text=f"OUVRIR LE DOSSIER {fmt_upper}",
                    fg_color="#4ade80", text_color="black", state="normal",
                    command=lambda: os.startfile(result_dir),
                )
            except Exception as e:
                self.log(f"\n⚠️ Échec de la conversion : {e}")
                self.btn_run.configure(
                    text="ERREUR D'EXPORT", fg_color="red", text_color="white", state="normal"
                )

        threading.Thread(target=_export_thread, daemon=True).start()

    # -----------------------------------------------------------------------
    # Gestion du dossier projet
    # -----------------------------------------------------------------------

    def open_project_folder(self):
        """
        Ouvre le dossier projet dans l'Explorateur Windows.
        - Si un projet est en cours → ouvre le dossier du projet.
        - Sinon → ouvre temp_projects pour voir tous les projets.
        """
        if self.project_path and os.path.exists(self.project_path):
            target = self.project_path
            self.log(f"📁 Ouverture du projet : {os.path.basename(target)}")
        else:
            target = self.projects_dir
            self.log("📁 Ouverture du dossier des projets")
        try:
            os.startfile(target)
        except Exception as e:
            self.log(f"⚠️ Impossible d'ouvrir le dossier : {e}")

    # -----------------------------------------------------------------------
    # Helpers UI
    # -----------------------------------------------------------------------

    def toggle_console(self):
        if self.console_visible:
            self.card_console.pack_forget()
            self.console_visible = False
        else:
            self.card_console.pack(fill="both", expand=True)
            self.console_visible = True

    def update_fps(self, val):
        self.lbl_freq_val.configure(text=f"{int(val)} FPS (Max: {int(self.native_fps)})")

    def update_blur(self, val):
        self.lbl_blur_val.configure(text=f"Seuil : {int(val)}")

    def log(self, text: str, replace: bool = False):
        """Affiche un message dans la console. Si replace=True, écrase la dernière ligne."""
        if replace:
            self.console_text.delete("end-2l", "end-1c")
        self.console_text.insert("end", text + "\n")
        self.console_text.see("end")

    def set_step_status(self, index: int, status: str):
        """
        Met à jour l'icône et la couleur d'une étape.
        status = "doing" → orange + flèche
        status = "done"  → vert + coche
        """
        lbl = self.step_labels.get(index)
        if not lbl:
            return
        current_text = lbl.cget("text")

        if status == "doing":
            new_text = current_text.replace("○", "➤").replace("✓", "➤")
            lbl.configure(text=new_text, text_color=THEME_ACCENT, font=("Roboto", 14, "bold"))
            self.progress_bar.set((index + 0.5) / len(self.STEPS))

        elif status == "done":
            new_text = current_text.replace("➤", "✓").replace("○", "✓")
            lbl.configure(text=new_text, text_color="#4ade80", font=("Roboto", 14))
            self.progress_bar.set((index + 1) / len(self.STEPS))

    def _reset_steps_ui(self):
        """Remet toutes les étapes à l'état initial (cercle vide, gris)."""
        for lbl in self.step_labels.values():
            text = lbl.cget("text").replace("✓", "○").replace("➤", "○")
            lbl.configure(text=text, text_color=THEME_TEXT_GRAY, font=("Roboto", 13))

    # -----------------------------------------------------------------------
    # Helpers COLMAP Mode (bannière + étapes dynamiques)
    # -----------------------------------------------------------------------

    def _make_subtitle_text(self, lf_label: str = None) -> str:
        """Construit le texte du sous-titre avec le mode COLMAP actif."""
        if lf_label is None:
            lf_ok    = bool(self.pipeline.lichtfeld_exe)
            lf_label = "Lichtfeld ✅" if lf_ok else "Lichtfeld ❌"

        mode    = self.config.get("colmap_mode", "incremental")
        feature = self.config.get("colmap_feature_type", "SIFT")

        mode_tag    = "GLOMAP" if mode == "global" else "Incrémental"
        feature_tag = "ALIKED" if feature.startswith("ALIKED") else feature

        return f"COLMAP {mode_tag} • {feature_tag} • {lf_label}"

    def _refresh_mode_ui(self):
        """Met à jour la bannière et les labels des étapes pour refléter le mode actif."""
        # Mettre à jour le sous-titre
        self.lbl_subtitle.configure(text=self._make_subtitle_text())

        # Reconstruire les labels d'étapes avec les noms dynamiques
        self.STEPS = self._build_steps(self.config)
        for i, step_name in enumerate(self.STEPS):
            lbl = self.step_labels.get(i)
            if lbl:
                # Garder l'icône actuelle (○, ➤, ✓)
                current = lbl.cget("text")
                icon = current[0] if current else "○"
                lbl.configure(text=f"{icon} {step_name}")
