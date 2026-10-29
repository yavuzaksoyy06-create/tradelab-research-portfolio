# README figures

Updated 29 October 2026. These are reproducible analytical figures, not generated mockups or fresh market observations.

| Figure | Source | Interpretation |
|---|---|---|
| research-results.png | docs/v41-historical-research.md, parsed archived replay and cost-sensitivity tables | Historical hypothetical P&L; separate periods and separately funded candidates; no fresh backtest |
| causal-replay.png | equity_data.synthetic_fixture, analyze_prefix, indicator_frame and historical_zone_bands | Synthetic completed-bar replay; 160 visible bars, final 100 displayed; no actual SPY prices |

Check out `feature/equity-lab-stage6-slice1` first. Run `python -B tools/build_readme_figures.py` from that development checkout root in the configured Python 3.12 environment. The script needs the existing plotting and research dependencies, performs no downloads, reads no private caches and never invokes a trading or frozen evaluation runner. `readme-figure-sources.json` records source values and SHA-256 hashes for the generated files.

Older UI captures remain preserved in this directory. They are not represented as screenshots of the current Stage 7 interface. The README now prioritizes quantified findings and an explicitly synthetic view of the current causal code.

The figure generator and causal modules are on the development branch, not main. This main-branch publication changes documentation and images only.
