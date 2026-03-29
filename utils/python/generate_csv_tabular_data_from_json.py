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
    Flatten the 'Compute Process Utilization' list-of-dicts column.
    Multiple processes are joined into semicolon-separated strings per field.
    """
    def summarise(entries):
        if not isinstance(entries, list) or len(entries) == 0:
            return pd.Series({
                "ComputeProcess_pid": None,
                "ComputeProcess_AvgSMUtilization(%)": None,
                "ComputeProcess_AvgMemoryUtilization(%)": None,
            })
        pids = "; ".join(str(e.get("pid", "")) for e in entries)
        sm   = "; ".join(str(e.get("Avg SM Utilization (%)", "")) for e in entries)
        mem  = "; ".join(str(e.get("Avg Memory Utilization (%)", "")) for e in entries)
        return pd.Series({
            "ComputeProcess_pid": pids,
            "ComputeProcess_AvgSMUtilization(%)": sm,
            "ComputeProcess_AvgMemoryUtilization(%)": mem,
        })

    expanded = df[col].apply(summarise)
    return df.drop(columns=[col]).join(expanded)


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
        print(f"\nProcessing: {filepath}")
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