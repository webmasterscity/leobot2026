#!/usr/bin/env bash
# Regresión completa + regeneración de experiments/ en results_v3/.
# Uso: ./run_tests.sh            -> pruebas y experimentos
#      ./run_tests.sh --solo-pruebas
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m unittest discover -s tests
[ "${1:-}" = "--solo-pruebas" ] && exit 0
for f in experiments/v*.py; do
  name="${f##*/}"
  name="${name%.py}"
  echo "== $f"
  case "$name" in
    v58_conditional_bootstrap_experiment|v510_natural_negation_experiment|\
    v511_negative_only_raw_experiment|v513_open_raw_arity_experiment|\
    v514_multi_antecedent_experiment|v515_contextual_revision_experiment|\
    v55_question_meta_transfer_experiment|v56_natural_conditional_rule_experiment)
      "$PY" -m "experiments.$name" > "results_v3/${name}.json"
      "$PY" -m json.tool "results_v3/${name}.json" > /dev/null
      ;;
    *) "$PY" -m "experiments.$name" > /dev/null ;;
  esac
done
echo "Experimentos regenerados en results_v3/"
