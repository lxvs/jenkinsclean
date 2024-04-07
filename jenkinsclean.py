#!/usr/bin/env python

__version__ = "0.2.0"

import os
import re
import sys
import stat
import shutil
import argparse
from pathlib import Path
from string import Template

class JenkinsClean:
    DEFAULT_FORMAT_STRING = r"Usage of $path: $used GiB / $total GiB (${percentage}%), $free GiB free"

    def __init__(
            self,
            path: Path | None = None,
            max_workspace: int | None = None,
            max_gb: float | None = None,
            max_percentage: float | None = None,
            always_preserve_pattern: str | None = None,
            always_clean_pattern: str | None = None,
            dry_run: bool = False,
            force: bool = False,
    ) -> None:
        self.path = path
        self.max_workspace = max_workspace
        self.max_gb = max_gb
        self.max_percentage = max_percentage
        self.always_preserve_pattern = always_preserve_pattern
        self.always_clean_pattern = always_clean_pattern
        self.dry_run = dry_run
        self.force = force
        self.max_size = None
        self.preserve_pattern = None
        self.clean_pattern = None
        self.__process_path()

    def path_usage(self, format_str: str | None = None) -> str:
        """
        Available format tokens are $path, $total, $used, $free, and $percentage.  Space is in GiB.
        """
        format_str = format_str or self.DEFAULT_FORMAT_STRING
        mapping = {}
        usage = shutil.disk_usage(self.path)
        mapping['path'] = self.path
        mapping['total'] = usage.total // 2**30
        mapping['used'] = usage.used // 2**30
        mapping['free'] = usage.free // 2**30
        mapping['percentage'] = 100 * usage.used // usage.total
        return Template(format_str).safe_substitute(mapping)

    def clean(self) -> None:
        self.__validate_args()
        to_clean = []
        to_preserve = []
        quota_number = self.max_workspace or None
        quota_size = self.max_size or None
        root, dirs, _ = next(self.path.walk())
        dirs_sorted = sorted(dirs, key=lambda x: os.path.getmtime(root / x), reverse=True)
        if self.clean_pattern:
            to_clean += [x for x in dirs if self.clean_pattern.search(x)]
        if self.preserve_pattern:
            if quota_size is not None:
                print("Calculating always preserved workspace size")
            for ws in dirs:
                if self.preserve_pattern.search(ws):
                    to_preserve.append(ws)
                    if ws in to_clean:
                        to_clean.remove(ws)
                    if quota_number is not None:
                        quota_number -= 1
                    if quota_size is not None:
                        quota_size -= self.size(root / ws)
        if quota_size is not None:
            print("Calculating workspace size")
        for ws in dirs_sorted:
            if ws in to_clean or ws in to_preserve:
                continue
            if quota_number is not None:
                quota_number -= 1
                if quota_number < 0:
                    print("Workspace number limit reached")
                    break
            if quota_size is not None:
                quota_size -= self.size(root / ws)
                if quota_size < 0:
                    print("Workspace size limit reached")
                    break
            to_preserve.append(ws)

        to_clean = [x for x in dirs_sorted if x not in to_preserve]

        if to_clean:
            print("Workspaces to remove:")
            for ws in to_clean:
                print(f"  {ws}")
            print()
        else:
            print("No workspace to remove")

        if to_preserve:
            print("Workspaces to preserve:")
            for ws in to_preserve:
                print(f"  {ws}")
            print()
        else:
            print("No workspace to preserve")

        for ws in to_clean:
            self.rmtree(root / ws)

    def size(self, path: Path) -> float:
        """Return the size of a directory in byte"""
        ret = 0.0
        for root, _, files in path.walk():
            ret += sum((root / f).stat().st_size for f in files)
        return ret

    def rmtree(self, path: str | Path) -> None:
        if self.dry_run or not self.force:
            return
        print("Removing", path)
        shutil.rmtree(path, onexc=self.__onexc)

    @staticmethod
    def __onexc(func, path, excinfo):
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWUSR)
            func(path)
        else:
            print(f"warning: failed to remove {path}: {excinfo}", file=sys.stderr)

    def __validate_args(self) -> None:
        if not self.dry_run and not self.force:
            raise JenkinsCleanError("neither -f nor -n given, refusing to clean")

        if self.max_gb and self.max_gb < 0:
            raise JenkinsCleanError(f"invalid max_gb: {self.max_gb}")

        if self.max_percentage and (self.max_percentage < 0 or self.max_percentage > 100):
            raise JenkinsCleanError(f"invalid max_percentage: {self.max_percentage}")

        if self.max_workspace and self.max_workspace < 0:
            raise JenkinsCleanError(f"invalid max_workspace: {self.max_workspace}")

        if self.max_gb and self.max_percentage:
            self.max_size = min(self.max_gb * 2**30, shutil.disk_usage(self.path).total * self.max_percentage // 100)
        elif self.max_gb:
            self.max_size = self.max_gb * 2**30
        elif self.max_percentage:
            self.max_size = shutil.disk_usage(self.path).total * self.max_percentage // 100

        if self.always_clean_pattern:
            self.clean_pattern = re.compile(self.always_clean_pattern)
        if self.always_preserve_pattern:
            self.preserve_pattern = re.compile(self.always_preserve_pattern)

    def __process_path(self) -> None:
        if not self.path:
            self.path = Path.cwd()
        else:
            self.path = self.path.resolve()
            if not self.path.is_dir():
                raise JenkinsCleanError(f"not a directory: {self.path}")


class JenkinsCleanError(Exception):
    pass


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
