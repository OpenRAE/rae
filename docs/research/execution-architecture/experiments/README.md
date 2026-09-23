# Running the bounded probes

These files are non-production experiment fixtures. They use only synthetic
effects and intentionally crash their own worker processes. Use a fresh,
disposable working directory: `.probe-state/` and `results/` are generated there.
The seven candidates are not production dependencies of RAE.

## Python probes

Use Python 3.12 with the versions in [evidence.json](../evidence.json). The tested
direct dependencies are AnyIO 4.15.1, DBOS 3.0.0, Temporal SDK 1.33.0, Ray 2.58.0
and SimPy 4.1.2. Run each probe in a fresh copied source directory or preserve
its initial empty `.probe-state/`; reusing crash markers invalidates the intended
first-attempt boundary. All programs should be supervised by an outer timeout.

```sh
python -m unittest test_witness
timeout 150 python probe_workers.py
timeout 150 python probe_simpy.py
timeout 150 python probe_dbos.py
timeout 150 python probe_ray.py
timeout 150 python verify_temporal.py
timeout 15 python probe_publication.py
```

The Temporal probe starts a local development service through its SDK. Initial
startup downloads its development binary; record the selected server version.
This run used CLI 1.9.1/server 1.32.0 with in-memory persistence. Only worker
process loss is injected. The SQLite probe is a separate toy transaction model,
not the production RAE store. DBOS uses its own SQLite files; its guard is a
synthetic retained claim marker owned by the experiment.

`verify_temporal.py` runs the original Temporal probe, then checks its expected
terminal statuses and result/error types as well as effect counts. Use this
entry point for new runs: the original collector alone can absorb a timeout or
record zero effects without establishing cooperative cancellation. The original
thirteen sources remain unchanged for historical hash reproducibility.
From the repository root, its negative-control regressions run with:

```sh
python3 -m unittest discover -s docs/research/execution-architecture/experiments -p test_temporal_verification.py -v
```

## ROS and BehaviorTree.CPP

Use the ROS Jazzy environment and package versions in the report. Install the
action tutorial interfaces and BehaviorTree.CPP development package along with
CMake and a C++17 compiler. Source the distribution's setup, restrict discovery
to localhost, then run:

```sh
timeout 45 python3 probe_ros.py
cmake -S . -B build
cmake --build build -j2
timeout 10 build/probe_bt
```

The tested ROS CMake export is `behaviortree_cpp::behaviortree_cpp`. The behavior
tree action intentionally leaves its synthetic background thread running when
halted; this isolates the contract of the halt hook from application-provided
stopping logic. The ROS action server likewise deliberately does not interrupt
the already sent synthetic request. Neither is a production backend example.

## Evidence handling

Python probes write JSON records under `results/`; the C++ probe emits JSON on
stdout. Preserve exact source hashes, package versions and the external witness
observations before terminating the disposable host. Record failed setup attempts
separately from candidate behavior. Never treat a command's successful exit alone
as proof of cancellation, crash durability or exactly-once external effects.

Cloud execution used a dedicated, tagged stack with no inbound network rules,
temporary SSM management identity, encrypted delete-on-termination storage, and
bounded teardown. The [report](../experiment-report.md) and cleanup evidence
describe the executed environment; running these files does not provision AWS
resources automatically.
