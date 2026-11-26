#!/bin/bash
#SBATCH --partition=UGGPU-TC1
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --cpus-per-task=10
#SBATCH --mem=30G
#SBATCH --time=15
#SBATCH --output=logs/output_%x_%j.out
#SBATCH --error=logs/error_%x_%j.err

# Smoke check for issue #16, in the setup of the real run (script A: one job
# per game, both at once). Submit from the repo root on TC1 (~/evo-harness-16):
#     mkdir -p logs
#     sbatch --export=ALL,GAME=ft09 --job-name=smoke-ft09-v4 cluster/job_smoke16.sh
#     sbatch --export=ALL,GAME=vc33 --job-name=smoke-vc33-v4 cluster/job_smoke16.sh
# Each job: the test suite, then the preflight (evolve/smoke.py: the game
# steps, the model endpoint answers from this node, a short run with all 5
# seeds starting, the action record in the player's context and in
# action_log, a checkpoint and a resume, the state-change and repeat checks
# on the saved episodes), in its own run directory runs/smoke_<game>-v4_<job>.
# Last, #15's run directories (~/evo-harness/runs/ft09, vc33) must have no file
# newer than the start of this job. If any step fails the job exits non-zero:
# do not start the real run.

if [ -z "$GAME" ]; then
  echo "GAME is not set: sbatch --export=ALL,GAME=ft09 ..." >&2
  exit 2
fi

module load anaconda
source activate evo-harness
set -a; source ~/.evo_harness_env; set +a
export OPERATION_MODE=offline
export PYTHONUNBUFFERED=1
MARK=$(mktemp)

echo "=== node $(hostname), job $SLURM_JOB_ID, game $GAME, commit $(cat COMMIT), start $(date +%FT%T), $(python --version) ==="
echo "=== 1/3 test suite ==="
python -m evolve.selftest
TESTS=$?
echo "=== test suite exit code: $TESTS ==="
if [ $TESTS -ne 0 ]; then rm -f "$MARK"; exit $TESTS; fi

echo "=== 2/3 preflight ==="
python evolve_run.py --config config_evolve_16.yaml --game "$GAME" --stage smoke --run-dir "runs/smoke_${GAME}-v4_$SLURM_JOB_ID"
SMOKE=$?
echo "=== preflight exit code: $SMOKE ==="

echo "=== 3/3 #15's run directories untouched ==="
TOUCHED=0
for D in ~/evo-harness/runs/ft09 ~/evo-harness/runs/vc33; do
  if [ -d "$D" ]; then
    N=$(find "$D" -newer "$MARK" | wc -l)
    echo "$D: $N file(s) changed since this job started"
    TOUCHED=$((TOUCHED + N))
  else
    echo "$D: not there"
  fi
done
rm -f "$MARK"
echo "=== end $(date +%FT%T) ==="
if [ $SMOKE -ne 0 ]; then exit $SMOKE; fi
if [ $TOUCHED -ne 0 ]; then exit 4; fi
exit 0
