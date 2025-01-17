#!/usr/bin/env python

import sys
import shutil
import argparse
from pathlib import Path
from string import Template

from jenkinsclean import JenkinsClean, JenkinsCleanError, __version__

DEFAULT_FORMAT_STRING = r"Usage of $path: $used GiB / $total GiB (${percentage}%), $free GiB free"

def path_usage(path: Path | None = None, format_str: str | None = None) -> str:
    """
    Available format tokens are $path, $total, $used, $free, and $percentage.  Space is in GiB.
    """
    path = path or Path.cwd()
    format_str = format_str or DEFAULT_FORMAT_STRING
    mapping = {}
    usage = shutil.disk_usage(path)
    mapping['path'] = path
    mapping['total'] = usage.total // 2**30
    mapping['used'] = usage.used // 2**30
    mapping['free'] = usage.free // 2**30
    mapping['percentage'] = 100 * usage.used // usage.total
    return Template(format_str).safe_substitute(mapping)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Clean up Jenkins workspaces",
    )
    parser.add_argument(
        '-V',
        '--version',
        action='version',
        version=__version__,
    )
    parser.add_argument(
        'path',
        nargs='?',
        help="path to parent of workspace directories (default: current directory)",
    )
    parser.add_argument(
        '-m',
        '--max-workspace',
        type=int,
        help="max number of workspace directories to be preserved",
    )
    parser.add_argument(
        '-s',
        '--max-gb',
        type=float,
        help="max number of GiB allowed for all preserved workspace",
    )
    parser.add_argument(
        '-r',
        '--max-percentage',
        type=float,
        help="max percentage of disk space allowed for preserved workspace",
    )
    parser.add_argument(
        '--target-gb',
        type=float,
        help="Target GiB after cleaning",
    )
    parser.add_argument(
        '--target-percentage',
        type=float,
        help="target percentage of disk space after cleaning",
    )
    parser.add_argument(
        '-p',
        '--always-preserve-pattern',
        help="regex pattern of directory names to be always preserved",
    )
    parser.add_argument(
        '-c',
        '--always-clean-pattern',
        help="regex pattern for directory names to be always cleaned up",
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help="force",
    )
    parser.add_argument(
        '-n',
        '--dry-run',
        action='store_true',
        help="dry run",
    )
    parser.add_argument(
        '-u',
        '--disk-usage',
        metavar='FORMAT',
        action='store',
        nargs='?',
        const=DEFAULT_FORMAT_STRING,
        help="Print a formatted string of disk usage and exit.  Available format tokens are $path, $total, $used, $free, and $percentage.  Space is in GiB.",
    )
    parser.add_argument(
        '-q',
        '--quiet',
        action='store_true',
        help="Only print errors and warnings",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    path = Path(args.path) if args.path else None
    jc = JenkinsClean(
        path=path,
        max_workspace=args.max_workspace,
        max_gb=args.max_gb,
        max_percentage=args.max_percentage,
        target_gb=args.target_gb,
        target_percentage=args.target_percentage,
        always_preserve_pattern=args.always_preserve_pattern,
        always_clean_pattern=args.always_clean_pattern,
        dry_run=args.dry_run,
        force=args.force,
        quiet=args.quiet,
    )

    disk_usage: str | None = args.disk_usage

    if disk_usage:
        print(path_usage(path, disk_usage))
        return

    jc.clean()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Abort.", file=sys.stderr)
    except JenkinsCleanError as error:
        print("error:", error, file=sys.stderr)
        sys.exit(1)
