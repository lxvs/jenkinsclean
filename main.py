#!/usr/bin/env python

import sys
import argparse
from pathlib import Path

from jenkinsclean import JenkinsClean, JenkinsCleanError, __version__

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
        const=JenkinsClean.DEFAULT_FORMAT_STRING,
        help="Print a formatted string of disk usage and exit.  Available format tokens are $path, $total, $used, $free, and $percentage.  Space is in GiB.",
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
        always_preserve_pattern=args.always_preserve_pattern,
        always_clean_pattern=args.always_clean_pattern,
        dry_run=args.dry_run,
        force=args.force,
    )

    disk_usage: str | None = args.disk_usage

    if disk_usage:
        print(jc.path_usage(disk_usage))
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
