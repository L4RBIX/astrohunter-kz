# Data Directory

This directory is intended for raw data inputs. 

**Important Rules:**
- Raw TESS light curves should **not** be committed to version control.
- Data should be downloaded dynamically through scripts and notebooks using public archives (e.g., via `lightkurve`).
- Do not store generated results here. All generated outputs (tables, figures) should be saved to the `results/` directory instead.
