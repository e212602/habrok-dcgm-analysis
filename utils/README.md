# utils

Helpers for DCGM analytics tasks.

## Python utils

- `generate_csv_tabular_data_from_json_v2.py`: Convert DCGM JSON output files (`results_*.json`) into a single CSV.

### usage

```bash
python3 utils/python/generate_csv_tabular_data_from_json.py <input-path> <output-path>
```

- `<input-path>` can be a folder containing `results_*.json` or a single `results_*.json` file.
- `<output-path>` is the destination CSV file path.

### features

- Normalizes numeric strings to numbers when possible.
- Flattens nested objects and arrays.
- Supports malformed input with trailing commas and newline JSON.
- Adds `_source_file` per row.

