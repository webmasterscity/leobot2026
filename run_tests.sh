#!/usr/bin/env bash
set -euo pipefail
python -m unittest discover -s tests -v
python v3_experiment.py
python v31_grounding_experiment.py
python v32_procedure_grounding_experiment.py
python v33_procedure_composition_experiment.py
