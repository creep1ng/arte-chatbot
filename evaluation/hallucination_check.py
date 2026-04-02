#!/usr/bin/env python3
"""
Hallucination Check Script for ARTE Chatbot

This script evaluates the hallucination rate of the chatbot by analyzing
the evaluation harness output CSV. It calculates the percentage of responses
that contain fabricated information (hallucinations) based on two criteria:
1. Number of retrieved sources is zero (num_sources == 0)
2. Response contains numerical values not present in any retrieved source

Usage:
    python evaluation/hallucination_check.py --run <path_to_csv_file>
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional


def extract_numerical_values(text: str) -> List[str]:
    """
    Extract numerical values with units from text using regex.
    Pattern: \d+[\\.,]?\\d*\\s*(W|V|A|%|°C|kWh)
    
    Args:
        text: Input text to search for numerical values
        
    Returns:
        List of numerical value strings found in the text
    """
    # Regex pattern to match numerical values with common electrical/technical units
    pattern = r'\d+[\.,]?\d*\s*(?:W|V|A|%|°C|kWh)'
    # Return the full match
    full_matches = re.findall(pattern, text, re.IGNORECASE)
    return full_matches


def check_hallucination(
    response: str, 
    source_documents: str, 
    num_sources: int
) -> Tuple[bool, str, List[str]]:
    """
    Check if a response contains hallucinations.
    
    Args:
        response: The chatbot's response text
        source_documents: The retrieved source documents text
        num_sources: Number of sources retrieved
        
    Returns:
        Tuple of (is_hallucination, reason, suspicious_values)
    """
    # Criterion 1: No sources retrieved
    if num_sources == 0:
        return True, "num_sources == 0", []
    
    # Criterion 2: Check for numerical values in response not in sources
    response_numericals = extract_numerical_values(response)
    source_numericals = extract_numerical_values(source_documents)
    
    # Convert to sets for efficient lookup
    response_set: Set[str] = set(response_numericals)
    source_set: Set[str] = set(source_numericals)
    
    # Find numerical values in response that are not in sources
    suspicious_values = list(response_set - source_set)
    
    if suspicious_values:
        return True, "numerical hallucination detected", suspicious_values
    
    return False, "", []


def process_csv(csv_path: Path) -> Dict[str, Any]:
    """
    Process the CSV file and calculate hallucination metrics.
    
    Args:
        csv_path: Path to the CSV file to process
        
    Returns:
        Dictionary containing hallucination analysis results
    """
    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        sys.exit(1)
    
    total_rows = 0
    hallucination_count = 0
    suspicious_queries = []
    num_sources_sum = 0
    num_sources_count = 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            for row_num, row in enumerate(reader, start=2):  # start at 2 since header is row 1
                total_rows += 1
                
                # Extract required fields with fallbacks
                query_id = row.get('query_id', f'row_{row_num}')
                query = row.get('query', '')
                response = row.get('response', '')
                source_documents = row.get('source_documents', '')
                
                # Handle num_sources - might be string or int
                num_sources_str = row.get('num_sources', '0')
                try:
                    num_sources = int(num_sources_str)
                except ValueError:
                    print(f"Warning: Invalid num_sources value '{num_sources_str}' in row {row_num}, defaulting to 0")
                    num_sources = 0
                
                num_sources_sum += num_sources
                if num_sources > 0:
                    num_sources_count += 1
                
                # Check for hallucination
                is_hallucination, reason, suspicious_values = check_hallucination(
                    response, source_documents, num_sources
                )
                
                if is_hallucination:
                    hallucination_count += 1
                    suspicious_queries.append({
                        'query_id': query_id,
                        'query': query,
                        'response': response[:200] + '...' if len(response) > 200 else response,
                        'reason': reason,
                        'suspicious_values': suspicious_values,
                        'num_sources': num_sources
                    })
    
    except Exception as e:
        print(f"Error processing CSV file: {e}")
        sys.exit(1)
    
    # Calculate metrics
    hallucination_rate = (hallucination_count / total_rows * 100) if total_rows > 0 else 0.0
    avg_num_sources = (num_sources_sum / num_sources_count) if num_sources_count > 0 else 0.0
    
    # Prepare results
    results = {
        'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'total_queries': total_rows,
        'hallucination_count': hallucination_count,
        'hallucination_rate_percent': round(hallucination_rate, 2),
        'average_num_sources': round(avg_num_sources, 2),
        'suspicious_queries': suspicious_queries,
        'criteria': [
            'num_sources == 0',
            'numerical values in response not found in source_documents (regex: \\d+[\\.,]?\\d*\\s*(W|V|A|%|°C|kWh))'
        ]
    }
    
    return results


def save_results(results: Dict[str, Any], output_dir: Path) -> Path:
    """
    Save results to JSON file.
    
    Args:
        results: Dictionary containing results to save
        output_dir: Directory to save the results file
        
    Returns:
        Path to the saved results file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"hallucination_{timestamp}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return output_path


