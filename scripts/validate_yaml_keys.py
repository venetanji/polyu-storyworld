#!/usr/bin/env python3
"""
YAML Validation and Key Collection Script

This script:
1. Scans the repository for YAML files (excluding .git and .github/workflows)
2. Validates YAML syntax and records parse errors
3. Extracts all keys in dot-notation and counts occurrences
4. Generates a repository-wide key count mapping
5. For each open PR, analyzes YAML changes and posts a summary comment
"""

import os
import sys
import yaml
import json
import requests
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Any


def extract_keys(data: Any, prefix: str = '') -> Dict[str, int]:
    """
    Extract all keys from a YAML structure in dot-notation.
    For lists, use prefix[] notation and count each occurrence.
    Returns a dict mapping key paths to their count.
    """
    key_counts = defaultdict(int)
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{prefix}.{key}" if prefix else key
            key_counts[current_path] += 1
            
            # Recursively process nested structures
            nested_counts = extract_keys(value, current_path)
            for nested_key, count in nested_counts.items():
                key_counts[nested_key] += count
    
    elif isinstance(data, list):
        # Mark that this path is a list
        list_path = f"{prefix}[]" if prefix else "[]"
        key_counts[list_path] += 1
        
        # Process each list element
        for item in data:
            nested_counts = extract_keys(item, prefix)
            for nested_key, count in nested_counts.items():
                key_counts[nested_key] += count
    
    return key_counts


def find_yaml_files(root_dir: str) -> List[Path]:
    """
    Find all YAML files in the repository, excluding .git and .github/workflows.
    """
    yaml_files = []
    root_path = Path(root_dir)
    
    for pattern in ['**/*.yml', '**/*.yaml']:
        for file_path in root_path.glob(pattern):
            # Skip .git directory
            if '.git' in file_path.parts:
                continue
            
            # Skip .github/workflows directory
            if '.github' in file_path.parts and 'workflows' in file_path.parts:
                continue
            
            yaml_files.append(file_path)
    
    return sorted(yaml_files)


def parse_yaml_file(file_path: Path) -> Tuple[List[Any], List[str]]:
    """
    Parse a YAML file using safe_load_all.
    Returns (list of documents, list of error messages).
    """
    documents = []
    errors = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Try to parse all documents in the file
        try:
            for doc in yaml.safe_load_all(content):
                if doc is not None:
                    documents.append(doc)
        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {str(e)}")
    
    except Exception as e:
        errors.append(f"File read error: {str(e)}")
    
    return documents, errors


def scan_repository(root_dir: str) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    """
    Scan all YAML files in the repository.
    Returns (key_counts, file_errors).
    """
    yaml_files = find_yaml_files(root_dir)
    print(f"Found {len(yaml_files)} YAML files to scan")
    
    all_key_counts = defaultdict(int)
    file_errors = {}
    
    for file_path in yaml_files:
        relative_path = str(file_path.relative_to(root_dir))
        documents, errors = parse_yaml_file(file_path)
        
        if errors:
            file_errors[relative_path] = errors
            print(f"❌ {relative_path}: {len(errors)} error(s)")
        else:
            print(f"✅ {relative_path}: {len(documents)} document(s)")
        
        # Extract keys from all documents
        for doc in documents:
            key_counts = extract_keys(doc)
            for key, count in key_counts.items():
                all_key_counts[key] += count
    
    return dict(all_key_counts), file_errors


def write_key_counts(key_counts: Dict[str, int], output_file: str):
    """
    Write key counts to output file in format: count<TAB>key
    Sorted by descending count, then by key name.
    """
    # Sort by count (descending) then by key (ascending)
    sorted_items = sorted(key_counts.items(), key=lambda x: (-x[1], x[0]))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for key, count in sorted_items:
            f.write(f"{count}\t{key}\n")
    
    print(f"\n✅ Wrote {len(sorted_items)} unique keys to {output_file}")


