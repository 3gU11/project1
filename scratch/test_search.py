import sys
import os
# Add parent directory to sys.path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crud.traceability import search_global_summary
import pandas as pd

try:
    kw = "187" # Use part of the serial to see if anything comes back
    df = search_global_summary(kw)
    print(f"Results for '{kw}':")
    print(df.to_string())
except Exception as e:
    print(f"Error: {e}")
