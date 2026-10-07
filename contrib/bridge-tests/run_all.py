#!/usr/bin/env python3
"""Run every bridge test against one eCash bitcoind, in two lanes (each test has its own ports and datadirs).

    BRIDGE_VANILLA_BIN=/path/to/bitcoin-29/bin ./run_all.py [<ecx-bitcoind>] [--lanes N] [test ...]

test_retry_cost.py is a measurement, not a pass/fail, and runs last on its own so the timing is not disturbed.
"""
import os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_cluster_leak", "test_restart_persist", "test_package_cpfp", "test_no_expiry", "test_package_multi_parent",
         "test_ephemeral_sibling", "test_backpressure", "test_fee_skip", "test_mempool_loss", "test_known_relayed",
         "test_stale_restart", "test_mixed_dead_input", "test_crash_feed", "test_reorg_retrack", "test_gate_release",
         "test_truc_sibling", "test_unpaid_anchor"]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
lanes = int(sys.argv[sys.argv.index("--lanes") + 1]) if "--lanes" in sys.argv else 2
if "--lanes" in sys.argv:
    args.remove(str(lanes))
ecx = [args.pop(0)] if args and os.path.isfile(args[0]) else []
chosen = [t.removesuffix(".py") for t in args] or TESTS

def run(name):
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, name + ".py")] + ecx, capture_output=True, text=True, timeout=1800)
    line = next((l for l in reversed(p.stdout.splitlines()) if l.startswith("RESULT")), (p.stdout + p.stderr).strip().splitlines()[-1:] or ["(no output)"])
    return name, p.returncode, line if isinstance(line, str) else line[0], time.time() - t0

with ThreadPoolExecutor(lanes) as pool:
    results = list(pool.map(run, chosen))
if not args:
    print("measuring test_retry_cost (alone) ...", flush=True)
    p = subprocess.run([sys.executable, os.path.join(HERE, "test_retry_cost.py")] + (ecx or ["-"]) + ["8000"],
                       capture_output=True, text=True, timeout=1800)
    cost = next((l for l in reversed(p.stdout.splitlines()) if l.startswith("RESULT")), "RESULT: (no measurement)")
print()
for name, rc, line, secs in results:
    print(f"{'PASS' if rc == 0 else 'FAIL'}  {name:28s} {secs:5.0f}s  {line.removeprefix('RESULT: ')[:110]}")
if not args:
    print(f"COST  {'test_retry_cost':28s}        {cost.removeprefix('RESULT: ')[:110]}")
failed = [n for n, rc, _, _ in results if rc != 0]
print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
sys.exit(1 if failed else 0)