def get_open_prs(github_token: str, repo: str) -> List[Dict]:
    """
    Get all open pull requests for the repository.
    """
    if not github_token:
        return []
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    url = f'https://api.github.com/repos/{repo}/pulls'
    params = {'state': 'open', 'per_page': 100}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️  Error fetching PRs: {e}")
        return []


def get_pr_files(github_token: str, repo: str, pr_number: int) -> List[Dict]:
    """
    Get files changed in a pull request.
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    url = f'https://api.github.com/repos/{repo}/pulls/{pr_number}/files'
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️  Error fetching PR files: {e}")
        return []


def fetch_file_content(raw_url: str, github_token: str) -> str:
    """
    Fetch raw file content from GitHub.
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3.raw'
    }
    
    try:
        response = requests.get(raw_url, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"⚠️  Error fetching file content: {e}")
        return ""


def analyze_pr_yaml_files(github_token: str, repo: str, pr_number: int) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    """
    Analyze YAML files changed in a PR.
    Returns (pr_key_counts, pr_file_errors).
    """
    pr_files = get_pr_files(github_token, repo, pr_number)
    
    pr_key_counts = defaultdict(int)
    pr_file_errors = {}
    
    for file_info in pr_files:
        filename = file_info['filename']
        
        # Only process YAML files
        if not (filename.endswith('.yml') or filename.endswith('.yaml')):
            continue
        
        # Skip .github/workflows
        if '.github/workflows' in filename:
            continue
        
        # Skip deleted files
        if file_info['status'] == 'removed':
            continue
        
        # Fetch file content
        raw_url = file_info.get('raw_url', '')
        if not raw_url:
            continue
        
        content = fetch_file_content(raw_url, github_token)
        if not content:
            pr_file_errors[filename] = ["Could not fetch file content"]
            continue
        
        # Parse YAML
        documents = []
        errors = []
        try:
            for doc in yaml.safe_load_all(content):
                if doc is not None:
                    documents.append(doc)
        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {str(e)}")
        
        if errors:
            pr_file_errors[filename] = errors
        
        # Extract keys
        for doc in documents:
            key_counts = extract_keys(doc)
            for key, count in key_counts.items():
                pr_key_counts[key] += count
    
    return dict(pr_key_counts), pr_file_errors


def build_pr_comment(
    pr_number: int,
    pr_key_counts: Dict[str, int],
    repo_key_counts: Dict[str, int],
    pr_file_errors: Dict[str, List[str]]
) -> str:
    """
    Build a comment summarizing the PR's YAML validation and key impact.
    """
    lines = []
    lines.append("## YAML Validation Report")
    lines.append("")
    
    # Validation results
    if pr_file_errors:
        lines.append("### ❌ Validation Errors")
        lines.append("")
        for filename, errors in pr_file_errors.items():
            lines.append(f"**{filename}**")
            for error in errors:
                lines.append(f"- {error}")
            lines.append("")
    else:
        lines.append("### ✅ All YAML Files Valid")
        lines.append("")
    
    # Key counts in PR
    if pr_key_counts:
        lines.append("### 📊 Keys in This PR")
        lines.append("")
        lines.append(f"Total unique keys: {len(pr_key_counts)}")
        lines.append("")
        
        # Sort by count (descending) then key
        sorted_pr_keys = sorted(pr_key_counts.items(), key=lambda x: (-x[1], x[0]))
        
        lines.append("<details>")
        lines.append("<summary>View all keys (click to expand)</summary>")
        lines.append("")
        lines.append("| Key | Count in PR |")
        lines.append("|-----|-------------|")
        for key, count in sorted_pr_keys:
            lines.append(f"| `{key}` | {count} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")
        
        # New keys and count increases
        new_keys = []
        increased_keys = []
        
        for key, pr_count in pr_key_counts.items():
            repo_count = repo_key_counts.get(key, 0)
            if repo_count == 0:
                new_keys.append(key)
            elif pr_count > 0:
                new_total = repo_count + pr_count
                increased_keys.append((key, repo_count, pr_count, new_total))
        
        if new_keys:
            lines.append("### 🆕 New Keys Introduced")
            lines.append("")
            for key in sorted(new_keys):
                pr_count = pr_key_counts[key]
                lines.append(f"- `{key}` (count: {pr_count})")
            lines.append("")
        
        if increased_keys:
            lines.append("### 📈 Keys with Increased Counts")
            lines.append("")
            lines.append("| Key | Repo Count | PR Count | New Total |")
            lines.append("|-----|------------|----------|-----------|")
            for key, repo_count, pr_count, new_total in sorted(increased_keys, key=lambda x: -x[2]):
                lines.append(f"| `{key}` | {repo_count} | +{pr_count} | {new_total} |")
            lines.append("")
    
    lines.append("---")
    lines.append("*Generated by YAML validation workflow*")
    
    return "\n".join(lines)


