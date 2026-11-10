# 📊 MouseComparator PRO

A standalone scientific desktop workstation for comparing **MouseAnalyzer PRO** behavioral tracking pictures, velocity heatmaps, paw-fault (*lenyúlás*) galleries, and 42-column kinematic CSV statistics across individual runs, longitudinal recovery sessions, and experimental cohorts.

---

## ✨ Key Features

* **📂 Automatic Artifact Discovery (`AnalyzerDatasetLoader`):**
  * Automatically parses `Minden_Egyed_Meresi_Adatai.csv` and per-subject `egyed_{id}_meresi_adatok.csv` files (supporting `;` or `,` delimiters and both Hungarian `,` and English `.` decimals).
  * Automatically links per-run and combined heatmaps (`*_heatmap.jpg`, `*_halvany_heatmap.jpg`, `*_OSSZESITETT_heatmap.jpg`), motion summary pictures (`*_osszefoglalo.jpg`), and paw-fault snapshot crops (`*_lenyulas_*.jpg`).
* **🔍 1-vs-1 Visual & Kinematic Comparison (`A vs B`):**
  * Interactive **Curtain Wipe Slider** (drag directly on the canvas), **Side-by-Side** view, **Signed Difference Heatmap ($\Delta\text{Heatmap}$)**, **Onion-Skin Alpha Blend**, and **Paw-Fault Snapshot Gallery**.
  * Computes **SSIM** (Structural Similarity Index), **2D Heatmap Dwell Correlation ($r$)**, and **Horizontal Center-of-Hesitation Shift ($\Delta X\%$)**.
  * Renders a **6-Axis Normalized Biomarker Radar Chart** alongside a **3-Zone (Start / Middle / Goal) & Forepaw/Hindpaw Bar Breakdown**.
* **📈 Longitudinal / Multi-Run Progression:**
  * Tracks the same subject across sequential runs or sessions with linear regression slope (`slope/run`), first-to-last percentage change, and ordered heatmap thumbnails.
* **👥 Cohort / Group Statistical Comparison (`Group A vs Group B`):**
  * Compares Control vs. Treated folders with group $\text{Mean} \pm \text{SD}$, $\Delta\%$, **Welch's two-sample $t$-test ($p$-value)**, **Mann-Whitney $U$ test ($p$-value)**, and **Cohen's $d$ effect size**.
* **📄 Publication-Ready Exports (`ReportExporter`):**
  * Exports high-resolution composite **Summary Images (`.png`/`.jpg`)**, formula-sanitized **Delta & Cohort CSVs (`.csv`)**, and self-contained **HTML5 / Printable PDF Visual Reports (`.html`)** with embedded base64 figures.
  * Bilingual **Hungarian (`HU`) / English (`EN`)** dark-mode interface with Windows Per-Monitor High-DPI and Unicode path support.

---

## 📁 Repository Structure

```text
├── .github/workflows/build.yml   # Automated CI test suite & Windows/macOS release builder
├── assets/
│   ├── icon.icns                 # macOS application bundle icon
│   └── icon.ico                  # Windows executable & window icon
├── tests/
│   └── test_mousecomparator.py   # Automated unit test suite
├── LICENSE                       # MIT License
├── MouseComparator.py            # Main application source
└── README.md                     # Documentation
```

---

## 💾 Installation & Standalone Binaries

Pre-compiled standalone releases (`.exe` for Windows and `.dmg` for macOS) are built automatically on version tags (`v*`) via GitHub Actions:

### Windows (`.exe`)
1. Download `MouseComparator_PRO.exe` from the latest GitHub Release.
2. Double-click to launch *(no Python installation required)*.

### macOS (`.dmg`)
1. Download `MouseComparator_PRO_macOS.dmg` from the latest GitHub Release.
2. Open the disk image and drag **MouseComparator PRO** into your **Applications** folder.
3. *Note:* If macOS Gatekeeper prompts on first launch, right-click (or Control-click) the app icon and select **Open**.

---

## 🛠️ Running from Source & Tests

Ensure Python 3.10+ is installed, then install the dependencies:

```bash
pip install opencv-python numpy scipy
```

Launch the workstation:

```bash
python MouseComparator.py
# Or pass Folder A and Folder B directly via CLI:
python MouseComparator.py /path/to/Control_Results /path/to/Treated_Results
```

Run the automated unit test suite:

```bash
python -m unittest discover -s tests -v
```

Run static analysis / linting (`ruff`):

```bash
ruff check --select E9,F,B MouseComparator.py tests/test_mousecomparator.py
```

---

## 📦 Release Notes (`v0.0.1`)

* **Initial Release (`v0.0.1`):**
  * Added `AnalyzerDatasetLoader` with automatic CSV normalization (`;` / `,` delimiters, `,` / `.` decimals) and visual artifact linking (`heatmap`, `halvany_heatmap`, `osszefoglalo`, `OSSZESITETT`, and `lenyulas` crops).
  * Added `VisualComparisonEngine` supporting Side-by-Side, Interactive Curtain Wipe Slider, Signed Difference Heatmap ($\Delta\text{Heatmap}$), Onion-Skin Alpha Blend, Paw-Fault Snapshot Gallery, 6-Axis Biomarker Radar + 3-Zone Bar Chart, and Longitudinal Progression Curves.
  * Added `StatisticalComparator` with 1-vs-1 deltas, multi-run linear regression trends, and cohort hypothesis testing (Welch's $t$-test, Mann-Whitney $U$, and Cohen's $d$).
  * Added `ReportExporter` for composite `.png`/`.jpg` figures, formula-sanitized `;`-delimited `.csv` tables, and self-contained `.html` / PDF reports.
  * Added GitHub Actions CI/CD workflow (`.github/workflows/build.yml`) to build `MouseComparator_PRO.exe` (Windows) and `MouseComparator_PRO_macOS.dmg` (macOS) on `v*` tags.
