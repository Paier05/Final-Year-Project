set -e
PY=../../.venv/Scripts/python.exe
for cfg in "--mode rzero" "--mode uniform" "--mode hardest" "--mode oracle" \
           "--mode rzero --ablate no-rep-penalty" \
           "--mode rzero --ablate no-filter" \
           "--mode rzero --ablate single-model"; do
  echo "=============== $cfg ==============="
  $PY run.py $cfg --seeds 3 --iters 15 --quiet
done
echo "ALL DONE"
