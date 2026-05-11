# AstroHunter KZ

**Research Question:** Do TESS targets with debris-disk / infrared-excess evidence show a higher post-vetting yield of exocomet-like asymmetric transit candidates compared with matched non-disk control stars?

**Scientific Honesty Statement:** This project identifies candidate asymmetric transits (dips) based on simple depth and asymmetry scoring. It serves as a reproducible signal-detection pipeline for controlled statistical comparisons. It does **NOT** claim the discovery of confirmed exocomets.

**Phase 1 Status:** Beta Pic positive-control test.
The goal of this phase is to retrieve TESS light curves for $\beta$ Pictoris, detect candidate dips, compute simple asymmetry scores, and output figures and tables, ensuring the known events can be recovered by the pipeline without applying machine learning yet.

## Installation

1. Clone the repository and navigate into it:
   ```bash
   git clone <your-repo-url>
   cd astrohunter-kz
   ```

2. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Phase 1 Notebook

1. Launch Jupyter Notebook or Jupyter Lab:
   ```bash
   jupyter notebook
   ```
2. Open `notebooks/01_beta_pic_positive_control.ipynb`.
3. Run all cells in the notebook.

## Expected Outputs
Running the notebook will download the data (which takes a minute) and automatically save outputs:
- **Full light curve plot**: Saved to `results/figures/beta_pic_full_lightcurve.png`
- **Candidate event window plots**: The top 10 deepest events will be plotted and saved in `results/figures/`
- **Candidate table**: A CSV of all detected candidates will be saved to `results/tables/beta_pic_candidate_dips.csv`
