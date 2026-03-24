#!/usr/bin/env python3
"""
Generate Catalog Index Script

This script reads PDF files from an S3 bucket (or local directory for development)
and generates a catalog_index.json file with metadata extracted from filenames.

Usage:
    python generate_index.py                              # Use S3 defaults
    python generate_index.py --source-dir ./data           # Local development
    python generate_index.py --bucket my-custom-bucket    # Custom S3 bucket
    python generate_index.py --output custom_index.json   # Custom output path

The script is idempotent: running it multiple times produces the same result.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Try to import boto3, fall back to mock for development without AWS credentials
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore
    NoCredentialsError = Exception  # type: ignore

# Default configuration
DEFAULT_BUCKET = "arte-chatbot-data"
DEFAULT_PREFIX = "raw/"
DEFAULT_OUTPUT_S3 = "catalog_index.json"
DEFAULT_OUTPUT_LOCAL = "backend/config/catalog_index.json"

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".PDF"}


def parse_filename(filename: str) -> dict[str, str]:
    """
    Extract metadata from filename.
    
    Expected format: {categoria}-{marca}-{modelo}.pdf
    Example: panel-solar-jinko-JKM540N-54HL4.pdf
    
    Returns:
        dict with 'nombre', 'categoria', 'marca', 'modelo'
    """
    # Remove extension
    name_without_ext = Path(filename).stem
    
    # Split by hyphen
    parts = name_without_ext.split("-")
    
    result: dict[str, str] = {
        "nombre": filename,
        "categoria": "",
        "marca": "",
        "modelo": name_without_ext,  # Default to full name
    }
    
    if len(parts) >= 1:
        result["categoria"] = parts[0]
    if len(parts) >= 2:
        result["marca"] = parts[1]
    if len(parts) >= 3:
        # Join remaining parts as model (may contain hyphens)
        result["modelo"] = "-".join(parts[2:])
    
    return result


def list_s3_files(bucket: str, prefix: str = DEFAULT_PREFIX) -> list[str]:
    """
    List PDF files from S3 bucket.
    
    Args:
        bucket: S3 bucket name
        prefix: S3 prefix (folder) to search in
        
    Returns:
        List of S3 keys (file paths) for PDF files
    """
    if not BOTO3_AVAILABLE:
        print("Warning: boto3 not available. Using mock data for testing.")
        return []
    
    try:
        s3_client = boto3.client("s3")
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        files = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                # Check if it's a PDF
                if any(key.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    files.append(key)
        
        return files
    except NoCredentialsError:
        print("Warning: No AWS credentials found. Using mock data for testing.")
        return []
    except ClientError as e:
        print(f"Error accessing S3: {e}")
        return []


def list_local_files(source_dir: str) -> list[str]:
    """
    List PDF files from local directory.
    
    Args:
        source_dir: Local directory path
        
    Returns:
        List of file paths for PDF files
    """
    dir_path = Path(source_dir)
    
    if not dir_path.exists():
        print(f"Warning: Source directory '{source_dir}' does not exist.")
        return []
    
    files = []
    for file_path in dir_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in SUPPORTED_EXTENSIONS:
            files.append(str(file_path))
    
    return files


def generate_catalog_index(
    files: list[str],
    source_type: str = "s3",
    bucket: str = DEFAULT_BUCKET,
    base_path: str = "",
) -> list[dict[str, Any]]:
    """
    Generate catalog index from file list.
    
    Args:
        files: List of file paths (S3 keys or local paths)
        source_type: 's3' or 'local'
        bucket: S3 bucket name (for S3 paths)
        base_path: Base path for local files
        
    Returns:
        List of catalog entries
    """
    catalog: list[dict[str, Any]] = []
    
    for file_path in files:
        # Parse filename for metadata
        filename = os.path.basename(file_path)
        metadata = parse_filename(filename)
        
        # Build the S3 path
        if source_type == "s3":
            s3_path = f"s3://{bucket}/{file_path}"
        else:
            # For local files, use absolute path
            s3_path = f"file://{os.path.abspath(file_path)}"
        
        entry = {
            "nombre": metadata["nombre"],
            "categoria": metadata["categoria"],
            "ruta_s3": s3_path,
            # Include additional metadata for reference
            "marca": metadata["marca"],
            "modelo": metadata["modelo"],
        }
        
        catalog.append(entry)
    
    # Sort by category then by nombre for consistency (idempotency)
    catalog.sort(key=lambda x: (x["categoria"], x["nombre"]))
    
    return catalog


def save_catalog_index(catalog: list[dict[str, Any]], output_path: str) -> None:
    """
    Save catalog index to JSON file.
    
    Args:
        catalog: Catalog entries list
        output_path: Output file path
    """
    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write JSON with sorted keys for idempotency
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    print(f"Catalog index saved to: {output_path}")
    print(f"Total entries: {len(catalog)}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate catalog index from PDF files in S3 or local directory."
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=None,
        help="Local directory containing PDF files (for development without S3)",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=DEFAULT_BUCKET,
        help=f"S3 bucket name (default: {DEFAULT_BUCKET})",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=DEFAULT_PREFIX,
        help=f"S3 prefix/folder to search in (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=f"Output path for catalog_index.json (default: {DEFAULT_OUTPUT_LOCAL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually creating files",
    )
    
    args = parser.parse_args()
    
    # Determine source type and output path
    if args.source_dir:
        source_type = "local"
        files = list_local_files(args.source_dir)
        output_path = args.output or DEFAULT_OUTPUT_LOCAL
        print(f"Using local source directory: {args.source_dir}")
    else:
        source_type = "s3"
        files = list_s3_files(args.bucket, args.prefix)
        output_path = args.output or DEFAULT_OUTPUT_LOCAL
        print(f"Using S3 bucket: {args.bucket}/{args.prefix}")
    
    if not files:
        print("No PDF files found.")
        # Generate empty catalog for idempotency
        catalog = []
    else:
        print(f"Found {len(files)} PDF files")
        
        # Generate catalog index
        catalog = generate_catalog_index(
            files,
            source_type=source_type,
            bucket=args.bucket if source_type == "s3" else "",
            base_path=args.source_dir or "",
        )
    
    if args.dry_run:
        print("\n--- Dry Run: Would generate the following catalog ---")
        print(json.dumps(catalog, indent=2, ensure_ascii=False))
        print(f"\nWould save to: {output_path}")
        return 0
    
    # Save catalog index
    save_catalog_index(catalog, output_path)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())