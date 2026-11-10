import os
import re
import sys
import csv
import math
import base64
import ctypes
import logging
import warnings
import webbrowser
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np

# Configure standard application logger without clobbering existing test/host handlers
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
logger = logging.getLogger("MouseComparator")

APP_NAME = "MouseComparator PRO"
APP_ID = "com.zalma.mousecomparator.pro"
APP_VERSION = "0.0.1"


# ==============================================================================
# RESOURCE PATH, UNICODE I/O & NATIVE OS BRANDING
# ==============================================================================
def get_resource_path(relative_path: str) -> str:
    """Finds bundled resources (icon.ico, icon.icns) in dev, assets/, cwd, and PyInstaller builds."""
    search_dirs = []
    if hasattr(sys, "_MEIPASS"):
        search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.join(sys._MEIPASS, "assets"))
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs.append(script_dir)
    search_dirs.append(os.path.join(script_dir, "assets"))
    search_dirs.append(os.getcwd())
    search_dirs.append(os.path.join(os.getcwd(), "assets"))
    for base_path in search_dirs:
        candidate = os.path.join(base_path, relative_path)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(script_dir, "assets", relative_path)


def configure_native_os_identity():
    """Configures native OS app identity and High-DPI awareness for Windows taskbars and macOS Dock."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError) as e:
            logger.debug("Win32 AppUserModelID configuration failed: %s", e)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError) as e:
                logger.debug("Win32 DPI awareness configuration skipped: %s", e)
    elif sys.platform == "darwin":
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            if bundle:
                info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
                if info is not None:
                    info["CFBundleName"] = APP_NAME
                    info["CFBundleDisplayName"] = APP_NAME
        except (ImportError, AttributeError, KeyError) as e:
            logger.debug("macOS NSBundle branding configuration failed: %s", e)


def apply_window_icon(root):
    """Applies icon.ico or icon.icns to the Tkinter window and Dock."""
    ico_path = get_resource_path("icon.ico")
    icns_path = get_resource_path("icon.icns")

    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            root.iconbitmap(default=ico_path)
            return
        except (tk.TclError, OSError) as e:
            logger.debug("Win32 iconbitmap set failed: %s", e)
    elif sys.platform == "darwin" and os.path.exists(icns_path):
        try:
            from AppKit import NSApplication, NSImage
            ns_app = NSApplication.sharedApplication()
            ns_img = NSImage.alloc().initWithContentsOfFile_(icns_path)
            if ns_img:
                ns_app.setApplicationIconImage_(ns_img)
        except (ImportError, AttributeError, OSError) as e:
            logger.debug("macOS NSApplication icon set failed: %s", e)

    if os.path.exists(ico_path):
        try:
            raw_bytes = np.fromfile(ico_path, dtype=np.uint8)
            img = cv2.imdecode(raw_bytes, cv2.IMREAD_UNCHANGED) if raw_bytes.size > 0 else None
            if img is None and raw_bytes.size > 8:
                png_offset = raw_bytes.tobytes().find(b"\x89PNG\r\n\x1a\n")
                if png_offset >= 0:
                    img = cv2.imdecode(raw_bytes[png_offset:], cv2.IMREAD_UNCHANGED)
            if img is not None:
                ok, buf = cv2.imencode(".png", img)
                if ok:
                    root._app_icon_ref = tk.PhotoImage(data=buf.tobytes())
                    root.iconphoto(True, root._app_icon_ref)
        except (tk.TclError, cv2.error, OSError) as e:
            logger.debug("Fallback PhotoImage icon set failed: %s", e)


def save_image_unicode(path: str, img: np.ndarray) -> bool:
    """Writes an OpenCV image to disk safely across Unicode/accented file paths."""
    if img is None:
        return False
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        ext = os.path.splitext(path)[1] or ".jpg"
        is_success, im_buf_arr = cv2.imencode(ext, img)
        if is_success:
            im_buf_arr.tofile(path)
            return True
    except (OSError, cv2.error) as e:
        logger.debug("save_image_unicode exception on %s: %s", path, e)
    return False


def read_image_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """Reads an OpenCV image from disk safely across Unicode/accented file paths."""
    if not path or not os.path.isfile(path):
        return None
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size > 0:
            return cv2.imdecode(data, flags)
    except (OSError, cv2.error) as e:
        logger.debug("read_image_unicode exception on %s: %s", path, e)
    return None


def sanitize_csv_cell(val: Any) -> str:
    """Prevents CSV formula injection (=, +, -, @, tab, CR) when exporting tables."""
    s = str(val) if val is not None else ""
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# ==============================================================================
# BILINGUAL TRANSLATION DICTIONARY (HU / EN)
# ==============================================================================
TRANSLATIONS = {
    "hu": {
        "subtitle": "Tudományos hőtérkép, mozgáskép és kinematikai összehasonlító munkaállomás",
        "btn_load_dir_a": "📂 Mappa / CSV 'A' betöltése",
        "btn_load_dir_b": "📂 Mappa / CSV 'B' betöltése",
        "btn_export_img": "🖼 Összefoglaló Kép",
        "btn_export_csv": "📊 Delta CSV",
        "btn_export_html": "📄 HTML / PDF Riport",
        "mode_1v1": "🔍 1-vs-1 Összehasonlítás (A vs B)",
        "mode_long": "📈 Longitudinális / Futások (Idősor)",
        "mode_cohort": "👥 Kohorsz / Csoport (A vs B)",
        "lbl_select_a": "Mérés A (Bázis / Kontroll):",
        "lbl_select_b": "Mérés B (Összehasonlított):",
        "lbl_artifact": "Képi réteg:",
        "art_heatmap": "Hőtérkép (Heatmap)",
        "art_faded_hm": "Halvány Hőtérkép",
        "art_summary": "Mozgáskép (Összefoglaló)",
        "art_combined_hm": "Összesített Hőtérkép",
        "art_dips": "Lábhiba / Lenyúlás Galéria",
        "lbl_view_mode": "Nézet:",
        "view_sbs": "Egymás mellett",
        "view_wipe": "Csúszka (Wipe)",
        "view_diff": "Δ Hőtérkép (Különbség)",
        "view_blend": "Áttűnés (Blend)",
        "view_radar": "Radar & Zóna Grafikon",
        "lbl_slider": "Csúszka / Áttűnés (%):",
        "col_metric": "Kinematikai / Viselkedési Mutató",
        "col_val_a": "Érték A",
        "col_val_b": "Érték B",
        "col_delta": "Különbség (Δ)",
        "col_pct": "Változás (%)",
        "col_eval": "Értékelés",
        "col_p_val": "p-érték (t / MW-U)",
        "col_cohen": "Cohen's d",
        "eval_improved": "✔ Javulás",
        "eval_worse": "⚠ Romlás",
        "eval_neutral": "➖ Változatlan",
        "kpi_records_a": "MÉRÉSEK (A CSOPORT)",
        "kpi_records_b": "MÉRÉSEK (B CSOPORT)",
        "kpi_ssim": "TÉRforgalmi HASONLÓSÁG (SSIM)",
        "kpi_headline": "FŐ KINEMATIKAI ELTÉRÉS",
        "long_subject": "Vizsgált Egyed (ID):",
        "long_metric": "Idősoros Mutató:",
        "msg_no_data": "Nincs betöltött mérés. Kérjük töltsön be egy MouseAnalyzer eredmény mappát vagy CSV fájlt!",
        "msg_exported": "✅ Sikeres exportálás ide:\n{path}",
        "status_ready": "Kész. Töltsön be MouseAnalyzer mappákat vagy CSV fájlokat az összehasonlításhoz.",
        "status_loaded": "Betöltve: A={na} futás ({sa} egyed) | B={nb} futás ({sb} egyed)",
    },
    "en": {
        "subtitle": "Scientific Heatmap, Motion Picture & Kinematic Comparison Workstation",
        "btn_load_dir_a": "📂 Load Folder / CSV 'A'",
        "btn_load_dir_b": "📂 Load Folder / CSV 'B'",
        "btn_export_img": "🖼 Summary Image",
        "btn_export_csv": "📊 Delta CSV",
        "btn_export_html": "📄 HTML / PDF Report",
        "mode_1v1": "🔍 1-vs-1 Comparison (A vs B)",
        "mode_long": "📈 Longitudinal / Multi-Run",
        "mode_cohort": "👥 Cohort / Group (A vs B)",
        "lbl_select_a": "Record A (Baseline / Control):",
        "lbl_select_b": "Record B (Target / Treated):",
        "lbl_artifact": "Visual Layer:",
        "art_heatmap": "Velocity Heatmap",
        "art_faded_hm": "Faded Heatmap",
        "art_summary": "Motion Summary Picture",
        "art_combined_hm": "Combined Multi-Run Heatmap",
        "art_dips": "Paw Fault / Dip Gallery",
        "lbl_view_mode": "View Mode:",
        "view_sbs": "Side-by-Side",
        "view_wipe": "Curtain Wipe Slider",
        "view_diff": "Δ Difference Heatmap",
        "view_blend": "Onion-Skin Blend",
        "view_radar": "Radar & Zone Charts",
        "lbl_slider": "Wipe / Blend (%):",
        "col_metric": "Kinematic / Behavioral Metric",
        "col_val_a": "Value A",
        "col_val_b": "Value B",
        "col_delta": "Delta (Δ)",
        "col_pct": "Change (%)",
        "col_eval": "Assessment",
        "col_p_val": "p-value (t / MW-U)",
        "col_cohen": "Cohen's d",
        "eval_improved": "✔ Improved",
        "eval_worse": "⚠ Degraded",
        "eval_neutral": "➖ Neutral",
        "kpi_records_a": "RECORDS (DATASET A)",
        "kpi_records_b": "RECORDS (DATASET B)",
        "kpi_ssim": "SPATIAL SIMILARITY (SSIM)",
        "kpi_headline": "KEY KINEMATIC DELTA",
        "long_subject": "Subject (Animal ID):",
        "long_metric": "Longitudinal Metric:",
        "msg_no_data": "No data loaded yet. Please load a MouseAnalyzer output folder or CSV file!",
        "msg_exported": "✅ Successfully exported to:\n{path}",
        "status_ready": "Ready. Load MouseAnalyzer folders or CSV files to begin comparison.",
        "status_loaded": "Loaded: A={na} runs ({sa} subjects) | B={nb} runs ({sb} subjects)",
    },
}


# ==============================================================================
# CANONICAL METRIC DEFINITIONS (42 CSV COLUMNS -> BIOMARKER CATALOG)
# ==============================================================================
# lower_is_better: True if a decrease means motor/behavioral improvement (e.g., fewer faults, lower transit time),
#                  False if an increase means higher locomotor speed, None if purely descriptive.
METRIC_SPECS = [
    ("Teljes_Athaladasi_Ido_mp", "Teljes áthaladási idő (mp)", "Total Transit Time (s)", "s", True),
    ("Netto_Mozgasi_Ido_mp", "Nettó mozgási idő (mp)", "Net Moving Time (s)", "s", True),
    ("Melynyulasok_Szama", "Összes mélynyúlás (db)", "Total Dips (count)", "", True),
    ("Mancs_Labhiba_Db", "Mancs lábhibák (db)", "Total Paw Faults", "", True),
    ("Mellso_Labhiba_Db", "Mellső lábhibák (db)", "Forepaw Faults", "", True),
    ("Hatso_Labhiba_Db", "Hátsó lábhibák (db)", "Hindpaw Faults", "", True),
    ("Enyhe_Megcsuszas_Db", "Enyhe megcsúszás (db)", "Minor Slips (<20px)", "", True),
    ("Mely_Leleses_Db", "Mély leesés (db)", "Deep Falls (>=20px)", "", True),
    ("Orr_Lenezes_Db", "Orr lenézés / exploráció (db)", "Snout Explorations", "", None),
    ("Hatso_Farok_Db", "Farok lelógás (db)", "Tail Dips", "", None),
    ("Megallasok_Szama", "Megállások / lefagyások (db)", "Freezes (count)", "", True),
    ("Megallasok_OsszIdeje_mp", "Megállások összideje (mp)", "Total Freeze Time (s)", "s", True),
    ("Mikro_Megtorpanas_Db", "Mikro-megtorpanások (db)", "Micro-Hesitations (count)", "", True),
    ("Mikro_Megtorpanas_Ido_mp", "Mikro-megtorpanás idő (mp)", "Micro-Hesitation Time (s)", "s", True),
    ("Sebesseg_Ingadozas_CV", "Sebesség ingadozás (CV)", "Velocity CV", "", True),
    ("Mozgas_Darabossag_Jerk", "Mozgás darabosság (Jerk)", "Jerk Score", "", True),
    ("Testtartas_Imbolygas_px", "Testtartás imbolygás (px)", "Postural Sway (px)", "px", True),
    ("Bizonytalansagi_Index_Pct", "Bizonytalansági Index (%)", "Uncertainty Index (%)", "%", True),
    ("Atlagsebesseg_cm_mp", "Átlagsebesség (cm/mp)", "Average Speed (cm/s)", "cm/s", False),
    ("Max_Sebesseg_cm_mp", "Max sebesség (cm/mp)", "Max Speed (cm/s)", "cm/s", False),
    ("Megtett_Ut_cm", "Megtett út (cm)", "Path Length (cm)", "cm", None),
    ("Start_Zona_Ido_mp", "Start zóna idő (mp)", "Start Zone Time (s)", "s", True),
    ("Start_Lenyulas_Db", "Start zóna lábhiba (db)", "Start Zone Dips", "", True),
    ("Start_Megallas_Db", "Start zóna megállás (db)", "Start Zone Freezes", "", True),
    ("Kozep_Zona_Ido_mp", "Közép zóna idő (mp)", "Middle Zone Time (s)", "s", True),
    ("Kozep_Lenyulas_Db", "Közép zóna lábhiba (db)", "Middle Zone Dips", "", True),
    ("Kozep_Megallas_Db", "Közép zóna megállás (db)", "Middle Zone Freezes", "", True),
    ("Cel_Zona_Ido_mp", "Cél zóna idő (mp)", "Goal Zone Time (s)", "s", True),
    ("Cel_Lenyulas_Db", "Cél zóna lábhiba (db)", "Goal Zone Dips", "", True),
    ("Cel_Megallas_Db", "Cél zóna megállás (db)", "Goal Zone Freezes", "", True),
]

METRIC_LOOKUP = {m[0]: m for m in METRIC_SPECS}


# ==============================================================================
# DATA MODELS & AUTO-DISCOVERY LOADER
# ==============================================================================
@dataclass
class RunRecord:
    """Represents a single analyzed run (or subject-level aggregate) with metrics and linked image paths."""
    subject_id: str
    safe_id: str
    video_name: str
    run_num: int
    direction: str
    metrics: Dict[str, float] = field(default_factory=dict)
    raw_row: Dict[str, str] = field(default_factory=dict)
    source_dir: str = ""
    heatmap_path: Optional[str] = None
    faded_heatmap_path: Optional[str] = None
    summary_img_path: Optional[str] = None
    combined_heatmap_path: Optional[str] = None
    combined_faded_heatmap_path: Optional[str] = None
    combined_summary_path: Optional[str] = None
    dip_crop_paths: List[str] = field(default_factory=list)
    is_subject_aggregate: bool = False

    @property
    def display_label(self) -> str:
        if self.is_subject_aggregate:
            return f"ID #{self.subject_id} [AVG ({int(self.metrics.get('_run_count', 1))} runs)] — {self.video_name}"
        return f"ID #{self.subject_id} | Run #{self.run_num} ({self.direction}) — {self.video_name}"

    def get_image_path(self, artifact_key: str) -> Optional[str]:
        if artifact_key == "heatmap":
            return self.heatmap_path or self.combined_heatmap_path or self.faded_heatmap_path
        if artifact_key == "faded_hm":
            return self.faded_heatmap_path or self.combined_faded_heatmap_path or self.heatmap_path
        if artifact_key == "summary":
            return self.summary_img_path or self.combined_summary_path
        if artifact_key == "combined_hm":
            return self.combined_heatmap_path or self.heatmap_path
        return self.heatmap_path


class AnalyzerDatasetLoader:
    """
    Loads and normalizes MouseAnalyzer CSV exports (`Minden_Egyed_Meresi_Adatai.csv` and
    `egyed_{safe_id}_meresi_adatok.csv`) and automatically links per-run and combined
    heatmaps, summary images, and paw-fault crop snapshots.
    """

    @staticmethod
    def parse_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        if isinstance(val, (int, float, np.number)):
            return float(val) if math.isfinite(float(val)) else default
        s = str(val).strip()
        if s.startswith("'"):
            s = s[1:].strip()
        if not s or s.lower() in ("none", "nan", "-"):
            return default
        s = s.replace(",", ".")
        try:
            res = float(s)
            return res if math.isfinite(res) else default
        except ValueError:
            return default

    @staticmethod
    def make_safe_id(subject_id: str) -> str:
        s = str(subject_id).strip()
        if s.startswith("'"):
            s = s[1:].strip()
        safe = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in s)
        return safe or "unknown"

    @classmethod
    def load_from_path(cls, path: str) -> List[RunRecord]:
        """
        Loads RunRecords from a directory (recursively scanning for CSVs & images)
        or directly from a CSV / image file path.
        """
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return []

        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext == ".csv":
                return cls._load_csv_file(path, os.path.dirname(path))
            elif ext in (".jpg", ".jpeg", ".png", ".bmp"):
                return [cls._create_record_from_standalone_image(path)]
            return []

        # Directory scan: prefer individual `egyed_*_meresi_adatok.csv` or `Minden_Egyed_Meresi_Adatai.csv`
        csv_files: List[str] = []
        master_csvs: List[str] = []
        for root_dir, _dirs, files in os.walk(path):
            for fname in sorted(files):
                low = fname.lower()
                full_p = os.path.join(root_dir, fname)
                if low == "minden_egyed_meresi_adatai.csv":
                    master_csvs.append(full_p)
                elif low.endswith("_meresi_adatok.csv") or (low.endswith(".csv") and "delta" not in low):
                    csv_files.append(full_p)

        records: List[RunRecord] = []
        seen_keys = set()

        # First load specific per-subject CSVs (their directory directly contains the images)
        for cpath in csv_files:
            for rec in cls._load_csv_file(cpath, os.path.dirname(cpath), root_search_dir=path):
                key = (rec.subject_id, rec.video_name, rec.run_num)
                if key not in seen_keys:
                    seen_keys.add(key)
                    records.append(rec)

        # Then load master CSVs for any runs not already covered
        for mpath in master_csvs:
            for rec in cls._load_csv_file(mpath, os.path.dirname(mpath), root_search_dir=path):
                key = (rec.subject_id, rec.video_name, rec.run_num)
                if key not in seen_keys:
                    seen_keys.add(key)
                    records.append(rec)

        # If a directory has images (heatmaps/summaries) but no CSVs, synthesize image-backed records
        if not records:
            records = cls._discover_image_only_records(path)

        return records

    @classmethod
    def _load_csv_file(cls, csv_path: str, base_dir: str, root_search_dir: Optional[str] = None) -> List[RunRecord]:
        records: List[RunRecord] = []
        search_root = root_search_dir or base_dir
        try:
            with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
                sample = f.read(4096)
                f.seek(0)
                delimiter = ";" if sample.count(";") >= sample.count(",") else ","
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    if not row:
                        continue
                    clean_row = {str(k).strip(): (str(v).strip() if v is not None else "") for k, v in row.items() if k}
                    subj_raw = clean_row.get("Egyed_ID", "").lstrip("'")
                    vid_raw = clean_row.get("Video_Fajl", "").lstrip("'")
                    if not subj_raw and not vid_raw:
                        continue
                    run_num = int(round(cls.parse_float(clean_row.get("Futas_Sorszam", 1), 1.0)))
                    direction = clean_row.get("Irany", "FORWARD").lstrip("'") or "FORWARD"
                    safe_id = cls.make_safe_id(subj_raw)

                    metrics: Dict[str, float] = {}
                    for m_key, *_ in METRIC_SPECS:
                        if m_key in clean_row:
                            metrics[m_key] = cls.parse_float(clean_row.get(m_key), 0.0)
                    metrics["Skala_px_per_cm"] = cls.parse_float(clean_row.get("Skala_px_per_cm", 10.0), 10.0)

                    rec = RunRecord(
                        subject_id=subj_raw or safe_id,
                        safe_id=safe_id,
                        video_name=vid_raw or os.path.basename(csv_path),
                        run_num=run_num,
                        direction=direction,
                        metrics=metrics,
                        raw_row=clean_row,
                        source_dir=base_dir,
                    )
                    cls._link_artifacts(rec, base_dir, search_root)
                    records.append(rec)
        except OSError as e:
            logger.warning("Failed to load CSV %s: %s", csv_path, e)
        return records

    @classmethod
    def _link_artifacts(cls, rec: RunRecord, base_dir: str, search_root: str):
        """Locates per-run heatmaps, summary frames, combined heatmaps, and dip crops for a RunRecord."""
        sid = rec.safe_id
        rnum = rec.run_num
        candidate_dirs = [base_dir]
        if search_root and os.path.isdir(search_root):
            for r_dir, _d, _f in os.walk(search_root):
                if r_dir not in candidate_dirs:
                    candidate_dirs.append(r_dir)

        hm_name = f"egyed_{sid}_futas_{rnum}_heatmap.jpg"
        faded_hm_name = f"egyed_{sid}_futas_{rnum}_halvany_heatmap.jpg"
        sum_name = f"egyed_{sid}_futas_{rnum}_osszefoglalo.jpg"
        comb_hm_name = f"egyed_{sid}_OSSZESITETT_heatmap.jpg"
        comb_faded_name = f"egyed_{sid}_OSSZESITETT_halvany_heatmap.jpg"
        dip_prefix = f"egyed_{sid}_futas_{rnum}_lenyulas_"
        comb_sum_prefix = f"egyed_{sid}_OSSZESITETT_"

        for cdir in candidate_dirs:
            if not os.path.isdir(cdir):
                continue
            if rec.heatmap_path is None:
                p = os.path.join(cdir, hm_name)
                if os.path.isfile(p):
                    rec.heatmap_path = p
                    rec.source_dir = cdir
            if rec.faded_heatmap_path is None:
                p = os.path.join(cdir, faded_hm_name)
                if os.path.isfile(p):
                    rec.faded_heatmap_path = p
            if rec.summary_img_path is None:
                p = os.path.join(cdir, sum_name)
                if os.path.isfile(p):
                    rec.summary_img_path = p
            if rec.combined_heatmap_path is None:
                p = os.path.join(cdir, comb_hm_name)
                if os.path.isfile(p):
                    rec.combined_heatmap_path = p
            if rec.combined_faded_heatmap_path is None:
                p = os.path.join(cdir, comb_faded_name)
                if os.path.isfile(p):
                    rec.combined_faded_heatmap_path = p

            try:
                for fname in sorted(os.listdir(cdir)):
                    if fname.startswith(dip_prefix) and fname.lower().endswith(".jpg"):
                        full_dip = os.path.join(cdir, fname)
                        if full_dip not in rec.dip_crop_paths:
                            rec.dip_crop_paths.append(full_dip)
                    elif (
                        rec.combined_summary_path is None
                        and fname.startswith(comb_sum_prefix)
                        and fname.lower().endswith("_futas.jpg")
                    ):
                        rec.combined_summary_path = os.path.join(cdir, fname)
            except OSError:
                pass

    @classmethod
    def _create_record_from_standalone_image(cls, img_path: str) -> RunRecord:
        fname = os.path.basename(img_path)
        m = re.match(r"egyed_(.+?)_futas_(\d+)_(.+)\.(jpg|jpeg|png)", fname, re.IGNORECASE)
        if m:
            sid, rnum = m.group(1), int(m.group(2))
        else:
            sid, rnum = os.path.splitext(fname)[0], 1
        rec = RunRecord(
            subject_id=sid,
            safe_id=sid,
            video_name=fname,
            run_num=rnum,
            direction="IMAGE",
            source_dir=os.path.dirname(img_path),
            heatmap_path=img_path,
            summary_img_path=img_path,
        )
        cls._link_artifacts(rec, os.path.dirname(img_path), os.path.dirname(img_path))
        return rec

    @classmethod
    def _discover_image_only_records(cls, folder: str) -> List[RunRecord]:
        records: List[RunRecord] = []
        for root_dir, _dirs, files in os.walk(folder):
            for fname in sorted(files):
                if fname.lower().endswith(("_heatmap.jpg", "_osszefoglalo.jpg")):
                    records.append(cls._create_record_from_standalone_image(os.path.join(root_dir, fname)))
        return records

    @classmethod
    def build_subject_aggregates(cls, records: List[RunRecord]) -> List[RunRecord]:
        """Creates per-subject mean aggregate records across all runs of each subject."""
        by_subj: Dict[str, List[RunRecord]] = {}
        for r in records:
            if not r.is_subject_aggregate:
                by_subj.setdefault(r.subject_id, []).append(r)

        aggregates: List[RunRecord] = []
        for subj_id, r_list in by_subj.items():
            if len(r_list) < 2:
                continue
            first = r_list[0]
            mean_metrics: Dict[str, float] = {"_run_count": float(len(r_list))}
            for m_key, *_ in METRIC_SPECS:
                vals = [x.metrics.get(m_key, 0.0) for x in r_list]
                mean_metrics[m_key] = float(np.mean(vals)) if vals else 0.0

            all_dips: List[str] = []
            for x in r_list:
                all_dips.extend(x.dip_crop_paths)

            agg = RunRecord(
                subject_id=subj_id,
                safe_id=first.safe_id,
                video_name=first.video_name,
                run_num=0,
                direction="COMBINED",
                metrics=mean_metrics,
                source_dir=first.source_dir,
                heatmap_path=first.combined_heatmap_path or first.heatmap_path,
                faded_heatmap_path=first.combined_faded_heatmap_path or first.faded_heatmap_path,
                summary_img_path=first.combined_summary_path or first.summary_img_path,
                combined_heatmap_path=first.combined_heatmap_path,
                combined_faded_heatmap_path=first.combined_faded_heatmap_path,
                combined_summary_path=first.combined_summary_path,
                dip_crop_paths=all_dips,
                is_subject_aggregate=True,
            )
            aggregates.append(agg)
        return aggregates


# ==============================================================================
# STATISTICAL COMPARISON ENGINE (1v1, LONGITUDINAL & COHORT HYPOTHESIS TESTING)
# ==============================================================================
class StatisticalComparator:
    """
    Computes 1-vs-1 kinematic deltas, longitudinal multi-run trend regressions,
    and two-cohort statistical tests (Welch's t-test, Mann-Whitney U, Cohen's d).
    """

    @staticmethod
    def _normal_survival_two_tailed(z: float) -> float:
        """Two-tailed p-value from standard normal Z-score using math.erfc."""
        return float(max(0.0, min(1.0, math.erfc(abs(z) / math.sqrt(2.0)))))

    @classmethod
    def welch_t_test(cls, vals_a: List[float], vals_b: List[float]) -> Tuple[float, float]:
        """Returns (t_stat, p_value) using Welch's two-sample t-test."""
        a = np.asarray(vals_a, dtype=np.float64)
        b = np.asarray(vals_b, dtype=np.float64)
        if a.size < 2 or b.size < 2:
            return 0.0, 1.0
        va = float(np.var(a, ddof=1))
        vb = float(np.var(b, ddof=1))
        se2 = (va / a.size) + (vb / b.size)
        if se2 <= 1e-12:
            return 0.0, 1.0 if abs(float(np.mean(a) - np.mean(b))) <= 1e-9 else 0.0
        t_stat = float((np.mean(b) - np.mean(a)) / math.sqrt(se2))
        try:
            from scipy import stats as sp_stats
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                res = sp_stats.ttest_ind(b, a, equal_var=False)
            p_val = float(res.pvalue)
            if math.isfinite(p_val):
                return t_stat, p_val
        except ImportError:
            pass
        # Welch-Satterthwaite df + Cornish-Fisher normal approximation
        num = se2 ** 2
        den = ((va / a.size) ** 2) / max(1, a.size - 1) + ((vb / b.size) ** 2) / max(1, b.size - 1)
        df = num / den if den > 1e-12 else float(a.size + b.size - 2)
        z_approx = abs(t_stat) * (1.0 - 1.0 / (4.0 * max(1.0, df))) / math.sqrt(
            1.0 + (t_stat ** 2) / (2.0 * max(1.0, df))
        )
        return t_stat, cls._normal_survival_two_tailed(z_approx)

    @classmethod
    def mann_whitney_u(cls, vals_a: List[float], vals_b: List[float]) -> Tuple[float, float]:
        """Returns (u_stat, p_value) for Mann-Whitney U test with tie-corrected normal approximation."""
        a = np.asarray(vals_a, dtype=np.float64)
        b = np.asarray(vals_b, dtype=np.float64)
        n1, n2 = a.size, b.size
        if n1 < 1 or n2 < 1:
            return 0.0, 1.0
        try:
            from scipy import stats as sp_stats
            res = sp_stats.mannwhitneyu(a, b, alternative="two-sided")
            p_val = float(res.pvalue)
            if math.isfinite(p_val):
                return float(res.statistic), p_val
        except (ImportError, ValueError):
            pass

        combined = np.concatenate([a, b])
        n = n1 + n2
        order = np.argsort(combined, kind="mergesort")
        ranks = np.empty(n, dtype=np.float64)
        i = 0
        tie_sum = 0.0
        while i < n:
            j = i
            while j + 1 < n and abs(combined[order[j + 1]] - combined[order[i]]) <= 1e-12:
                j += 1
            avg_rank = 0.5 * (i + j) + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            t_len = j - i + 1
            if t_len > 1:
                tie_sum += float(t_len ** 3 - t_len)
            i = j + 1

        r1 = float(np.sum(ranks[:n1]))
        u1 = r1 - n1 * (n1 + 1) / 2.0
        u2 = float(n1 * n2) - u1
        u_stat = min(u1, u2)
        mu_u = n1 * n2 / 2.0
        tie_corr = tie_sum / (n * (n - 1)) if n > 1 else 0.0
        var_u = (n1 * n2 / 12.0) * max(0.0, (n + 1.0) - tie_corr)
        if var_u <= 1e-12:
            return u_stat, 1.0
        z = (abs(u1 - mu_u) - 0.5) / math.sqrt(var_u)
        return u_stat, cls._normal_survival_two_tailed(max(0.0, z))

    @staticmethod
    def cohens_d(vals_a: List[float], vals_b: List[float]) -> float:
        """Computes pooled Cohen's d effect size (B - A) / s_pooled."""
        a = np.asarray(vals_a, dtype=np.float64)
        b = np.asarray(vals_b, dtype=np.float64)
        if a.size < 2 or b.size < 2:
            return 0.0
        va = float(np.var(a, ddof=1))
        vb = float(np.var(b, ddof=1))
        denom_df = a.size + b.size - 2
        if denom_df <= 0:
            return 0.0
        s_pool = math.sqrt(((a.size - 1) * va + (b.size - 1) * vb) / denom_df)
        if s_pool <= 1e-9:
            return 0.0
        return float((np.mean(b) - np.mean(a)) / s_pool)

    @classmethod
    def compare_1v1(cls, rec_a: RunRecord, rec_b: RunRecord, lang: str = "hu") -> List[Dict[str, Any]]:
        """Generates a structured comparison table between two RunRecords."""
        rows: List[Dict[str, Any]] = []
        tr_d = TRANSLATIONS.get(lang, TRANSLATIONS["hu"])
        for key, lbl_hu, lbl_en, unit, lower_is_better in METRIC_SPECS:
            va = float(rec_a.metrics.get(key, 0.0))
            vb = float(rec_b.metrics.get(key, 0.0))
            delta = vb - va
            if abs(va) > 1e-6:
                pct = (delta / abs(va)) * 100.0
            elif abs(vb) > 1e-6:
                pct = 100.0 if vb > 0 else -100.0
            else:
                pct = 0.0

            if abs(delta) <= 1e-5 or lower_is_better is None:
                status = "neutral"
                eval_txt = tr_d["eval_neutral"]
            else:
                is_better = (delta < 0) if lower_is_better else (delta > 0)
                status = "improved" if is_better else "worse"
                eval_txt = tr_d["eval_improved"] if is_better else tr_d["eval_worse"]

            rows.append({
                "key": key,
                "label": lbl_hu if lang == "hu" else lbl_en,
                "unit": unit,
                "val_a": va,
                "val_b": vb,
                "delta": delta,
                "pct": pct,
                "status": status,
                "eval_text": eval_txt,
            })
        return rows

    @classmethod
    def compare_cohorts(cls, group_a: List[RunRecord], group_b: List[RunRecord], lang: str = "hu") -> List[Dict[str, Any]]:
        """Computes group Mean ± SD, Δ%, Welch t-test p-value, Mann-Whitney p-value, and Cohen's d."""
        rows: List[Dict[str, Any]] = []
        tr_d = TRANSLATIONS.get(lang, TRANSLATIONS["hu"])
        runs_a = [r for r in group_a if not r.is_subject_aggregate] or group_a
        runs_b = [r for r in group_b if not r.is_subject_aggregate] or group_b

        for key, lbl_hu, lbl_en, unit, lower_is_better in METRIC_SPECS:
            vals_a = [float(r.metrics.get(key, 0.0)) for r in runs_a]
            vals_b = [float(r.metrics.get(key, 0.0)) for r in runs_b]
            mean_a = float(np.mean(vals_a)) if vals_a else 0.0
            sd_a = float(np.std(vals_a, ddof=1)) if len(vals_a) > 1 else 0.0
            mean_b = float(np.mean(vals_b)) if vals_b else 0.0
            sd_b = float(np.std(vals_b, ddof=1)) if len(vals_b) > 1 else 0.0

            delta = mean_b - mean_a
            pct = (delta / abs(mean_a)) * 100.0 if abs(mean_a) > 1e-6 else 0.0
            _t, p_t = cls.welch_t_test(vals_a, vals_b)
            _u, p_mw = cls.mann_whitney_u(vals_a, vals_b)
            d_eff = cls.cohens_d(vals_a, vals_b)

            if abs(delta) <= 1e-5 or lower_is_better is None:
                status = "neutral"
                eval_txt = tr_d["eval_neutral"]
            else:
                is_better = (delta < 0) if lower_is_better else (delta > 0)
                status = "improved" if is_better else "worse"
                sig_star = " *" if min(p_t, p_mw) < 0.05 else ""
                eval_txt = (tr_d["eval_improved"] if is_better else tr_d["eval_worse"]) + sig_star

            rows.append({
                "key": key,
                "label": lbl_hu if lang == "hu" else lbl_en,
                "unit": unit,
                "val_a": mean_a,
                "sd_a": sd_a,
                "val_b": mean_b,
                "sd_b": sd_b,
                "delta": delta,
                "pct": pct,
                "p_t": p_t,
                "p_mw": p_mw,
                "cohens_d": d_eff,
                "status": status,
                "eval_text": eval_txt,
            })
        return rows

    @staticmethod
    def compute_longitudinal_trend(records: List[RunRecord], metric_key: str) -> Dict[str, Any]:
        """Computes per-run trajectory and linear regression slope across ordered runs."""
        runs = sorted(
            [r for r in records if not r.is_subject_aggregate],
            key=lambda x: (x.run_num, x.video_name)
        )
        if not runs:
            return {"runs": [], "x": [], "y": [], "slope": 0.0, "intercept": 0.0, "pct_change": 0.0}
        xs = np.arange(1, len(runs) + 1, dtype=np.float64)
        ys = np.array([float(r.metrics.get(metric_key, 0.0)) for r in runs], dtype=np.float64)
        if len(xs) >= 2:
            slope, intercept = np.polyfit(xs, ys, 1)
            pct_change = ((ys[-1] - ys[0]) / abs(ys[0]) * 100.0) if abs(ys[0]) > 1e-6 else 0.0
        else:
            slope, intercept, pct_change = 0.0, float(ys[0]), 0.0
        return {
            "runs": runs,
            "x": xs.tolist(),
            "y": ys.tolist(),
            "slope": float(slope),
            "intercept": float(intercept),
            "pct_change": float(pct_change),
        }


