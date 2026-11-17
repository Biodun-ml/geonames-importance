# Run a command and print its wall time and peak RSS (Linux), e.g.
# python scripts/measure.py geonames-importance score data/NG.zip -o ng.parquet

import resource
import subprocess
import sys
import time

started = time.perf_counter()
returncode = subprocess.run(sys.argv[1:]).returncode
elapsed = time.perf_counter() - started
# ru_maxrss is in kilobytes on Linux (bytes on macOS).
peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
print(f"wall {elapsed:.1f}s, peak RSS {peak_mb:.0f} MB, exit {returncode}", file=sys.stderr)
sys.exit(returncode)