def post_pr_comment(github_token: str, repo: str, pr_number: int, comment_body: str):
    """
    Post a comment on a pull request.
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    url = f'https://api.github.com/repos/{repo}/issues/{pr_number}/comments'
    data = {'body': comment_body}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"✅ Posted comment on PR #{pr_number}")
    except Exception as e:
        print(f"⚠️  Error posting comment on PR #{pr_number}: {e}")


def process_pull_requests(github_token: str, repo: str, repo_key_counts: Dict[str, int]):
    """
    Process all open PRs and post validation comments.
    """
    if not github_token:
        print("\n⚠️  GITHUB_TOKEN not provided, skipping PR comments")
        return
    
    if not repo:
        print("\n⚠️  Repository name not available, skipping PR comments")
        return
    
    prs = get_open_prs(github_token, repo)
    print(f"\n📋 Found {len(prs)} open PR(s)")
    
    for pr in prs:
        pr_number = pr['number']
        pr_title = pr['title']
        print(f"\n🔍 Analyzing PR #{pr_number}: {pr_title}")
        
        pr_key_counts, pr_file_errors = analyze_pr_yaml_files(github_token, repo, pr_number)
        
        comment = build_pr_comment(pr_number, pr_key_counts, repo_key_counts, pr_file_errors)
        post_pr_comment(github_token, repo, pr_number, comment)


def main():
    """
    Main execution function.
    """
    # Get configuration
    github_token = os.environ.get('GITHUB_TOKEN', '')
    
    # Try to determine repository from environment or git
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if not repo:
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'config', '--get', 'remote.origin.url'],
                capture_output=True,
                text=True,
                check=True
            )
            origin_url = result.stdout.strip()
            # Parse repo from URL (e.g., https://github.com/owner/repo.git)
            if 'github.com' in origin_url:
                parts = origin_url.split('github.com')[-1].strip('/:').replace('.git', '')
                repo = parts
        except:
            pass
    
    if not repo:
        print("⚠️  Could not determine repository name from GITHUB_REPOSITORY or git remote")
        print("    Repository name is required for posting PR comments")
        print("    Continuing with key collection only...")
    
    print(f"Repository: {repo}")
    print(f"GitHub Token: {'✅ Available' if github_token else '❌ Not available'}")
    print("="*80)
    
    # Scan repository
    print("\n📂 Scanning repository for YAML files...")
    repo_key_counts, file_errors = scan_repository('.')
    
    # Print summary
    print("\n" + "="*80)
    print(f"📊 Repository Statistics:")
    print(f"  - Total unique keys: {len(repo_key_counts)}")
    print(f"  - Files with errors: {len(file_errors)}")
    
    if file_errors:
        print("\n❌ Files with parse errors:")
        for filename, errors in file_errors.items():
            print(f"  - {filename}: {len(errors)} error(s)")
    
    # Write key counts to file
    output_file = 'unique_keys_counts.txt'
    write_key_counts(repo_key_counts, output_file)
    
    # Process pull requests
    process_pull_requests(github_token, repo, repo_key_counts)
    
    print("\n" + "="*80)
    print("✅ Script completed successfully")
    print("="*80)
    
    # Exit with 0 even if there were parse errors
    sys.exit(0)


if __name__ == '__main__':
    main()
