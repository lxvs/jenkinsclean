__version__ = "0.3.0"

import os
import re
import sys
import stat
import shutil
from pathlib import Path

class JenkinsClean:

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

    def clean(self) -> None:
        self.__validate_args()
        to_clean = []
        to_preserve = []
        quota_number = self.max_workspace or None
        quota_size = None
        if self.max_size and self.max_size < shutil.disk_usage(self.path).used:
            quota_size = self.max_size
        root, dirs, _ = next(self.path.walk())
        dirs_sorted = sorted(dirs, key=lambda x: os.path.getmtime(root / x), reverse=True)
        if self.clean_pattern:
            to_clean += [x for x in dirs if self.clean_pattern.search(x)]
        if self.preserve_pattern:
            if quota_size is not None:
                print("Calculating always preserved workspace size", flush=True)
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
            print("Calculating workspace size", flush=True)
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

        self.report(to_clean, "clean")
        self.report(to_preserve, "preserve")

        for ws in to_clean:
            self.rmtree(root / ws)

    @staticmethod
    def report(ws: list, to: str) -> None:
        sep = '\n  '
        if ws:
            print(f"Workspaces to {to}:{sep}", sep.join(ws), '\n', sep='', flush=True)
        else:
            print(f"No workspace to {to}", flush=True)

    def size(self, path: Path) -> float:
        """Return the size of a directory in byte"""
        ret = 0.0
        for root, _, files in path.walk():
            ret += sum((root / f).stat().st_size for f in files)
        return ret

    def rmtree(self, path: str | Path) -> None:
        if self.dry_run or not self.force:
            return
        print("Removing", path, flush=True)
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