def upload_to_s3(file_path: Path, s3_key: str) -> bool:
    """
    Upload a file to S3 using boto3 directly.

    Reads AWS credentials from environment variables:
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - AWS_BUCKET_NAME
      - AWS_REGION (defaults to us-east-1)

    Args:
        file_path: Local path to the file to upload.
        s3_key: S3 key (path) where the file should be stored.

    Returns:
        True if upload successful, False otherwise.
    """
    import os

    try:
        import boto3
    except ImportError:
        print("✗ boto3 is not installed. Run: uv pip install boto3")
        return False

    bucket_name = os.getenv("AWS_BUCKET_NAME")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")

    if not all([bucket_name, access_key, secret_key]):
        print(
            "✗ AWS credentials or bucket name not set. "
            "Define AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_BUCKET_NAME."
        )
        return False

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        with open(file_path, "rb") as f:
            s3.put_object(Bucket=bucket_name, Key=s3_key, Body=f.read())

        print(f"✓ Uploaded {file_path} to s3://{bucket_name}/{s3_key}")
        return True

    except Exception as e:
        print(f"✗ Failed to upload to S3: {e}")
        return False


def main() -> None:
    """Main entry point for the hallucination check script."""
    parser = argparse.ArgumentParser(
        description="Check hallucination rate in ARTE Chatbot evaluation results"
    )
    parser.add_argument(
        '--run',
        required=True,
        help='Path to the CSV file generated by the evaluation harness'
    )
    parser.add_argument(
        '--output-dir',
        default='evaluation/results',
        help='Directory to save the hallucination report (default: evaluation/results)'
    )
    parser.add_argument(
        '--upload-s3',
        action='store_true',
        help='Upload results to S3 bucket'
    )
    
    args = parser.parse_args()
    
    csv_path = Path(args.run)
    output_dir = Path(args.output_dir)
    
    print("=" * 60)
    print("ARTE Chatbot Hallucination Check")
    print("=" * 60)
    print(f"Processing CSV: {csv_path}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Process the CSV
    results = process_csv(csv_path)
    
    # Save results
    output_path = save_results(results, output_dir)
    
    # Print summary
    print(f"Total queries processed: {results['total_queries']}")
    print(f"Hallucinations detected: {results['hallucination_count']}")
    print(f"Hallucination rate: {results['hallucination_rate_percent']}%")
    print(f"Average number of sources: {results['average_num_sources']}")
    print()
    print(f"Results saved to: {output_path}")
    print()
    
    # Check if hallucination rate meets criteria (< 20%)
    if results['hallucination_rate_percent'] < 20.0:
        print("[PASS] Hallucination rate is below 20% threshold (meets US-07 criteria)")
    else:
        print("[FAIL] Hallucination rate exceeds 20% threshold (does not meet US-07 criteria)")
    
    # Upload to S3 if requested
    if args.upload_s3:
        print()
        print("Uploading results to S3...")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        s3_key = f"evaluation/hallucination_reports/hallucination_{timestamp}.json"
        upload_to_s3(output_path, s3_key)
    
    print("=" * 60)


if __name__ == "__main__":
    main()
