import pandas as pd
import glob
import os
import argparse


def flatten_dict_columns(df: pd.DataFrame, col: str, prefix: str) -> pd.DataFrame:
    """Expand a column containing dicts into multiple columns with a given prefix."""
    expanded = df[col].apply(
        lambda x: x if isinstance(x, dict) else {}
    ).apply(pd.Series)
    expanded.columns = [f"{prefix}_{c}" for c in expanded.columns]
    return df.drop(columns=[col]).join(expanded)


def flatten_compute_process(df: pd.DataFrame, col: str = "Compute Process Utilization") -> pd.DataFrame:
    """
    Explode 'Compute Process Utilization' so that each process gets its own row.
    All job-level fields are duplicated across the resulting rows.
    Jobs with no processes get a single row with NaN process columns.
    """
    # Ensure empty / missing values are represented as a list with one None entry
    # so that explode still produces one row for those jobs.
    df[col] = df[col].apply(
        lambda x: x if isinstance(x, list) and len(x) > 0 else [None]
    )

    # One row per process entry
    df = df.explode(col, ignore_index=True)

    # Expand the per-process dict into columns
    process_df = df[col].apply(
        lambda x: pd.Series(x) if isinstance(x, dict) else pd.Series({
            "pid": None,
            "Avg SM Utilization (%)": None,
            "Avg Memory Utilization (%)": None,
        })
    )
    process_df.columns = [
        "ComputeProcess_pid",
        "ComputeProcess_AvgSMUtilization(%)",
        "ComputeProcess_AvgMemoryUtilization(%)",
    ]

    return df.drop(columns=[col]).join(process_df)


def load_and_flatten(input_path: str) -> pd.DataFrame:
    """Read all results_*.json files from input_path and return a flat DataFrame."""
    pattern = os.path.join(input_path, "results_*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        raise FileNotFoundError(f"No files matching 'results_*.json' found in: {input_path}")

    print(f"Found {len(files)} file(s):")
    for f in files:
        print(f"  {f}")

    frames = []
    for filepath in files:
        # pd.read_json with lines=False reads a JSON array as a DataFrame directly
        df = pd.read_json(filepath)
        df["_source_file"] = os.path.basename(filepath)
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)

    # ── Nested dict columns ──────────────────────────────────────────────────
    nested_dict_cols = {
        "PowerUsage(Watts)":        "PowerUsage(Watts)",
        "SMClock(MHz)":             "SMClock(MHz)",
        "MemoryClock(MHz)":         "MemoryClock(MHz)",
        "SMUtilization(%)":         "SMUtilization(%)",
        "MemoryUtilization(%)":     "MemoryUtilization(%)",
        "PCIeRxBandwidth(megabytes)": "PCIeRxBandwidth(megabytes)",
        "PCIeTxBandwidth(megabytes)": "PCIeTxBandwidth(megabytes)",
        "Slowdown Stats":           "SlowdownStats",
    }

    for col, prefix in nested_dict_cols.items():
        if col in df.columns:
            df = flatten_dict_columns(df, col, prefix)

    # ── List-of-dicts column ─────────────────────────────────────────────────
    if "Compute Process Utilization" in df.columns:
        df = flatten_compute_process(df, "Compute Process Utilization")

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Convert results_*.json files to a single CSV file."
    )
    parser.add_argument(
        "--input_path",
        required=True,
        help="Directory containing the results_*.json files.",
    )
    parser.add_argument(
        "--output_path",
        required=True,
        help="Directory (or full file path) where the output CSV will be saved.",
    )
    args = parser.parse_args()

    # Resolve output path
    output_path = args.output_path
    if os.path.isdir(output_path) or not output_path.endswith(".csv"):
        os.makedirs(output_path, exist_ok=True)
        output_path = os.path.join(output_path, "results_combined.csv")

    df = load_and_flatten(args.input_path)

    df.to_csv(output_path, index=False)
    print(f"\nCSV saved to: {output_path}")
    print(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
    print("\nColumns:")
    for col in df.columns:
        print(f"  {col}")


if __name__ == "__main__":
    main()