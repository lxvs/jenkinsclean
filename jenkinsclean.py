__version__ = "0.4.0"

import os
import re
import stat
import shutil
import logging
from pathlib import Path

class JenkinsClean:

    def __init__(
            self,
            path: Path | None = None,
            max_workspace: int | None = None,
            max_gb: float | None = None,
            max_percentage: float | None = None,
            target_gb: float | None = None,
            target_percentage: float | None = None,
            always_preserve_pattern: str | None = None,
            always_clean_pattern: str | None = None,
            dry_run: bool = False,
            force: bool = False,
            quiet: bool = False,
    ) -> None:
        self.path = path
        self.max_workspace = max_workspace
        self.max_gb = max_gb
        self.max_percentage = max_percentage
        self.target_gb = target_gb
        self.target_percentage = target_percentage
        self.always_preserve_pattern = always_preserve_pattern
        self.always_clean_pattern = always_clean_pattern
        self.dry_run = dry_run
        self.force = force
        self.max_size = None
        self.target_size = None
        self.preserve_pattern = None
        self.clean_pattern = None
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        if quiet:
            self.logger.setLevel(logging.WARNING)
        self.__process_path()

    def clean(self) -> None:
        self.__validate_args()
        to_clean = []
        to_preserve = []
        quota_number = self.max_workspace or None
        quota_size = None
        if self.max_size and self.max_size < shutil.disk_usage(self.path).used:
            quota_size = self.target_size or self.max_size
        if self.max_gb:
            self.logger.info("Size limit:             %s", self.proper_size(self.max_gb * 2**30))
        if self.target_gb:
            self.logger.info("Target size:            %s", self.proper_size(self.target_gb * 2**30))
        if self.max_percentage:
            self.logger.info("Percentage limit:       %s%%", self.max_percentage)
        if self.target_percentage:
            self.logger.info("Target percentage:      %s%%", self.target_percentage)
        if self.max_workspace:
            self.logger.info("Workspace number limit: %s", self.max_workspace)
        if self.max_size:
            self.logger.info("Actual size limit:      %s", self.proper_size(self.max_size))
        if quota_size:
            self.logger.info("Actual size target:     %s", self.proper_size(quota_size))
        root, dirs, _ = next(self.path.walk())
        self.logger.info("Sorting")
        dirs_sorted = sorted(dirs, key=lambda x: os.path.getmtime(root / x), reverse=True)
        self.logger.info("Scanning")
        if self.clean_pattern:
            to_clean += [x for x in dirs if self.clean_pattern.search(x)]
        if self.preserve_pattern:
            if quota_size is not None:
                self.logger.info("Calculating always preserved workspace size")
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
            self.logger.info("Calculating workspace size")
        for ws in dirs_sorted:
            if ws in to_clean or ws in to_preserve:
                continue
            if quota_number is not None:
                quota_number -= 1
                if quota_number < 0:
                    self.logger.info("Workspace number limit reached")
                    break
            if quota_size is not None:
                quota_size -= self.size(root / ws)
                if quota_size < 0:
                    self.logger.info("Workspace size limit reached")
                    break
            to_preserve.append(ws)

        to_clean = [x for x in dirs_sorted if x not in to_preserve]

        self.report(to_clean, "clean")
        self.report(to_preserve, "preserve")

        for ws in to_clean:
            self.rmtree(root / ws)

    def proper_size(self, size: float) -> str:
        """Return a human readable size"""
        units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
        for unit in units:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} {units[-1]}"

    def report(self, ws: list, to: str) -> None:
        sep = '\n  '
        if ws:
            self.logger.info("Workspaces to %s:%s%s", to, sep, sep.join(ws))
        else:
            self.logger.info("No workspace to %s", to)

    def size(self, path: Path) -> float:
        """Return the size of a directory in byte"""
        ret = 0.0
        for root, _, files in path.walk():
            ret += sum((root / f).stat().st_size for f in files)
        return ret

    def rmtree(self, path: str | Path) -> None:
        if self.dry_run or not self.force:
            return
        self.logger.info("Removing %s", str(path))
        shutil.rmtree(path, onexc=self.__onexc)

    def __onexc(self, func, path, excinfo):
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWUSR)
            func(path)
        else:
            self.logger.warning("warning: failed to remove %s: %s", path, excinfo)

    def __validate_args(self) -> None:
        if not self.dry_run and not self.force:
            raise JenkinsCleanError("neither -f nor -n given, refusing to clean")

        if self.max_gb and self.max_gb < 0:
            raise JenkinsCleanError(f"invalid max_gb: {self.max_gb}")

        if self.max_percentage and (self.max_percentage < 0 or self.max_percentage > 100):
            raise JenkinsCleanError(f"invalid max_percentage: {self.max_percentage}")

        if self.max_workspace and self.max_workspace < 0:
            raise JenkinsCleanError(f"invalid max_workspace: {self.max_workspace}")

        if self.target_gb and self.target_gb < 0:
            raise JenkinsCleanError(f"invalid target_gb: {self.target_gb}")

        if self.target_percentage and (self.target_percentage < 0 or self.target_percentage > 100):
            raise JenkinsCleanError(f"invalid target_percentage: {self.target_percentage}")

        if self.max_gb and self.max_percentage:
            self.max_size = min(self.max_gb * 2**30, shutil.disk_usage(self.path).total * self.max_percentage // 100)
        elif self.max_gb:
            self.max_size = self.max_gb * 2**30
        elif self.max_percentage:
            self.max_size = shutil.disk_usage(self.path).total * self.max_percentage // 100
        elif self.max_workspace is None:
            self.logger.warning("warning: no limit specified, will not clean")

        if self.target_gb and self.target_percentage:
            self.target_size = min(self.target_gb * 2**30, shutil.disk_usage(self.path).total * self.target_percentage // 100)
        elif self.target_gb:
            self.target_size = self.target_gb * 2**30
        elif self.target_percentage:
            self.target_size = shutil.disk_usage(self.path).total * self.target_percentage // 100

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
