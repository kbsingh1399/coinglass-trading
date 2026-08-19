"""
mythos_pipeline_loop.py  -  Single-command daily updater.

Runs patch_gaps -> check_authenticity in a self-healing loop.
Exits cleanly once everything is 0-gaps + 100% authenticated.

Usage (daily):
  cd to binance_historical_pipeline directory, then:
  python mythos_pipeline_loop.py
"""

import os
import sys
import time
import subprocess

PIPELINE_DIR = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\binance_historical_pipeline"
PATCH_SCRIPT = os.path.join(PIPELINE_DIR, "patch_gaps.py")
AUTH_SCRIPT  = os.path.join(PIPELINE_DIR, "check_authenticity.py")


def run_script(script_path: str, args: list | None = None) -> int:
    cmd = ["python", script_path] + (args or [])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"\n>> Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, cwd=PIPELINE_DIR)
    return result.returncode


def main():
    max_iterations = 5   # Should converge in 1-2; 5 is a generous safety net
    print("\n" + "=" * 60)
    print("  MYTHOS PIPELINE LOOP: AUTOMATED PARQUET SYNC & AUTHENTICATION")
    print("=" * 60 + "\n")

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- [ ITERATION {iteration}/{max_iterations} ] ---")

        # ── Step 1: Dry-run to check if any work is needed ──────────────
        print("\nChecking for gaps / new days...")
        dry = subprocess.run(
            ["python", PATCH_SCRIPT, "--dry-run"],
            capture_output=True, text=True, cwd=PIPELINE_DIR,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        needs_patch = ("Gaps:" in dry.stdout) or ("New:" in dry.stdout)

        if not needs_patch:
            print("No gaps or new days detected.")
        else:
            # ── Step 2: Execute patch ───────────────────────────────────
            print("Gaps or new days detected. Running PATCH_GAPS...")
            patch_code = run_script(PATCH_SCRIPT)
            if patch_code != 0:
                print(f"[ERR] patch_gaps.py exited with code {patch_code}. Retrying in 10 s...")
                time.sleep(10)
                continue

        # ── Step 3: Authenticity check ──────────────────────────────────
        print("\nRunning Authenticity Check...")
        auth_code = run_script(AUTH_SCRIPT)

        if auth_code == 0:
            if not needs_patch:
                # Perfect state: nothing to patch AND everything authenticated
                print("\n" + "=" * 60)
                print("  GOAL ACHIEVED: 0 Gaps & 100% Mathematically Authenticated")
                print("=" * 60)
                sys.exit(0)
            else:
                # We patched something AND auth passed — run one more dry-run to
                # confirm no new gaps were introduced by the alignment trim.
                print("Auth passed after patching. Running one more dry-run to confirm...")
                continue
        else:
            print(f"[ERR] Authenticity check failed (code {auth_code}). Retrying loop...")
            time.sleep(5)

    # If we get here, we exhausted iterations
    print(f"\n[ERR] Max iterations ({max_iterations}) reached. Manual check required.")
    sys.exit(1)


if __name__ == "__main__":
    main()
