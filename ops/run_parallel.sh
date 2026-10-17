#!/usr/bin/env bash
# Run one garda-train job per GPU: line i of JOBS_FILE runs on GPU i (CUDA_VISIBLE_DEVICES=i).
# Lines are garda-train arguments; blank lines and '#' comments are ignored.
# Exits non-zero if any job fails. Logs: logs/<jobs-name>-gpu<i>.log
#   usage: ops/run_parallel.sh ops/jobs/wave1_parity.jobs
source "$(dirname "$0")/_env.sh"
JOBS_FILE="${1:?usage: $0 JOBS_FILE}"
EXTRA="${GARDA_EXTRA:-cu124}"
N_GPUS="${N_GPUS:-$(nvidia-smi -L | wc -l)}"
JOBS=()
while IFS= read -r line; do
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  JOBS+=("$line")
done <"$JOBS_FILE"
if (( ${#JOBS[@]} > N_GPUS )); then
  echo "error: ${#JOBS[@]} jobs but only $N_GPUS GPUs" >&2; exit 3
fi
cd "$REPO_DIR"
mkdir -p logs
name="$(basename "$JOBS_FILE" .jobs)"
pids=()
for i in "${!JOBS[@]}"; do
  log="logs/${name}-gpu${i}.log"
  # shellcheck disable=SC2086 # job lines are intentionally word-split into arguments
  CUDA_VISIBLE_DEVICES="$i" nohup uv run --extra "$EXTRA" garda-train ${JOBS[$i]} >"$log" 2>&1 &
  pids+=("$!")
  echo "gpu$i pid $!: garda-train ${JOBS[$i]}  (log: $log)"
done
failed=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    echo "job on gpu$i FAILED (see logs/${name}-gpu${i}.log)" >&2
    failed=1
  fi
done
exit "$failed"
