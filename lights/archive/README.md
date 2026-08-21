# Archived LED tooling

## angio_setup.py

Configured a **WLED Angio-8** board from `tube-map.json` — LED outputs and
GPIO pins per data line, E1.31 *Multi RGB* realtime with a per-board start
universe, force-max-brightness, a 5% offline boot preset, mDNS name, and an
ABL power cap.

Retired **2026-08-20** when the LEDs moved to a single
[Kulp K128D-B](../k128/README.md): one data line per tube instead of five
WLED boards driving 4-tube chains. Its replacement is
[k128/fpp_setup.py](../k128/fpp_setup.py), which configures FPP over its HTTP
API from the same map.

Kept because the five Angio-8 boards still exist and still work. If one gets
pressed back into service, this script is how you set it up — but note it
expects the **old** `tube-map.json` shape (`angios` / `groups` /
`start_universe` / serpentine), which the current generator no longer emits.
Recover it from git history before `tube_map.py` was rewritten:

```bash
git log --oneline -- lights/tube_map.py
git show <commit-before-the-rewrite>:lights/tube-map.json > /tmp/old-tube-map.json
```
