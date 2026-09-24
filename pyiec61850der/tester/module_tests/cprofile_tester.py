# -*- coding: utf-8 -*-
"""
A tester script to perform a profiling of the vIED to detect performance bottlenecks.

This test script can be used to monitor the resouce usage of a submodule.
Primarily targeted at developers for code performance optimization.
"""

import cProfile
import pstats
import io
import time
import threading
import sys
import simulation.virtual_ied as pyiec61850cls

PATH_CONFIG = './settings/config.yaml'
TIMEOUT = 300

# --- 1. Define the target loop wrapper ---
def vIED_profiler():
    # Runs your infinite simulation loop normally
    pyiec61850cls.run_virtual_ied(path_config=PATH_CONFIG)

# --- 2. Setup the Profiler ---
pr = cProfile.Profile()
pr.enable()

# --- 3. Run the target in a background thread to bypass Windows limitations ---
tester_thread = threading.Thread(target=vIED_profiler, name="vIED_profiler_thread")
# Setting daemon=True ensures this thread dies automatically when the main script ends
tester_thread.daemon = True
tester_thread.start()


print(f"[Main] Background thread active. Gathering profile data in-memory for {TIMEOUT} seconds...")

# --- 4. Wait for the timeout cushion ---
try:
    time.sleep(TIMEOUT)
except KeyboardInterrupt:
    print("\n[Main] Profiling interrupted early by user.")

# --- 5. Stop profiling and generate the report cleanly ---
pr.disable()
print("[Main] Timeout reached. Processing profile results...")

s = io.StringIO()
sortby = pstats.SortKey.CUMULATIVE
# We pass the live `pr` object directly, so no 'program.prof' file is needed!
ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
ps.print_stats(40) # Prints the top 40 heaviest function stacks

print("\n" + "="*40 + " IN-MEMORY PROFILE RESULTS " + "="*40)
print(s.getvalue())

# Force exit the process to instantly clean up all background threads
sys.exit(0)