#!/usr/bin/env python3
"""
Process GPU monitoring log files and generate sbatch scripts from SLURM accounting data.

This script:
1. Iterates through JSON files containing GPU monitoring data
2. Extracts job_id from each entry
3. Queries SLURM accounting data using sacct
4. Generates sbatch scripts and metadata for each job
"""

import json
import subprocess
import argparse
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def convert_memory(memory_mb):
    """Convert memory from MB to appropriate unit for sbatch."""
    if memory_mb >= 1024:
        return f"{memory_mb // 1024}G"
    return f"{memory_mb}M"


def convert_time(seconds):
    """Convert seconds to HH:MM:SS format for sbatch."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_timestamp(timestamp):
    """Convert Unix timestamp to readable format."""
    if timestamp and timestamp > 0:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return None


def extract_sbatch_params(job_data):
    """Extract relevant sbatch parameters from job data."""
    params = {}
    
    # Job name
    if job_data.get("name"):
        params["job-name"] = job_data["name"]
    
    # Partition
    if job_data.get("partition"):
        params["partition"] = job_data["partition"]
    
    # Account
    if job_data.get("account"):
        params["account"] = job_data["account"]
    
    # Number of nodes
    if job_data.get("allocation_nodes"):
        params["nodes"] = job_data["allocation_nodes"]
    
    # CPUs (from required or allocated TRES)
    if "required" in job_data and job_data["required"].get("CPUs"):
        params["cpus-per-task"] = job_data["required"]["CPUs"]
    
    # Memory
    if "required" in job_data:
        mem_per_node = job_data["required"].get("memory_per_node", {})
        mem_per_cpu = job_data["required"].get("memory_per_cpu", {})
        
        if mem_per_node.get("set") and mem_per_node.get("number"):
            params["mem"] = convert_memory(mem_per_node["number"])
        elif mem_per_cpu.get("set") and mem_per_cpu.get("number"):
            params["mem-per-cpu"] = convert_memory(mem_per_cpu["number"])
    
    # Time limit
    if "time" in job_data and "limit" in job_data["time"]:
        time_limit = job_data["time"]["limit"]
        if time_limit.get("set") and time_limit.get("number"):
            params["time"] = convert_time(time_limit["number"] * 60)  # Convert minutes to seconds
    
    # QOS
    if job_data.get("qos"):
        params["qos"] = job_data["qos"]
    
    # GPUs (from TRES)
    if "tres" in job_data and "requested" in job_data["tres"]:
        for tres in job_data["tres"]["requested"]:
            if tres.get("type") == "gres" and "gpu" in tres.get("name", ""):
                gpu_name = tres["name"]  # e.g., "gpu" or "gpu:a100"
                gpu_count = tres["count"]
                if gpu_name == "gpu":
                    params["gres"] = f"gpu:{gpu_count}"
                else:
                    # Extract specific GPU type
                    gpu_type = gpu_name.split(":")[-1]
                    params["gres"] = f"gpu:{gpu_type}:{gpu_count}"
                break
    
    # Output file
    if job_data.get("stdout"):
        params["output"] = job_data["stdout"]
    
    # Error file (if different from stdout)
    if job_data.get("stderr") and job_data.get("stderr") != job_data.get("stdout"):
        params["error"] = job_data["stderr"]
    
    # Working directory
    if job_data.get("working_directory"):
        params["chdir"] = job_data["working_directory"]
    
    return params


def extract_metadata(job_data):
    """
    Extract metadata that is not part of sbatch script.
    Excludes runtime usage information that cannot be known before execution.
    """
    metadata = {}
    
    # Job identification
    metadata["job_id"] = job_data.get("job_id")
    metadata["cluster"] = job_data.get("cluster")
    metadata["user"] = job_data.get("user")
    metadata["group"] = job_data.get("group")
    
    # Association information
    if "association" in job_data:
        metadata["association"] = {
            "id": job_data["association"].get("id"),
            "cluster": job_data["association"].get("cluster"),
            "partition": job_data["association"].get("partition")
        }
    
    # Submission information (known at submission time)
    if "time" in job_data:
        time_data = job_data["time"]
        metadata["submission_time"] = format_timestamp(time_data.get("submission"))
        metadata["eligible_time"] = format_timestamp(time_data.get("eligible"))
        
        # Planned start time (if available)
        planned = time_data.get("planned", {})
        if planned.get("set") and planned.get("number"):
            metadata["planned_start"] = planned["number"]
    
    # Job state and exit information (after completion)
    if "state" in job_data:
        metadata["state"] = {
            "current": job_data["state"].get("current"),
            "reason": job_data["state"].get("reason")
        }
    
    if "exit_code" in job_data:
        exit_code = job_data["exit_code"]
        metadata["exit_code"] = {
            "status": exit_code.get("status"),
            "return_code": exit_code.get("return_code", {}).get("number"),
            "signal_id": exit_code.get("signal", {}).get("id", {}).get("number"),
            "signal_name": exit_code.get("signal", {}).get("name")
        }
    
    # Priority
    priority = job_data.get("priority", {})
    if priority.get("set"):
        metadata["priority"] = priority.get("number")
    
    # Flags
    if job_data.get("flags"):
        metadata["flags"] = job_data["flags"]
    
    # Array job information
    if "array" in job_data:
        array_info = job_data["array"]
        if array_info.get("job_id") or array_info.get("task"):
            metadata["array"] = {
                "job_id": array_info.get("job_id"),
                "task_id": array_info.get("task_id", {}).get("number"),
                "task": array_info.get("task")
            }
            # Array limits
            if "limits" in array_info:
                metadata["array"]["limits"] = array_info["limits"]
    
    # Heterogeneous job information
    if "het" in job_data:
        het_info = job_data["het"]
        if het_info.get("job_id"):
            metadata["heterogeneous"] = {
                "job_id": het_info.get("job_id"),
                "job_offset": het_info.get("job_offset", {}).get("number")
            }
    
    # Reservation
    if "reservation" in job_data:
        res = job_data["reservation"]
        if res.get("name"):
            metadata["reservation"] = {
                "id": res.get("id"),
                "name": res.get("name")
            }
    
    # Comments
    if "comment" in job_data:
        comments = {}
        for key, value in job_data["comment"].items():
            if value:
                comments[key] = value
        if comments:
            metadata["comments"] = comments
    
    # Constraints
    if job_data.get("constraints"):
        metadata["constraints"] = job_data["constraints"]
    
    # Licenses
    if job_data.get("licenses"):
        metadata["licenses"] = job_data["licenses"]
    
    # Container
    if job_data.get("container"):
        metadata["container"] = job_data["container"]
    
    # MCS label
    if "mcs" in job_data and job_data["mcs"].get("label"):
        metadata["mcs_label"] = job_data["mcs"]["label"]
    
    # WCKey
    if "wckey" in job_data:
        wckey = job_data["wckey"]
        if wckey.get("wckey"):
            metadata["wckey"] = {
                "wckey": wckey.get("wckey"),
                "flags": wckey.get("flags")
            }
    
    # Submit line (original submission command)
    if job_data.get("submit_line"):
        metadata["submit_line"] = job_data["submit_line"]
    
    # Node assignment (if already allocated)
    if job_data.get("nodes"):
        metadata["assigned_nodes"] = job_data["nodes"]
    
    # Hold status
    if "hold" in job_data:
        metadata["hold"] = job_data["hold"]
    
    # Kill request user
    if job_data.get("kill_request_user"):
        metadata["kill_request_user"] = job_data["kill_request_user"]
    
    # Restart count
    if job_data.get("restart_cnt"):
        metadata["restart_count"] = job_data["restart_cnt"]
    
    # Input/output file information (expanded paths)
    io_info = {}
    if job_data.get("stdin_expanded"):
        io_info["stdin_expanded"] = job_data["stdin_expanded"]
    if job_data.get("stdout_expanded"):
        io_info["stdout_expanded"] = job_data["stdout_expanded"]
    if job_data.get("stderr_expanded"):
        io_info["stderr_expanded"] = job_data["stderr_expanded"]
    if io_info:
        metadata["io_expanded_paths"] = io_info
    
    # Job steps (if any were recorded)
    if job_data.get("steps"):
        metadata["steps"] = job_data["steps"]
    
    return metadata


def generate_sbatch_script(job_data):
    """Generate sbatch script content from job data."""
    params = extract_sbatch_params(job_data)
    
    script_lines = ["#!/bin/bash"]
    script_lines.append("")
    
    # Add sbatch directives
    for key, value in params.items():
        script_lines.append(f"#SBATCH --{key}={value}")
    
    script_lines.append("")
    script_lines.append("# Add your commands below")
    script_lines.append("")
    
    return "\n".join(script_lines)


def query_sacct(job_id):
    """
    Query SLURM accounting data for a specific job ID.
    Returns the JSON data or None if the query fails.
    """
    try:
        cmd = ["sacct", "--json", "-l", "-p", f"--jobs={job_id}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if result.returncode != 0:
            print(f"Warning: sacct failed for job {job_id}: {result.stderr}", file=sys.stderr)
            return None
        
        data = json.loads(result.stdout)
        return data
    
    except subprocess.CalledProcessError as e:
        print(f"Error: sacct command failed for job {job_id}: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse sacct JSON output for job {job_id}: {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: sacct command not found. Make sure SLURM is installed and in PATH.", file=sys.stderr)
        sys.exit(1)


def process_gpu_log_file(gpu_log_path, output_dir, stats):
    """
    Process a single GPU log file and generate sbatch scripts for all jobs.
    Returns the number of jobs processed.
    """
    try:
        with open(gpu_log_path, 'r') as f:
            gpu_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{gpu_log_path}' not found", file=sys.stderr)
        return 0
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{gpu_log_path}': {e}", file=sys.stderr)
        return 0
    
    # Handle both list and dict with "jobs" key
    if isinstance(gpu_data, dict) and "jobs" in gpu_data:
        gpu_entries = gpu_data["jobs"]
    elif isinstance(gpu_data, list):
        gpu_entries = gpu_data
    else:
        print(f"Warning: Unexpected JSON structure in '{gpu_log_path}'", file=sys.stderr)
        return 0
    
    jobs_processed = 0
    
    for idx, gpu_entry in enumerate(gpu_entries):
        # Extract job_id (handle both "job_id" and "vv" keys as seen in the example)
        job_id = gpu_entry.get("job_id") or gpu_entry.get("vv")
        
        if not job_id:
            print(f"Warning: No job_id found in entry {idx} of '{gpu_log_path}'", file=sys.stderr)
            continue
        
        # Skip if already processed
        if job_id in stats["processed_jobs"]:
            stats["skipped_duplicates"] += 1
            continue
        
        print(f"Processing job {job_id} from {gpu_log_path.name}...")
        
        # Query SLURM accounting data
        sacct_data = query_sacct(job_id)
        
        if not sacct_data or "jobs" not in sacct_data or not sacct_data["jobs"]:
            print(f"Warning: No SLURM data found for job {job_id}", file=sys.stderr)
            stats["failed_jobs"].append(job_id)
            continue
        
        # Process all job entries from sacct (may include array tasks or job steps)
        for slurm_job_idx, slurm_job in enumerate(sacct_data["jobs"]):
            # Generate output filename
            if len(sacct_data["jobs"]) > 1:
                output_base = output_dir / f"job_{job_id}_{slurm_job_idx}"
            else:
                output_base = output_dir / f"job_{job_id}"
            
            sbatch_file = output_base.with_suffix(".sh")
            metadata_file = output_base.with_suffix(".metadata.json")
            
            # Generate sbatch script
            sbatch_content = generate_sbatch_script(slurm_job)
            with open(sbatch_file, 'w') as f:
                f.write(sbatch_content)
            
            # Generate metadata
            metadata = extract_metadata(slurm_job)
            
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            stats["successful_jobs"] += 1
            jobs_processed += 1
        
        # Mark job as processed
        stats["processed_jobs"].add(job_id)
    
    return jobs_processed


def main():
    parser = argparse.ArgumentParser(
        description="Process GPU monitoring logs and generate sbatch scripts from SLURM accounting data"
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing GPU monitoring JSON files (results_*.json)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("./sbatch_output"),
        help="Output directory for generated sbatch scripts and metadata (default: ./sbatch_output)"
    )
    parser.add_argument(
        "-p", "--pattern",
        default="results_*.json",
        help="File pattern to match (default: results_*.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually querying sacct or generating files"
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists():
        print(f"Error: Input directory '{args.input_dir}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    if not args.input_dir.is_dir():
        print(f"Error: '{args.input_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {args.output_dir.absolute()}")
    
    # Find GPU log files
    gpu_log_files = sorted(args.input_dir.glob(args.pattern))
    
    if not gpu_log_files:
        print(f"Error: No files matching pattern '{args.pattern}' found in '{args.input_dir}'", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(gpu_log_files)} GPU log file(s) to process")
    
    # Statistics
    stats = {
        "processed_jobs": set(),
        "successful_jobs": 0,
        "failed_jobs": [],
        "skipped_duplicates": 0
    }
    
    # Process each GPU log file
    for gpu_log_file in gpu_log_files:
        print(f"\n{'='*70}")
        print(f"Processing: {gpu_log_file.name}")
        print(f"{'='*70}")
        
        if args.dry_run:
            try:
                with open(gpu_log_file, 'r') as f:
                    data = json.load(f)
                if isinstance(data, dict) and "jobs" in data:
                    entries = data["jobs"]
                elif isinstance(data, list):
                    entries = data
                else:
                    entries = []
                
                job_ids = [e.get("job_id") or e.get("vv") for e in entries if e.get("job_id") or e.get("vv")]
                print(f"Would process {len(job_ids)} job(s): {job_ids}")
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
        else:
            jobs_count = process_gpu_log_file(gpu_log_file, args.output_dir, stats)
            print(f"Processed {jobs_count} job(s) from {gpu_log_file.name}")
    
    # Print summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total unique jobs processed: {len(stats['processed_jobs'])}")
    print(f"Successful: {stats['successful_jobs']}")
    print(f"Failed: {len(stats['failed_jobs'])}")
    print(f"Skipped (duplicates): {stats['skipped_duplicates']}")
    
    if stats['failed_jobs']:
        print(f"\nFailed job IDs: {stats['failed_jobs']}")
    
    if not args.dry_run:
        print(f"\nOutput files written to: {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()