# ==============================================================================
# VISUAL, HEATMAP & SCIENTIFIC CHART RENDERING ENGINE (PURE OPENCV / NUMPY)
# ==============================================================================
class VisualComparisonEngine:
    """
    Performs spatial alignment, SSIM & heatmap dwell-density comparison,
    difference heatmap synthesis, interactive wipe/blend rendering, and
    scientific radar / zone / longitudinal chart rendering.
    """

    @staticmethod
    def make_placeholder(width: int = 960, height: int = 420, title: str = "No Image Available") -> np.ndarray:
        canvas = np.full((height, width, 3), (22, 30, 44), dtype=np.uint8)
        cv2.rectangle(canvas, (12, 12), (width - 12, height - 12), (51, 65, 85), 1)
        cv2.putText(
            canvas, title, (max(24, width // 2 - 160), height // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (148, 163, 184), 2, cv2.LINE_AA
        )
        return canvas

    @staticmethod
    def align_pair(img_a: Optional[np.ndarray], img_b: Optional[np.ndarray], target_size: Tuple[int, int] = (960, 420)) -> Tuple[np.ndarray, np.ndarray]:
        """Normalizes two images to a shared resolution for pixel-wise & spatial comparison."""
        tw, th = target_size
        if img_a is not None and img_b is not None:
            th = max(240, min(720, max(img_a.shape[0], img_b.shape[0])))
            tw = max(480, min(1440, max(img_a.shape[1], img_b.shape[1])))
        elif img_a is not None:
            th, tw = img_a.shape[:2]
        elif img_b is not None:
            th, tw = img_b.shape[:2]

        a_norm = (
            cv2.resize(img_a, (tw, th), interpolation=cv2.INTER_AREA)
            if img_a is not None else VisualComparisonEngine.make_placeholder(tw, th, "Missing Image A")
        )
        b_norm = (
            cv2.resize(img_b, (tw, th), interpolation=cv2.INTER_AREA)
            if img_b is not None else VisualComparisonEngine.make_placeholder(tw, th, "Missing Image B")
        )
        return a_norm, b_norm

    @staticmethod
    def extract_heatmap_intensity(img: np.ndarray) -> np.ndarray:
        """
        Extracts normalized spatial dwell & fault heat intensity [0..1] from a MouseAnalyzer
        heatmap or summary frame by isolating chromatic saturation and warm (Red/Yellow/Magenta) dominance.
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat = hsv[:, :, 1] / 255.0
        val = hsv[:, :, 2] / 255.0
        b = img[:, :, 0].astype(np.float32) / 255.0
        g = img[:, :, 1].astype(np.float32) / 255.0
        r = img[:, :, 2].astype(np.float32) / 255.0
        warmth = np.clip(r - 0.35 * b + 0.25 * g, 0.0, 1.0)
        heat = np.clip(sat * (0.55 * warmth + 0.45 * val), 0.0, 1.0)
        # Mask top header overlay box (y < 76) so text banners don't skew spatial metrics
        if heat.shape[0] > 90:
            heat[:76, :] *= 0.15
        return cv2.GaussianBlur(heat, (15, 15), 0)

    @classmethod
    def compute_spatial_metrics(cls, img_a: Optional[np.ndarray], img_b: Optional[np.ndarray]) -> Dict[str, float]:
        """
        Computes SSIM (Structural Similarity Index), 2D Heatmap Dwell Correlation,
        and Horizontal Center-of-Hesitation Shift (ΔX % of ladder width).
        """
        if img_a is None or img_b is None:
            return {"ssim": 0.0, "dwell_corr": 0.0, "com_shift_pct": 0.0, "mean_abs_diff": 0.0}

        a, b = cls.align_pair(img_a, img_b)
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float64)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float64)

        # Global SSIM with Gaussian window
        c1 = (0.01 * 255.0) ** 2
        c2 = (0.03 * 255.0) ** 2
        mu1 = cv2.GaussianBlur(ga, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(gb, (11, 11), 1.5)
        mu1_sq = mu1 * mu1
        mu2_sq = mu2 * mu2
        mu1_mu2 = mu1 * mu2
        sigma1_sq = cv2.GaussianBlur(ga * ga, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(gb * gb, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(ga * gb, (11, 11), 1.5) - mu1_mu2
        ssim_map = ((2.0 * mu1_mu2 + c1) * (2.0 * sigma12 + c2)) / (
            (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2) + 1e-12
        )
        ssim_val = float(np.clip(np.mean(ssim_map), -1.0, 1.0))

        ha = cls.extract_heatmap_intensity(a)
        hb = cls.extract_heatmap_intensity(b)
        if np.std(ha) > 1e-6 and np.std(hb) > 1e-6:
            corr = float(np.corrcoef(ha.ravel(), hb.ravel())[0, 1])
        else:
            corr = 1.0 if np.allclose(ha, hb) else 0.0

        w = a.shape[1]
        xs = np.arange(w, dtype=np.float32)
        col_a = np.sum(ha, axis=0)
        col_b = np.sum(hb, axis=0)
        com_a = float(np.sum(xs * col_a) / max(1e-6, float(np.sum(col_a))))
        com_b = float(np.sum(xs * col_b) / max(1e-6, float(np.sum(col_b))))
        com_shift_pct = ((com_b - com_a) / float(max(1, w))) * 100.0
        mad = float(np.mean(np.abs(ha - hb)) * 100.0)

        return {
            "ssim": ssim_val,
            "dwell_corr": corr,
            "com_shift_pct": com_shift_pct,
            "mean_abs_diff": mad,
        }

    @classmethod
    def render_side_by_side(cls, img_a: Optional[np.ndarray], img_b: Optional[np.ndarray], label_a: str = "A", label_b: str = "B") -> np.ndarray:
        a, b = cls.align_pair(img_a, img_b)
        h, w = a.shape[:2]
        # Stack vertically if aspect ratio is very wide, else horizontally
        if w / float(max(1, h)) > 1.85:
            sep = np.full((6, w, 3), (6, 182, 212), dtype=np.uint8)
            a_lbl = a.copy()
            b_lbl = b.copy()
            cls._draw_corner_badge(a_lbl, f"[A] {label_a}", (2, 132, 199))
            cls._draw_corner_badge(b_lbl, f"[B] {label_b}", (16, 185, 129))
            return np.vstack([a_lbl, sep, b_lbl])
        else:
            sep = np.full((h, 6, 3), (6, 182, 212), dtype=np.uint8)
            a_lbl = a.copy()
            b_lbl = b.copy()
            cls._draw_corner_badge(a_lbl, f"[A] {label_a}", (2, 132, 199))
            cls._draw_corner_badge(b_lbl, f"[B] {label_b}", (16, 185, 129))
            return np.hstack([a_lbl, sep, b_lbl])

    @classmethod
    def render_wipe_slider(
        cls, img_a: Optional[np.ndarray], img_b: Optional[np.ndarray],
        split_ratio: float = 0.5, label_a: str = "A", label_b: str = "B"
    ) -> np.ndarray:
        a, b = cls.align_pair(img_a, img_b)
        h, w = a.shape[:2]
        split_x = int(np.clip(round(w * split_ratio), 4, w - 4))
        out = b.copy()
        out[:, :split_x] = a[:, :split_x]
        cv2.line(out, (split_x, 0), (split_x, h), (6, 182, 212), 3, cv2.LINE_AA)
        cv2.circle(out, (split_x, h // 2), 14, (15, 23, 42), -1, cv2.LINE_AA)
        cv2.circle(out, (split_x, h // 2), 14, (6, 182, 212), 2, cv2.LINE_AA)
        cv2.putText(out, "<>", (split_x - 10, h // 2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (248, 250, 252), 1, cv2.LINE_AA)
        cls._draw_corner_badge(out, f"< [A] {label_a}", (2, 132, 199), pos="bottom_left")
        cls._draw_corner_badge(out, f"[B] {label_b} >", (16, 185, 129), pos="bottom_right")
        return out

    @classmethod
    def render_onion_blend(
        cls, img_a: Optional[np.ndarray], img_b: Optional[np.ndarray],
        alpha: float = 0.5, label_a: str = "A", label_b: str = "B"
    ) -> np.ndarray:
        a, b = cls.align_pair(img_a, img_b)
        alpha = float(np.clip(alpha, 0.0, 1.0))
        out = cv2.addWeighted(a, 1.0 - alpha, b, alpha, 0)
        cls._draw_corner_badge(
            out, f"Blend: {int((1.0 - alpha) * 100)}% [A: {label_a}] + {int(alpha * 100)}% [B: {label_b}]",
            (20, 184, 166), pos="bottom_left"
        )
        return out

    @classmethod
    def render_difference_heatmap(
        cls, img_a: Optional[np.ndarray], img_b: Optional[np.ndarray],
        label_a: str = "A", label_b: str = "B"
    ) -> np.ndarray:
        """
        Synthesizes a signed diverging difference heatmap (B - A):
        - Cyan/Blue: Decreased dwell/slip intensity in B vs A (Improvement / faster transit)
        - Red/Magenta: Increased dwell/slip intensity in B vs A (More hesitation / slips in B)
        """
        a, b = cls.align_pair(img_a, img_b)
        h, w = a.shape[:2]
        ha = cls.extract_heatmap_intensity(a)
        hb = cls.extract_heatmap_intensity(b)
        diff = hb - ha  # [-1.0 .. +1.0]

        # Dimmed structural background from mean grayscale of A & B
        gray_bg = cv2.cvtColor(cv2.addWeighted(a, 0.5, b, 0.5, 0), cv2.COLOR_BGR2GRAY)
        base_bgr = cv2.cvtColor((gray_bg * 0.42).astype(np.uint8), cv2.COLOR_GRAY2BGR)

        max_abs = max(float(np.percentile(np.abs(diff), 98)), 0.08)
        norm_diff = np.clip(diff / max_abs, -1.0, 1.0)

        overlay = np.zeros_like(base_bgr, dtype=np.float32)
        pos_mask = norm_diff > 0.08
        neg_mask = norm_diff < -0.08

        # Positive (B > A: More hesitation/faults in B) -> Hot Red/Amber (BGR: 30, 60, 255)
        pos_s = norm_diff[pos_mask]
        overlay[pos_mask, 0] = 30.0 * pos_s
        overlay[pos_mask, 1] = 75.0 * pos_s
        overlay[pos_mask, 2] = 255.0 * pos_s

        # Negative (B < A: Less hesitation/faults in B) -> Cool Cyan/Blue (BGR: 255, 210, 20)
        neg_s = -norm_diff[neg_mask]
        overlay[neg_mask, 0] = 255.0 * neg_s
        overlay[neg_mask, 1] = 210.0 * neg_s
        overlay[neg_mask, 2] = 20.0 * neg_s

        alpha_map = np.clip(np.abs(norm_diff) * 0.82, 0.0, 0.85)[..., None]
        out = np.clip(base_bgr.astype(np.float32) * (1.0 - alpha_map) + overlay * alpha_map, 0, 255).astype(np.uint8)

        # Horizontal 1D intensity profile strip at bottom (height 48px)
        strip_h = 48
        strip = np.full((strip_h, w, 3), (15, 23, 42), dtype=np.uint8)
        cv2.line(strip, (0, strip_h // 2), (w, strip_h // 2), (71, 85, 105), 1)
        col_diff = np.mean(norm_diff, axis=0)
        pts = []
        for x_i in range(w):
            y_i = int(np.clip(strip_h // 2 - col_diff[x_i] * (strip_h * 0.42), 3, strip_h - 3))
            pts.append((x_i, y_i))
        for i in range(1, len(pts)):
            col = (40, 80, 250) if col_diff[i] > 0 else (250, 200, 30)
            cv2.line(strip, pts[i - 1], pts[i], col, 2, cv2.LINE_AA)

        spat = cls.compute_spatial_metrics(a, b)
        legend = (
            f"Delta Heatmap (B - A) | SSIM: {spat['ssim']:.3f} | "
            f"Corr: {spat['dwell_corr']:.2f} | CoM Shift: {spat['com_shift_pct']:+.1f}%  "
            f"[Cyan = Less in B | Red = More in B]"
        )
        cls._draw_corner_badge(out, legend, (15, 23, 42), pos="bottom_left")
        return np.vstack([out, strip])

    @classmethod
    def render_dip_gallery(
        cls, rec_a: Optional[RunRecord], rec_b: Optional[RunRecord],
        canvas_w: int = 960, canvas_h: int = 500
    ) -> np.ndarray:
        """Renders a synchronized 2-row Paw Fault / Dip Snapshot Gallery comparing A and B."""
        canvas = np.full((canvas_h, canvas_w, 3), (15, 23, 42), dtype=np.uint8)
        paths_a = rec_a.dip_crop_paths if rec_a else []
        paths_b = rec_b.dip_crop_paths if rec_b else []

        lbl_a = f"[A] {rec_a.display_label} ({len(paths_a)} fault snapshots)" if rec_a else "[A] None"
        lbl_b = f"[B] {rec_b.display_label} ({len(paths_b)} fault snapshots)" if rec_b else "[B] None"

        row_h = (canvas_h - 70) // 2
        cls._render_strip_row(canvas, paths_a, 12, 34, canvas_w - 24, row_h, lbl_a, (2, 132, 199))
        cls._render_strip_row(canvas, paths_b, 12, 54 + row_h, canvas_w - 24, row_h, lbl_b, (16, 185, 129))
        return canvas

    @classmethod
    def _render_strip_row(
        cls, canvas: np.ndarray, paths: List[str],
        x0: int, y0: int, w: int, h: int, title: str, accent: Tuple[int, int, int]
    ):
        cv2.putText(canvas, title[:95], (x0, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, accent, 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (51, 65, 85), 1)
        if not paths:
            cv2.putText(
                canvas, "0 paw-fault snapshots recorded (Clean Run / No crops saved)",
                (x0 + 24, y0 + h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (148, 163, 184), 1, cv2.LINE_AA
            )
            return

        max_thumbs = min(4, len(paths))
        pad = 8
        thumb_w = (w - pad * (max_thumbs + 1)) // max_thumbs
        thumb_h = h - 2 * pad
        for idx in range(max_thumbs):
            img = read_image_unicode(paths[idx])
            tx = x0 + pad + idx * (thumb_w + pad)
            ty = y0 + pad
            if img is not None:
                resized = cv2.resize(img, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
                canvas[ty:ty + thumb_h, tx:tx + thumb_w] = resized
                cv2.rectangle(canvas, (tx, ty), (tx + thumb_w, ty + thumb_h), accent, 1)
                cv2.putText(
                    canvas, f"Dip #{idx + 1}", (tx + 6, ty + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA
                )

    @classmethod
    def render_radar_and_zones_chart(
        cls, metrics_a: Dict[str, float], metrics_b: Dict[str, float],
        label_a: str = "A", label_b: str = "B",
        width: int = 960, height: int = 460
    ) -> np.ndarray:
        """
        Renders a two-panel scientific chart:
        Left: 6-Axis Normalized Biomarker Radar Chart (Transit Time, Paw Faults, Uncertainty %,
              Velocity CV, Postural Sway, Inverse Speed).
        Right: 3-Zone (Start / Middle / Goal) Dwell Time & Faults Bar Comparison.
        """
        canvas = np.full((height, width, 3), (15, 23, 42), dtype=np.uint8)
        mid_x = width // 2
        cv2.line(canvas, (mid_x, 16), (mid_x, height - 16), (51, 65, 85), 1)

        # ── LEFT PANEL: 6-Axis Biomarker Radar ──────────────────────────────
        cv2.putText(
            canvas, "6-Axis Kinematic & Behavioral Radar",
            (24, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (248, 250, 252), 1, cv2.LINE_AA
        )
        radar_axes = [
            ("Transit (s)", "Teljes_Athaladasi_Ido_mp", 15.0),
            ("Paw Faults", "Mancs_Labhiba_Db", 6.0),
            ("Uncertainty %", "Bizonytalansagi_Index_Pct", 100.0),
            ("Vel CV", "Sebesseg_Ingadozas_CV", 1.2),
            ("Sway (px)", "Testtartas_Imbolygas_px", 12.0),
            ("Speed (cm/s)", "Atlagsebesseg_cm_mp", 35.0),
        ]
        cx, cy = mid_x // 2, height // 2 + 18
        radius = min(mid_x // 2 - 75, height // 2 - 65)
        n_ax = len(radar_axes)

        # Concentric web rings
        for ring in (0.25, 0.50, 0.75, 1.0):
            pts_ring = []
            for i in range(n_ax):
                ang = -math.pi / 2.0 + i * (2.0 * math.pi / n_ax)
                pts_ring.append((int(cx + radius * ring * math.cos(ang)), int(cy + radius * ring * math.sin(ang))))
            cv2.polylines(canvas, [np.array(pts_ring, dtype=np.int32)], True, (40, 52, 70), 1, cv2.LINE_AA)

        pts_a, pts_b = [], []
        for i, (ax_lbl, m_key, ref_max) in enumerate(radar_axes):
            ang = -math.pi / 2.0 + i * (2.0 * math.pi / n_ax)
            ex = int(cx + radius * math.cos(ang))
            ey = int(cy + radius * math.sin(ang))
            cv2.line(canvas, (cx, cy), (ex, ey), (51, 65, 85), 1, cv2.LINE_AA)

            va = float(metrics_a.get(m_key, 0.0))
            vb = float(metrics_b.get(m_key, 0.0))
            scale = max(ref_max, va * 1.15, vb * 1.15, 1e-3)
            na = float(np.clip(va / scale, 0.06, 1.0))
            nb = float(np.clip(vb / scale, 0.06, 1.0))
            pts_a.append((int(cx + radius * na * math.cos(ang)), int(cy + radius * na * math.sin(ang))))
            pts_b.append((int(cx + radius * nb * math.cos(ang)), int(cy + radius * nb * math.sin(ang))))

            lx = int(cx + (radius + 36) * math.cos(ang)) - 34
            ly = int(cy + (radius + 22) * math.sin(ang)) + 4
            cv2.putText(canvas, ax_lbl, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (148, 163, 184), 1, cv2.LINE_AA)

        overlay = canvas.copy()
        cv2.fillPoly(overlay, [np.array(pts_a, dtype=np.int32)], (212, 140, 6))
        canvas = cv2.addWeighted(canvas, 0.78, overlay, 0.22, 0)
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [np.array(pts_b, dtype=np.int32)], (129, 185, 16))
        canvas = cv2.addWeighted(canvas, 0.78, overlay, 0.22, 0)

        cv2.polylines(canvas, [np.array(pts_a, dtype=np.int32)], True, (240, 175, 10), 2, cv2.LINE_AA)
        cv2.polylines(canvas, [np.array(pts_b, dtype=np.int32)], True, (16, 215, 140), 2, cv2.LINE_AA)
        for p in pts_a:
            cv2.circle(canvas, p, 4, (240, 175, 10), -1, cv2.LINE_AA)
        for p in pts_b:
            cv2.circle(canvas, p, 4, (16, 215, 140), -1, cv2.LINE_AA)

        # Legend at bottom-left
        cv2.rectangle(canvas, (24, height - 34), (40, height - 20), (240, 175, 10), -1)
        cv2.putText(canvas, f"A: {label_a[:26]}", (46, height - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (248, 250, 252), 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (240, height - 34), (256, height - 20), (16, 215, 140), -1)
        cv2.putText(canvas, f"B: {label_b[:26]}", (262, height - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (248, 250, 252), 1, cv2.LINE_AA)

        # ── RIGHT PANEL: 3-Zone Spatial Breakdown & Limb Fault Split ────────
        rx0 = mid_x + 28
        cv2.putText(
            canvas, "Spatial Zone Times (s) & Limb Fault Breakdown",
            (rx0, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (248, 250, 252), 1, cv2.LINE_AA
        )
        bars = [
            ("Start (s)", "Start_Zona_Ido_mp"),
            ("Mid (s)", "Kozep_Zona_Ido_mp"),
            ("Goal (s)", "Cel_Zona_Ido_mp"),
            ("Forepaw", "Mellso_Labhiba_Db"),
            ("Hindpaw", "Hatso_Labhiba_Db"),
            ("Freezes", "Megallasok_Szama"),
        ]
        chart_top = 68
        chart_bot = height - 60
        chart_h = chart_bot - chart_top
        cv2.line(canvas, (rx0, chart_bot), (width - 24, chart_bot), (100, 116, 139), 1)

        vals_all = [max(float(metrics_a.get(k, 0.0)), float(metrics_b.get(k, 0.0))) for _, k in bars]
        max_bar = max(max(vals_all) * 1.2, 1.0)
        slot_w = (width - rx0 - 30) // len(bars)
        bar_w = max(12, slot_w // 3)

        for idx, (b_lbl, b_key) in enumerate(bars):
            va = float(metrics_a.get(b_key, 0.0))
            vb = float(metrics_b.get(b_key, 0.0))
            ha_px = int(round((va / max_bar) * chart_h))
            hb_px = int(round((vb / max_bar) * chart_h))
            bx = rx0 + idx * slot_w + 8

            # Bar A (Cyan-Blue)
            cv2.rectangle(canvas, (bx, chart_bot - ha_px), (bx + bar_w, chart_bot), (240, 175, 10), -1)
            cv2.putText(canvas, f"{va:.1f}", (bx - 2, max(chart_top - 4, chart_bot - ha_px - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (240, 175, 10), 1, cv2.LINE_AA)

            # Bar B (Emerald)
            bx_b = bx + bar_w + 4
            cv2.rectangle(canvas, (bx_b, chart_bot - hb_px), (bx_b + bar_w, chart_bot), (16, 215, 140), -1)
            cv2.putText(canvas, f"{vb:.1f}", (bx_b - 2, max(chart_top - 4, chart_bot - hb_px - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (16, 215, 140), 1, cv2.LINE_AA)

            cv2.putText(canvas, b_lbl, (bx - 4, chart_bot + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (148, 163, 184), 1, cv2.LINE_AA)

        return canvas

    @classmethod
    def render_longitudinal_chart(
        cls, records: List[RunRecord], metric_key: str,
        width: int = 960, height: int = 440, lang: str = "hu"
    ) -> np.ndarray:
        """Renders a multi-run longitudinal progression curve with linear trendline & heat thumbnails."""
        canvas = np.full((height, width, 3), (15, 23, 42), dtype=np.uint8)
        trend = StatisticalComparator.compute_longitudinal_trend(records, metric_key)
        runs = trend["runs"]
        if not runs:
            return cls.make_placeholder(width, height, "No Longitudinal Runs Found")

        spec = METRIC_LOOKUP.get(metric_key, (metric_key, metric_key, metric_key, "", True))
        m_title = spec[1] if lang == "hu" else spec[2]
        subj = runs[0].subject_id

        header = (
            f"ID #{subj} Longitudinal Progression — {m_title} | "
            f"Slope: {trend['slope']:+.2f}/run ({trend['pct_change']:+.1f}% First->Last)"
        )
        cv2.putText(canvas, header, (24, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (248, 250, 252), 1, cv2.LINE_AA)

        pad_l, pad_r, pad_t, pad_b = 68, 40, 62, 130
        cw = width - pad_l - pad_r
        ch = height - pad_t - pad_b
        cv2.rectangle(canvas, (pad_l, pad_t), (pad_l + cw, pad_t + ch), (51, 65, 85), 1)

        ys = trend["y"]
        y_min = min(0.0, min(ys))
        y_max = max(max(ys) * 1.2, y_min + 1.0)

        n = len(runs)
        pts = []
        for i, val in enumerate(ys):
            px = pad_l + int(round((i / float(max(1, n - 1))) * cw)) if n > 1 else pad_l + cw // 2
            py = pad_t + ch - int(round(((val - y_min) / (y_max - y_min)) * ch))
            pts.append((px, py))

        # Linear regression dashed line
        if n >= 2:
            y_fit_0 = trend["slope"] * 1.0 + trend["intercept"]
            y_fit_n = trend["slope"] * float(n) + trend["intercept"]
            py0 = int(np.clip(pad_t + ch - round(((y_fit_0 - y_min) / (y_max - y_min)) * ch), pad_t, pad_t + ch))
            pyn = int(np.clip(pad_t + ch - round(((y_fit_n - y_min) / (y_max - y_min)) * ch), pad_t, pad_t + ch))
            cv2.line(canvas, (pts[0][0], py0), (pts[-1][0], pyn), (245, 158, 11), 2, cv2.LINE_AA)

        for i in range(1, len(pts)):
            cv2.line(canvas, pts[i - 1], pts[i], (6, 182, 212), 3, cv2.LINE_AA)

        thumb_w = min(140, max(60, (cw - 16) // max(1, n) - 8))
        thumb_h = 56
        for i, (px, py) in enumerate(pts):
            cv2.circle(canvas, (px, py), 6, (16, 185, 129), -1, cv2.LINE_AA)
            cv2.putText(
                canvas, f"{ys[i]:.2f}", (px - 16, max(pad_t + 14, py - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (248, 250, 252), 1, cv2.LINE_AA
            )
            cv2.putText(
                canvas, f"Run #{runs[i].run_num}", (px - 24, pad_t + ch + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA
            )
            hm_p = runs[i].get_image_path("heatmap")
            if hm_p:
                im = read_image_unicode(hm_p)
                if im is not None:
                    th_im = cv2.resize(im, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
                    tx = int(np.clip(px - thumb_w // 2, 12, width - thumb_w - 12))
                    ty = pad_t + ch + 30
                    if ty + thumb_h < height - 4:
                        canvas[ty:ty + thumb_h, tx:tx + thumb_w] = th_im
                        cv2.rectangle(canvas, (tx, ty), (tx + thumb_w, ty + thumb_h), (6, 182, 212), 1)

        return canvas

    @staticmethod
    def _draw_corner_badge(img: np.ndarray, text: str, bg_bgr: Tuple[int, int, int], pos: str = "bottom_left"):
        h, w = img.shape[:2]
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        pad_x, pad_y = 10, 7
        bw = tw + 2 * pad_x
        bh = th + 2 * pad_y
        x1 = 12 if "left" in pos else max(12, w - bw - 12)
        y1 = h - bh - 12 if "bottom" in pos else 12
        cv2.rectangle(img, (x1, y1), (min(w - 4, x1 + bw), min(h - 4, y1 + bh)), bg_bgr, -1)
        cv2.rectangle(img, (x1, y1), (min(w - 4, x1 + bw), min(h - 4, y1 + bh)), (248, 250, 252), 1)
        cv2.putText(
            img, text, (x1 + pad_x, y1 + bh - pad_y - 1),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA
        )


# ==============================================================================
# PUBLICATION REPORT & COMPOSITE EXPORT ENGINE (PNG/JPG, CSV, HTML/PDF)
# ==============================================================================
class ReportExporter:
    """
    Exports high-resolution composite comparison images, formula-sanitized Delta CSVs,
    and self-contained HTML/PDF visual reports with embedded base64 charts and heatmaps.
    """

    @staticmethod
    def _encode_base64_jpg(img: Optional[np.ndarray]) -> str:
        if img is None:
            return ""
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")

    @classmethod
    def build_composite_summary_image(
        cls,
        visual_top: np.ndarray,
        diff_hm: np.ndarray,
        radar_chart: np.ndarray,
        rows: List[Dict[str, Any]],
        title_a: str,
        title_b: str,
    ) -> np.ndarray:
        """Combines the main visual comparison, ΔHeatmap, Radar/Zone chart, and KPI delta table into one high-res figure."""
        target_w = 1280
        banner = np.full((64, target_w, 3), (11, 15, 23), dtype=np.uint8)
        cv2.putText(
            banner, f"MOUSEANALYZER COMPARATOR PRO — [A] {title_a[:42]}  vs  [B] {title_b[:42]}",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (248, 250, 252), 2, cv2.LINE_AA
        )

        def _fit_w(im: np.ndarray, w: int) -> np.ndarray:
            h_new = max(120, int(round(im.shape[0] * (w / float(max(1, im.shape[1]))))))
            return cv2.resize(im, (w, h_new), interpolation=cv2.INTER_AREA)

        v_top = _fit_w(visual_top, target_w)
        d_hm = _fit_w(diff_hm, target_w // 2)
        r_ch = cv2.resize(radar_chart, (target_w - d_hm.shape[1], d_hm.shape[0]), interpolation=cv2.INTER_AREA)
        mid_row = np.hstack([d_hm, r_ch])

        # Render compact KPI summary table at bottom
        key_rows = [r for r in rows if r["key"] in (
            "Teljes_Athaladasi_Ido_mp", "Netto_Mozgasi_Ido_mp", "Mancs_Labhiba_Db",
            "Mellso_Labhiba_Db", "Hatso_Labhiba_Db", "Bizonytalansagi_Index_Pct",
            "Atlagsebesseg_cm_mp", "Sebesseg_Ingadozas_CV", "Testtartas_Imbolygas_px"
        )] or rows[:9]

        row_h = 28
        tbl_h = 46 + len(key_rows) * row_h
        tbl = np.full((tbl_h, target_w, 3), (19, 27, 38), dtype=np.uint8)
        cv2.rectangle(tbl, (0, 0), (target_w - 1, tbl_h - 1), (51, 65, 85), 1)
        headers = [("Metric", 24), ("Value A", 460), ("Value B", 640), ("Delta", 820), ("Change %", 980), ("Status", 1120)]
        for h_txt, hx in headers:
            cv2.putText(tbl, h_txt, (hx, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (6, 182, 212), 1, cv2.LINE_AA)
        cv2.line(tbl, (16, 34), (target_w - 16, 34), (51, 65, 85), 1)

        for idx, r in enumerate(key_rows):
            y = 56 + idx * row_h
            col_stat = (16, 185, 129) if r["status"] == "improved" else ((68, 68, 239) if r["status"] == "worse" else (148, 163, 184))
            cv2.putText(tbl, str(r["label"])[:38], (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (248, 250, 252), 1, cv2.LINE_AA)
            cv2.putText(tbl, f"{r['val_a']:.2f}", (460, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (248, 250, 252), 1, cv2.LINE_AA)
            cv2.putText(tbl, f"{r['val_b']:.2f}", (640, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (248, 250, 252), 1, cv2.LINE_AA)
            cv2.putText(tbl, f"{r['delta']:+.2f}", (820, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, col_stat, 1, cv2.LINE_AA)
            cv2.putText(tbl, f"{r['pct']:+.1f}%", (980, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, col_stat, 1, cv2.LINE_AA)
            st_ascii = "IMPROVED" if r["status"] == "improved" else ("DEGRADED" if r["status"] == "worse" else "NEUTRAL")
            cv2.putText(tbl, st_ascii, (1120, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col_stat, 1, cv2.LINE_AA)

        return np.vstack([banner, v_top, mid_row, tbl])

    @classmethod
    def export_csv(cls, path: str, rows: List[Dict[str, Any]], is_cohort: bool = False) -> bool:
        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                if is_cohort:
                    writer.writerow([
                        "Metric_Key", "Label", "Unit", "Mean_A", "SD_A", "Mean_B", "SD_B",
                        "Delta", "Pct_Change", "Welch_p", "MannWhitney_p", "Cohens_d", "Assessment"
                    ])
                    for r in rows:
                        writer.writerow([
                            sanitize_csv_cell(r["key"]),
                            sanitize_csv_cell(r["label"]),
                            sanitize_csv_cell(r.get("unit", "")),
                            f"{r['val_a']:.4f}",
                            f"{r.get('sd_a', 0.0):.4f}",
                            f"{r['val_b']:.4f}",
                            f"{r.get('sd_b', 0.0):.4f}",
                            f"{r['delta']:+.4f}",
                            f"{r['pct']:+.2f}",
                            f"{r.get('p_t', 1.0):.5f}",
                            f"{r.get('p_mw', 1.0):.5f}",
                            f"{r.get('cohens_d', 0.0):+.3f}",
                            sanitize_csv_cell(r["eval_text"]),
                        ])
                else:
                    writer.writerow(["Metric_Key", "Label", "Unit", "Value_A", "Value_B", "Delta", "Pct_Change", "Assessment"])
                    for r in rows:
                        writer.writerow([
                            sanitize_csv_cell(r["key"]),
                            sanitize_csv_cell(r["label"]),
                            sanitize_csv_cell(r.get("unit", "")),
                            f"{r['val_a']:.4f}",
                            f"{r['val_b']:.4f}",
                            f"{r['delta']:+.4f}",
                            f"{r['pct']:+.2f}",
                            sanitize_csv_cell(r["eval_text"]),
                        ])
            return True
        except OSError as e:
            logger.error("Failed to export CSV %s: %s", path, e)
            return False

    @classmethod
    def export_html_report(
        cls,
        path: str,
        title_a: str,
        title_b: str,
        rows: List[Dict[str, Any]],
        spatial_metrics: Dict[str, float],
        sbs_img: Optional[np.ndarray],
        diff_img: Optional[np.ndarray],
        radar_img: Optional[np.ndarray],
        is_cohort: bool = False,
    ) -> bool:
        """Generates a self-contained HTML5 report (printable to PDF) with embedded base64 visuals and tables."""
        try:
            b64_sbs = cls._encode_base64_jpg(sbs_img)
            b64_diff = cls._encode_base64_jpg(diff_img)
            b64_radar = cls._encode_base64_jpg(radar_img)

            tr_rows_html = []
            for r in rows:
                cls_badge = (
                    "color:#10B981;font-weight:700;" if r["status"] == "improved"
                    else ("color:#EF4444;font-weight:700;" if r["status"] == "worse" else "color:#94A3B8;")
                )
                if is_cohort:
                    val_a_s = f"{r['val_a']:.2f} &plusmn; {r.get('sd_a', 0.0):.2f}"
                    val_b_s = f"{r['val_b']:.2f} &plusmn; {r.get('sd_b', 0.0):.2f}"
                    extra_cols = f"<td>{r.get('p_t', 1.0):.4f} / {r.get('p_mw', 1.0):.4f}</td><td>{r.get('cohens_d', 0.0):+.2f}</td>"
                else:
                    val_a_s = f"{r['val_a']:.2f}"
                    val_b_s = f"{r['val_b']:.2f}"
                    extra_cols = ""

                tr_rows_html.append(
                    f"<tr>"
                    f"<td><strong>{r['label']}</strong></td>"
                    f"<td>{val_a_s}</td>"
                    f"<td>{val_b_s}</td>"
                    f"<td style='{cls_badge}'>{r['delta']:+.2f}</td>"
                    f"<td style='{cls_badge}'>{r['pct']:+.1f}%</td>"
                    f"{extra_cols}"
                    f"<td style='{cls_badge}'>{r['eval_text']}</td>"
                    f"</tr>"
                )

            extra_headers = "<th>p-value (Welch / MW-U)</th><th>Cohen's d</th>" if is_cohort else ""
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>MouseAnalyzer Comparison Report — {title_a} vs {title_b}</title>
<style>
  body {{ background:#0B0F17; color:#F8FAFC; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:24px; }}
  .card {{ background:#131B26; border:1px solid #334155; border-radius:8px; padding:18px; margin-bottom:20px; }}
  h1 {{ margin:0 0 6px 0; font-size:22px; color:#F8FAFC; }}
  h2 {{ margin:0 0 12px 0; font-size:16px; color:#06B6D4; border-bottom:1px solid #334155; padding-bottom:6px; }}
  .meta {{ color:#94A3B8; font-size:13px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  img {{ width:100%; border-radius:6px; border:1px solid #334155; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid #1E293B; text-align:left; }}
  th {{ background:#1E293B; color:#06B6D4; }}
  @media print {{ body {{ background:#FFFFFF; color:#0F172A; }} .card {{ background:#FFFFFF; border-color:#CBD5E1; }} th {{ background:#F1F5F9; color:#0F172A; }} }}
</style>
</head>
<body>
  <div class="card">
    <h1>🐁 MouseAnalyzer PRO — Scientific Comparison Report</h1>
    <div class="meta"><strong>[A] Baseline / Control:</strong> {title_a} &nbsp;|&nbsp; <strong>[B] Target / Treated:</strong> {title_b}</div>
    <div class="meta" style="margin-top:4px;">
      Spatial SSIM: <strong>{spatial_metrics.get('ssim', 0.0):.3f}</strong> &nbsp;|&nbsp;
      Heatmap Dwell Correlation: <strong>{spatial_metrics.get('dwell_corr', 0.0):.2f}</strong> &nbsp;|&nbsp;
      Center-of-Hesitation Shift: <strong>{spatial_metrics.get('com_shift_pct', 0.0):+.1f}%</strong>
    </div>
  </div>
  <div class="card">
    <h2>1. Visual & Trajectory Heatmap Comparison</h2>
    {f'<img src="data:image/jpeg;base64,{b64_sbs}" alt="Side by Side"/>' if b64_sbs else ''}
  </div>
  <div class="grid2">
    <div class="card">
      <h2>2. Signed Difference Heatmap (&Delta;Heatmap: B &minus; A)</h2>
      {f'<img src="data:image/jpeg;base64,{b64_diff}" alt="Difference Heatmap"/>' if b64_diff else ''}
    </div>
    <div class="card">
      <h2>3. 6-Axis Biomarker Radar &amp; Spatial Zones</h2>
      {f'<img src="data:image/jpeg;base64,{b64_radar}" alt="Radar Chart"/>' if b64_radar else ''}
    </div>
  </div>
  <div class="card">
    <h2>4. Complete Kinematic &amp; Behavioral Delta Table</h2>
    <table>
      <thead>
        <tr><th>Metric</th><th>Value A</th><th>Value B</th><th>Delta (&Delta;)</th><th>Change (%)</th>{extra_headers}<th>Assessment</th></tr>
      </thead>
      <tbody>
        {''.join(tr_rows_html)}
      </tbody>
    </table>
  </div>
</body>
</html>"""
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, mode="w", encoding="utf-8") as f:
                f.write(html)
            return True
        except OSError as e:
            logger.error("Failed to export HTML report %s: %s", path, e)
            return False


# ==============================================================================
# MAIN WORKSTATION GUI (MOUSECOMPARATOR PRO)
# ==============================================================================
class MouseComparatorApp:
    PALETTE = {
        "bg_main": "#0B0F17",
        "bg_card": "#131B26",
        "bg_panel": "#1E293B",
        "border": "#334155",
        "text_main": "#F8FAFC",
        "text_muted": "#94A3B8",
        "blue": "#0284C7",
        "blue_hover": "#0369A1",
        "cyan": "#06B6D4",
        "emerald": "#10B981",
        "emerald_hover": "#059669",
        "emerald_soft": "#14332B",
        "teal": "#14B8A6",
        "teal_hover": "#0D9488",
        "danger": "#EF4444",
        "amber": "#F59E0B",
    }

    def __init__(self, root: tk.Tk, init_path_a: Optional[str] = None, init_path_b: Optional[str] = None):
        self.root = root
        self.lang = "hu"
        self.root.title(f"{APP_NAME} v{APP_VERSION} — Scientific Comparison Workstation")
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            init_w = min(1360, max(880, sw - 60))
            init_h = min(860, max(620, sh - 80))
            self.root.geometry(f"{init_w}x{init_h}")
        except tk.TclError:
            self.root.geometry("1320x840")
        self.root.minsize(760, 560)
        self.root.configure(bg=self.PALETTE["bg_main"])
        apply_window_icon(self.root)

        self.records_a: List[RunRecord] = []
        self.records_b: List[RunRecord] = []
        self.current_mode = tk.StringVar(value="1v1")       # "1v1", "long", "cohort"
        self.current_artifact = tk.StringVar(value="heatmap")
        self.current_view = tk.StringVar(value="wipe")      # "sbs", "wipe", "diff", "blend", "radar"
        self.slider_pct = tk.DoubleVar(value=50.0)
        self.long_subject_var = tk.StringVar(value="")
        self.long_metric_var = tk.StringVar(value="Mancs_Labhiba_Db")

        self._cached_visual_bgr: Optional[np.ndarray] = None
        self._photo_ref: Optional[tk.PhotoImage] = None
        self._current_rows: List[Dict[str, Any]] = []
        self._current_spatial: Dict[str, float] = {"ssim": 0.0, "dwell_corr": 0.0, "com_shift_pct": 0.0}

        self._setup_styles()
        self._build_ui()

        # Auto-load default workspace results if available
        if init_path_a and os.path.exists(init_path_a):
            self.load_dataset(init_path_a, slot="A")
        else:
            default_dir = os.path.join(os.path.expanduser("~"), "Documents", "MouseAnalyzer_Results")
            if os.path.isdir(default_dir):
                self.load_dataset(default_dir, slot="A")

        if init_path_b and os.path.exists(init_path_b):
            self.load_dataset(init_path_b, slot="B")

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["hu"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.ui_font = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"
        self.mono_font = "Menlo" if sys.platform == "darwin" else "Consolas"
        P = self.PALETTE

        style.configure("TFrame", background=P["bg_main"])
        style.configure("Card.TFrame", background=P["bg_card"])
        style.configure("TLabel", background=P["bg_card"], foreground=P["text_main"], font=(self.ui_font, 9))
        style.configure(
            "Treeview",
            background="#0E141E",
            foreground=P["text_main"],
            rowheight=26,
            fieldbackground="#0E141E",
            borderwidth=0,
            font=(self.ui_font, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=P["bg_panel"],
            foreground=P["text_main"],
            relief="flat",
            padding=(8, 5),
            font=(self.ui_font, 9, "bold"),
        )
        style.map("Treeview", background=[("selected", P["emerald_soft"])], foreground=[("selected", "#A7F3D0")])

        btn_specs = {
            "Emerald.TButton": (P["emerald"], P["emerald_hover"], "#FFFFFF", (self.ui_font, 9, "bold")),
            "Teal.TButton": (P["teal"], P["teal_hover"], "#FFFFFF", (self.ui_font, 9, "bold")),
            "Primary.TButton": (P["blue"], P["blue_hover"], "#FFFFFF", (self.ui_font, 9, "bold")),
            "Ghost.TButton": (P["bg_panel"], P["border"], P["text_main"], (self.ui_font, 9)),
        }
        for s_name, (bg_col, active_col, fg_col, fnt) in btn_specs.items():
            style.configure(
                s_name, background=bg_col, foreground=fg_col, font=fnt,
                padding=(10, 5), borderwidth=1, bordercolor=P["border"], relief="flat"
            )
            style.map(s_name, background=[("active", active_col)])

    def _build_ui(self):
        P = self.PALETTE

        # ── 1. HEADER BAR ────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=P["bg_card"], padx=16, pady=10, highlightthickness=1, highlightbackground=P["border"])
        header.pack(side="top", fill="x")

        h_right = tk.Frame(header, bg=P["bg_card"])
        h_right.pack(side="right")

        self.btn_load_a = ttk.Button(h_right, text=self.tr("btn_load_dir_a"), command=lambda: self.prompt_load("A"), style="Primary.TButton")
        self.btn_load_a.pack(side="left", padx=4)

        self.btn_load_b = ttk.Button(h_right, text=self.tr("btn_load_dir_b"), command=lambda: self.prompt_load("B"), style="Teal.TButton")
        self.btn_load_b.pack(side="left", padx=4)

        self.btn_exp_img = ttk.Button(h_right, text=self.tr("btn_export_img"), command=self.action_export_image, style="Ghost.TButton")
        self.btn_exp_img.pack(side="left", padx=4)

        self.btn_exp_csv = ttk.Button(h_right, text=self.tr("btn_export_csv"), command=self.action_export_csv, style="Ghost.TButton")
        self.btn_exp_csv.pack(side="left", padx=4)

        self.btn_exp_html = ttk.Button(h_right, text=self.tr("btn_export_html"), command=self.action_export_html, style="Emerald.TButton")
        self.btn_exp_html.pack(side="left", padx=4)

        self.btn_lang = ttk.Button(h_right, text="HU", width=4, command=self.toggle_language, style="Ghost.TButton")
        self.btn_lang.pack(side="left", padx=(6, 0))

        h_left = tk.Frame(header, bg=P["bg_card"])
        h_left.pack(side="left", fill="x", expand=True)
        tk.Label(h_left, text="MOUSEANALYZER COMPARATOR PRO", bg=P["bg_card"], fg=P["text_main"], font=(self.ui_font, 12, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(h_left, text=f"v{APP_VERSION}", bg=P["bg_panel"], fg=P["cyan"], font=(self.mono_font, 8, "bold"), padx=6, pady=1).pack(side="left", padx=(0, 10))
        self.lbl_sub = tk.Label(h_left, text=self.tr("subtitle"), bg=P["bg_card"], fg=P["text_muted"], font=(self.ui_font, 9))
        self.lbl_sub.pack(side="left")

        # ── 2. KPI TELEMETRY STRIP ───────────────────────────────────────────
        kpi_strip = tk.Frame(self.root, bg=P["bg_main"], padx=14, pady=6)
        kpi_strip.pack(side="top", fill="x")
        self.kpi_vars = {
            "rec_a": tk.StringVar(value="0"),
            "rec_b": tk.StringVar(value="0"),
            "ssim": tk.StringVar(value="-"),
            "headline": tk.StringVar(value="-"),
        }
        self.kpi_lbl_titles = {}
        kpi_specs = [
            ("rec_a", "kpi_records_a", P["blue"]),
            ("rec_b", "kpi_records_b", P["emerald"]),
            ("ssim", "kpi_ssim", P["cyan"]),
            ("headline", "kpi_headline", P["amber"]),
        ]
        for idx, (k_id, t_key, col) in enumerate(kpi_specs):
            kpi_strip.grid_columnconfigure(idx, weight=1, uniform="kpi")
            card = tk.Frame(kpi_strip, bg=P["bg_card"], padx=12, pady=6, highlightthickness=1, highlightbackground=P["border"])
            card.grid(row=0, column=idx, sticky="nsew", padx=4)
            t_lbl = tk.Label(card, text=self.tr(t_key), bg=P["bg_card"], fg=P["text_muted"], font=(self.ui_font, 8, "bold"), anchor="w")
            t_lbl.pack(fill="x")
            self.kpi_lbl_titles[t_key] = t_lbl
            tk.Label(card, textvariable=self.kpi_vars[k_id], bg=P["bg_card"], fg=col, font=(self.mono_font, 11, "bold"), anchor="w").pack(fill="x", pady=(2, 0))

        # ── 3. CONTROL & MODE SELECTOR BAR ───────────────────────────────────
        ctrl_bar = tk.Frame(self.root, bg=P["bg_card"], padx=14, pady=8, highlightthickness=1, highlightbackground=P["border"])
        ctrl_bar.pack(side="top", fill="x", padx=18, pady=(2, 6))

        mode_row = tk.Frame(ctrl_bar, bg=P["bg_card"])
        mode_row.pack(fill="x", pady=(0, 6))

        self.mode_buttons = {}
        for m_val, m_key in [("1v1", "mode_1v1"), ("long", "mode_long"), ("cohort", "mode_cohort")]:
            b = ttk.Button(
                mode_row, text=self.tr(m_key),
                command=lambda v=m_val: self._switch_mode(v),
                style="Primary.TButton" if m_val == "1v1" else "Ghost.TButton"
            )
            b.pack(side="left", padx=(0, 6))
            self.mode_buttons[m_val] = (b, m_key)

        # Slider for Wipe / Onion-Skin blend
        slider_frame = tk.Frame(mode_row, bg=P["bg_card"])
        slider_frame.pack(side="right")
        self.lbl_slider = tk.Label(slider_frame, text=self.tr("lbl_slider"), bg=P["bg_card"], fg=P["text_muted"], font=(self.ui_font, 9))
        self.lbl_slider.pack(side="left", padx=(0, 6))
        self.scale_wipe = ttk.Scale(
            slider_frame, from_=5.0, to=95.0, orient="horizontal", length=160,
            variable=self.slider_pct, command=lambda _v: self.refresh_comparison()
        )
        self.scale_wipe.pack(side="left")

        # Selector row (Record A, Record B, Artifact, View Mode)
        sel_row = tk.Frame(ctrl_bar, bg=P["bg_card"])
        sel_row.pack(fill="x")

        self.lbl_sel_a = tk.Label(sel_row, text=self.tr("lbl_select_a"), bg=P["bg_card"], fg=P["cyan"], font=(self.ui_font, 9, "bold"))
        self.lbl_sel_a.pack(side="left", padx=(0, 4))
        self.combo_a = ttk.Combobox(sel_row, state="readonly", width=32)
        self.combo_a.pack(side="left", padx=(0, 12))
        self.combo_a.bind("<<ComboboxSelected>>", lambda _e: self.refresh_comparison())

        self.lbl_sel_b = tk.Label(sel_row, text=self.tr("lbl_select_b"), bg=P["bg_card"], fg=P["emerald"], font=(self.ui_font, 9, "bold"))
        self.lbl_sel_b.pack(side="left", padx=(0, 4))
        self.combo_b = ttk.Combobox(sel_row, state="readonly", width=32)
        self.combo_b.pack(side="left", padx=(0, 12))
        self.combo_b.bind("<<ComboboxSelected>>", lambda _e: self.refresh_comparison())

        self.lbl_art = tk.Label(sel_row, text=self.tr("lbl_artifact"), bg=P["bg_card"], fg=P["text_muted"], font=(self.ui_font, 9))
        self.lbl_art.pack(side="left", padx=(0, 4))
        self.combo_artifact = ttk.Combobox(
            sel_row, state="readonly", width=18,
            values=["heatmap", "faded_hm", "summary", "combined_hm", "dips"]
        )
        self.combo_artifact.set("heatmap")
        self.combo_artifact.pack(side="left", padx=(0, 12))
        self.combo_artifact.bind("<<ComboboxSelected>>", lambda _e: self._on_artifact_selected())

        self.lbl_view = tk.Label(sel_row, text=self.tr("lbl_view_mode"), bg=P["bg_card"], fg=P["text_muted"], font=(self.ui_font, 9))
        self.lbl_view.pack(side="left", padx=(0, 4))
        self.combo_view = ttk.Combobox(
            sel_row, state="readonly", width=18,
            values=["wipe", "sbs", "diff", "blend", "radar"]
        )
        self.combo_view.set("wipe")
        self.combo_view.pack(side="left")
        self.combo_view.bind("<<ComboboxSelected>>", lambda _e: self._on_view_selected())

        # ── 4. MAIN SPLIT WORKSPACE (LEFT: INTERACTIVE CANVAS | RIGHT: STATS TABLE) ──
        workspace = tk.PanedWindow(self.root, orient="horizontal", bg=P["border"], sashwidth=5, bd=0)
        workspace.pack(side="top", fill="both", expand=True, padx=18, pady=(0, 8))

        left_card = tk.Frame(workspace, bg=P["bg_card"], highlightthickness=1, highlightbackground=P["border"])
        right_card = tk.Frame(workspace, bg=P["bg_card"], highlightthickness=1, highlightbackground=P["border"])
        workspace.add(left_card, minsize=460, stretch="always")
        workspace.add(right_card, minsize=420, stretch="always")

        self.canvas_view = tk.Canvas(left_card, bg="#090D14", highlightthickness=0, cursor="crosshair")
        self.canvas_view.pack(fill="both", expand=True)
        self.canvas_view.bind("<Configure>", lambda _e: self._redraw_canvas_image())
        self.canvas_view.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas_view.bind("<ButtonPress-1>", self._on_canvas_drag)

        # Right side: Delta & Cohort Statistical Table
        cols = ("metric", "val_a", "val_b", "delta", "pct", "extra", "eval")
        self.tree = ttk.Treeview(right_card, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("metric", text=self.tr("col_metric"))
        self.tree.heading("val_a", text=self.tr("col_val_a"))
        self.tree.heading("val_b", text=self.tr("col_val_b"))
        self.tree.heading("delta", text=self.tr("col_delta"))
        self.tree.heading("pct", text=self.tr("col_pct"))
        self.tree.heading("extra", text=self.tr("col_p_val"))
        self.tree.heading("eval", text=self.tr("col_eval"))

        self.tree.column("metric", width=210, anchor="w")
        self.tree.column("val_a", width=85, anchor="e")
        self.tree.column("val_b", width=85, anchor="e")
        self.tree.column("delta", width=80, anchor="e")
        self.tree.column("pct", width=75, anchor="e")
        self.tree.column("extra", width=95, anchor="center")
        self.tree.column("eval", width=95, anchor="center")

        self.tree.tag_configure("improved", foreground="#34D399")
        self.tree.tag_configure("worse", foreground="#F87171")
        self.tree.tag_configure("neutral", foreground="#94A3B8")

        vsb = ttk.Scrollbar(right_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_metric_selected)

        # ── 5. STATUS BAR ────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value=self.tr("status_ready"))
        status_bar = tk.Frame(self.root, bg=P["bg_card"], padx=16, pady=5, highlightthickness=1, highlightbackground=P["border"])
        status_bar.pack(side="bottom", fill="x")
        tk.Label(status_bar, textvariable=self.status_var, bg=P["bg_card"], fg=P["text_muted"], font=(self.mono_font, 8), anchor="w").pack(fill="x")

    def toggle_language(self):
        self.lang = "en" if self.lang == "hu" else "hu"
        self.btn_lang.config(text="EN" if self.lang == "en" else "HU")
        self.lbl_sub.config(text=self.tr("subtitle"))
        self.btn_load_a.config(text=self.tr("btn_load_dir_a"))
        self.btn_load_b.config(text=self.tr("btn_load_dir_b"))
        self.btn_exp_img.config(text=self.tr("btn_export_img"))
        self.btn_exp_csv.config(text=self.tr("btn_export_csv"))
        self.btn_exp_html.config(text=self.tr("btn_export_html"))
        self.lbl_slider.config(text=self.tr("lbl_slider"))
        self.lbl_sel_a.config(text=self.tr("lbl_select_a"))
        self.lbl_sel_b.config(text=self.tr("lbl_select_b"))
        self.lbl_art.config(text=self.tr("lbl_artifact"))
        self.lbl_view.config(text=self.tr("lbl_view_mode"))
        for t_key, lbl_w in self.kpi_lbl_titles.items():
            lbl_w.config(text=self.tr(t_key))
        for _m_val, (btn_w, m_key) in self.mode_buttons.items():
            btn_w.config(text=self.tr(m_key))
        self.tree.heading("metric", text=self.tr("col_metric"))
        self.tree.heading("val_a", text=self.tr("col_val_a"))
        self.tree.heading("val_b", text=self.tr("col_val_b"))
        self.tree.heading("delta", text=self.tr("col_delta"))
        self.tree.heading("pct", text=self.tr("col_pct"))
        self.tree.heading("extra", text=self.tr("col_p_val"))
        self.tree.heading("eval", text=self.tr("col_eval"))
        self.refresh_comparison()

    def _switch_mode(self, mode: str):
        self.current_mode.set(mode)
        for m_val, (btn_w, _m_key) in self.mode_buttons.items():
            btn_w.configure(style="Primary.TButton" if m_val == mode else "Ghost.TButton")
        self.refresh_comparison()

    def _on_artifact_selected(self):
        self.current_artifact.set(self.combo_artifact.get())
        self.refresh_comparison()

    def _on_view_selected(self):
        self.current_view.set(self.combo_view.get())
        self.refresh_comparison()

    def _on_canvas_drag(self, event):
        if self.current_mode.get() == "1v1" and self.current_view.get() in ("wipe", "blend"):
            cw = max(1, self.canvas_view.winfo_width())
            pct = float(np.clip((event.x / float(cw)) * 100.0, 5.0, 95.0))
            self.slider_pct.set(pct)
            self.refresh_comparison()

    def _on_tree_metric_selected(self, _event=None):
        if self.current_mode.get() != "long":
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(METRIC_SPECS):
            self.long_metric_var.set(METRIC_SPECS[idx][0])
            self.refresh_comparison()

    def prompt_load(self, slot: str):
        folder = filedialog.askdirectory(title=f"Select MouseAnalyzer Results Folder ({slot})")
        if not folder:
            file_p = filedialog.askopenfilename(
                title=f"Or Select CSV / Heatmap File ({slot})",
                filetypes=[("MouseAnalyzer Data", "*.csv *.jpg *.png"), ("All Files", "*.*")]
            )
            if not file_p:
                return
            folder = file_p
        self.load_dataset(folder, slot=slot)

    def load_dataset(self, path: str, slot: str = "A"):
        raw_records = AnalyzerDatasetLoader.load_from_path(path)
        aggregates = AnalyzerDatasetLoader.build_subject_aggregates(raw_records)
        all_recs = raw_records + aggregates

        if slot == "A":
            self.records_a = all_recs
            if not self.records_b:
                self.records_b = list(all_recs)
        else:
            self.records_b = all_recs
            if not self.records_a:
                self.records_a = list(all_recs)

        self._populate_selectors()
        self.refresh_comparison()

    def _populate_selectors(self):
        labels_a = [r.display_label for r in self.records_a]
        labels_b = [r.display_label for r in self.records_b]
        self.combo_a["values"] = labels_a
        self.combo_b["values"] = labels_b
        if labels_a:
            self.combo_a.current(0)
        if labels_b:
            self.combo_b.current(min(1, len(labels_b) - 1))

        runs_a = [r for r in self.records_a if not r.is_subject_aggregate]
        runs_b = [r for r in self.records_b if not r.is_subject_aggregate]
        subjs_a = len({r.subject_id for r in runs_a})
        subjs_b = len({r.subject_id for r in runs_b})
        self.kpi_vars["rec_a"].set(f"{len(runs_a)} runs ({subjs_a} ID)")
        self.kpi_vars["rec_b"].set(f"{len(runs_b)} runs ({subjs_b} ID)")
        self.status_var.set(self.tr("status_loaded", na=len(runs_a), sa=subjs_a, nb=len(runs_b), sb=subjs_b))

    def _get_selected_pair(self) -> Tuple[Optional[RunRecord], Optional[RunRecord]]:
        idx_a = self.combo_a.current()
        idx_b = self.combo_b.current()
        rec_a = self.records_a[idx_a] if 0 <= idx_a < len(self.records_a) else (self.records_a[0] if self.records_a else None)
        rec_b = self.records_b[idx_b] if 0 <= idx_b < len(self.records_b) else (self.records_b[0] if self.records_b else None)
        return rec_a, rec_b

    def refresh_comparison(self):
        mode = self.current_mode.get()
        rec_a, rec_b = self._get_selected_pair()

        if rec_a is None or rec_b is None:
            self._cached_visual_bgr = VisualComparisonEngine.make_placeholder(960, 460, self.tr("msg_no_data"))
            self._redraw_canvas_image()
            return

        art = self.current_artifact.get()
        vmode = self.current_view.get()
        ratio = float(self.slider_pct.get()) / 100.0

        img_a = read_image_unicode(rec_a.get_image_path(art) or "")
        img_b = read_image_unicode(rec_b.get_image_path(art) or "")
        self._current_spatial = VisualComparisonEngine.compute_spatial_metrics(img_a, img_b)
        self.kpi_vars["ssim"].set(
            f"SSIM {self._current_spatial['ssim']:.3f} | r={self._current_spatial['dwell_corr']:.2f}"
        )

        if mode == "1v1":
            self._current_rows = StatisticalComparator.compare_1v1(rec_a, rec_b, lang=self.lang)
            self._populate_tree(self._current_rows, is_cohort=False)
            if art == "dips":
                self._cached_visual_bgr = VisualComparisonEngine.render_dip_gallery(rec_a, rec_b)
            elif vmode == "sbs":
                self._cached_visual_bgr = VisualComparisonEngine.render_side_by_side(img_a, img_b, rec_a.display_label, rec_b.display_label)
            elif vmode == "wipe":
                self._cached_visual_bgr = VisualComparisonEngine.render_wipe_slider(img_a, img_b, ratio, rec_a.display_label, rec_b.display_label)
            elif vmode == "diff":
                self._cached_visual_bgr = VisualComparisonEngine.render_difference_heatmap(img_a, img_b, rec_a.display_label, rec_b.display_label)
            elif vmode == "blend":
                self._cached_visual_bgr = VisualComparisonEngine.render_onion_blend(img_a, img_b, ratio, rec_a.display_label, rec_b.display_label)
            else:
                self._cached_visual_bgr = VisualComparisonEngine.render_radar_and_zones_chart(
                    rec_a.metrics, rec_b.metrics, rec_a.display_label, rec_b.display_label
                )

        elif mode == "long":
            subj_runs = [r for r in self.records_a if r.subject_id == rec_a.subject_id and not r.is_subject_aggregate]
            if len(subj_runs) < 2:
                subj_runs = [r for r in self.records_a if not r.is_subject_aggregate]
            first_r = subj_runs[0] if subj_runs else rec_a
            last_r = subj_runs[-1] if subj_runs else rec_b
            self._current_rows = StatisticalComparator.compare_1v1(first_r, last_r, lang=self.lang)
            self._populate_tree(self._current_rows, is_cohort=False)
            self._cached_visual_bgr = VisualComparisonEngine.render_longitudinal_chart(
                subj_runs, self.long_metric_var.get(), lang=self.lang
            )

        else:  # Cohort / Group mode
            self._current_rows = StatisticalComparator.compare_cohorts(self.records_a, self.records_b, lang=self.lang)
            self._populate_tree(self._current_rows, is_cohort=True)
            mean_a = {r["key"]: r["val_a"] for r in self._current_rows}
            mean_b = {r["key"]: r["val_b"] for r in self._current_rows}
            if vmode == "diff" and img_a is not None and img_b is not None:
                self._cached_visual_bgr = VisualComparisonEngine.render_difference_heatmap(img_a, img_b, "Cohort A", "Cohort B")
            else:
                self._cached_visual_bgr = VisualComparisonEngine.render_radar_and_zones_chart(
                    mean_a, mean_b, "Cohort A (Mean)", "Cohort B (Mean)"
                )

        # Update headline KPI delta (Paw Faults & Transit Time)
        fault_row = next((r for r in self._current_rows if r["key"] == "Mancs_Labhiba_Db"), None)
        time_row = next((r for r in self._current_rows if r["key"] == "Teljes_Athaladasi_Ido_mp"), None)
        if fault_row and time_row:
            self.kpi_vars["headline"].set(
                f"Faults: {fault_row['delta']:+.1f} ({fault_row['pct']:+.0f}%) | Time: {time_row['delta']:+.2f}s"
            )

        self._redraw_canvas_image()

    def _populate_tree(self, rows: List[Dict[str, Any]], is_cohort: bool = False):
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            if is_cohort:
                va_str = f"{r['val_a']:.2f}±{r.get('sd_a', 0.0):.2f}"
                vb_str = f"{r['val_b']:.2f}±{r.get('sd_b', 0.0):.2f}"
                ext_str = f"p={r.get('p_t', 1.0):.3f} | d={r.get('cohens_d', 0.0):+.2f}"
            else:
                va_str = f"{r['val_a']:.2f}"
                vb_str = f"{r['val_b']:.2f}"
                ext_str = r.get("unit", "")
            self.tree.insert(
                "", "end",
                values=(
                    r["label"], va_str, vb_str,
                    f"{r['delta']:+.2f}", f"{r['pct']:+.1f}%",
                    ext_str, r["eval_text"]
                ),
                tags=(r["status"],)
            )

    def _redraw_canvas_image(self):
        if self._cached_visual_bgr is None:
            return
        cw = max(100, self.canvas_view.winfo_width())
        ch = max(100, self.canvas_view.winfo_height())
        ih, iw = self._cached_visual_bgr.shape[:2]
        scale = min(cw / float(iw), ch / float(ih))
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        resized = cv2.resize(self._cached_visual_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", resized)
        if ok:
            self._photo_ref = tk.PhotoImage(data=buf.tobytes())
            self.canvas_view.delete("all")
            self.canvas_view.create_image(cw // 2, ch // 2, image=self._photo_ref, anchor="center")

    def action_export_image(self):
        rec_a, rec_b = self._get_selected_pair()
        if rec_a is None or rec_b is None:
            messagebox.showinfo(APP_NAME, self.tr("msg_no_data"))
            return
        out_path = filedialog.asksaveasfilename(
            title="Export High-Res Comparison Summary Image",
            defaultextension=".png",
            initialfile=f"Comparison_{rec_a.safe_id}_vs_{rec_b.safe_id}.png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg")],
        )
        if not out_path:
            return
        art = self.current_artifact.get()
        img_a = read_image_unicode(rec_a.get_image_path(art) or "")
        img_b = read_image_unicode(rec_b.get_image_path(art) or "")
        sbs = VisualComparisonEngine.render_side_by_side(img_a, img_b, rec_a.display_label, rec_b.display_label)
        diff = VisualComparisonEngine.render_difference_heatmap(img_a, img_b, rec_a.display_label, rec_b.display_label)
        radar = VisualComparisonEngine.render_radar_and_zones_chart(
            rec_a.metrics, rec_b.metrics, rec_a.display_label, rec_b.display_label
        )
        comp = ReportExporter.build_composite_summary_image(
            sbs, diff, radar, self._current_rows, rec_a.display_label, rec_b.display_label
        )
        if save_image_unicode(out_path, comp):
            messagebox.showinfo(APP_NAME, self.tr("msg_exported", path=out_path))

    def action_export_csv(self):
        if not self._current_rows:
            messagebox.showinfo(APP_NAME, self.tr("msg_no_data"))
            return
        out_path = filedialog.asksaveasfilename(
            title="Export Comparison Delta CSV",
            defaultextension=".csv",
            initialfile="MouseAnalyzer_Comparison_Deltas.csv",
            filetypes=[("CSV File", "*.csv")],
        )
        if not out_path:
            return
        is_coh = self.current_mode.get() == "cohort"
        if ReportExporter.export_csv(out_path, self._current_rows, is_cohort=is_coh):
            messagebox.showinfo(APP_NAME, self.tr("msg_exported", path=out_path))

    def action_export_html(self):
        rec_a, rec_b = self._get_selected_pair()
        if rec_a is None or rec_b is None or not self._current_rows:
            messagebox.showinfo(APP_NAME, self.tr("msg_no_data"))
            return
        out_path = filedialog.asksaveasfilename(
            title="Export Self-Contained HTML / PDF Report",
            defaultextension=".html",
            initialfile=f"MouseAnalyzer_Report_{rec_a.safe_id}_vs_{rec_b.safe_id}.html",
            filetypes=[("HTML Report", "*.html")],
        )
        if not out_path:
            return
        art = self.current_artifact.get()
        img_a = read_image_unicode(rec_a.get_image_path(art) or "")
        img_b = read_image_unicode(rec_b.get_image_path(art) or "")
        sbs = VisualComparisonEngine.render_side_by_side(img_a, img_b, rec_a.display_label, rec_b.display_label)
        diff = VisualComparisonEngine.render_difference_heatmap(img_a, img_b, rec_a.display_label, rec_b.display_label)
        radar = VisualComparisonEngine.render_radar_and_zones_chart(
            rec_a.metrics, rec_b.metrics, rec_a.display_label, rec_b.display_label
        )
        is_coh = self.current_mode.get() == "cohort"
        if ReportExporter.export_html_report(
            out_path, rec_a.display_label, rec_b.display_label,
            self._current_rows, self._current_spatial, sbs, diff, radar, is_cohort=is_coh
        ):
            try:
                webbrowser.open(Path(os.path.abspath(out_path)).as_uri())
            except Exception:
                pass
            messagebox.showinfo(APP_NAME, self.tr("msg_exported", path=out_path))


def main():
    configure_native_os_identity()
    path_a = sys.argv[1] if len(sys.argv) > 1 else None
    path_b = sys.argv[2] if len(sys.argv) > 2 else None
    root = tk.Tk()
    _app = MouseComparatorApp(root, init_path_a=path_a, init_path_b=path_b)
    root.mainloop()


if __name__ == "__main__":
    main()
