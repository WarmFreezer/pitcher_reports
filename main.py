import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import os

#venv/Scripts/activate

def main():
    # use a path relative to this script so running from another cwd still works
    base_dir = os.path.dirname(__file__)
    input_dir = os.path.join(base_dir, 'app', 'input')

    if not os.path.isdir(input_dir):
        print(f"Input directory not found: {input_dir}")
        return

    files = os.listdir(input_dir)
    if not files:
        print(f"No files found in input directory: {input_dir}")
        return

    for filename in files:
        full_path = os.path.join(input_dir, filename)
        if not os.path.isfile(full_path):
            # skip directories
            continue

        name, ext = os.path.splitext(filename)
        ext = ext.lower()

        try:
            if ext in ('.xlsx', '.xls', '.xlsm', '.xlsb'):
                df = pd.read_excel(full_path)
            elif ext == '.csv':
                df = pd.read_csv(full_path)
            else:
                print(f"Skipping unsupported file type: {filename}")
                continue

            print(f"--- {filename} ---")
            print(df.head())

        except Exception as exc:
            print(f"Failed to read {filename}: {exc}")


if __name__ == '__main__':
    main()