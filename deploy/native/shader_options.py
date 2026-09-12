"""Unreal command-line settings for the current Pod's shader compiler."""
import os
from pathlib import Path


def quota_workers(available):
    """Return the CPU quota visible to this process on cgroup v1 or v2."""
    v2 = Path('/sys/fs/cgroup/cpu.max')
    if v2.is_file():
        fields = v2.read_text().split()
        if len(fields) != 2:
            raise RuntimeError('Malformed cgroup v2 cpu.max; cannot size shader workers')
        quota, period = fields
        if quota == 'max':
            return available
        try:
            return max(1, int(quota) // int(period))
        except ValueError as exc:
            raise RuntimeError('Malformed cgroup v2 CPU quota; cannot size shader workers') from exc

    quota_path = Path('/sys/fs/cgroup/cpu/cpu.cfs_quota_us')
    period_path = Path('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
    if quota_path.is_file() or period_path.is_file():
        if not quota_path.is_file() or not period_path.is_file():
            raise RuntimeError('Incomplete cgroup v1 CPU quota; cannot size shader workers')
        try:
            quota, period = int(quota_path.read_text()), int(period_path.read_text())
        except ValueError as exc:
            raise RuntimeError('Malformed cgroup v1 CPU quota; cannot size shader workers') from exc
        if quota < 0:
            return available
        if period <= 0:
            raise RuntimeError('Invalid cgroup v1 CPU quota period; cannot size shader workers')
        return max(1, quota // period)
    return available


def main():
    available = len(os.sched_getaffinity(0))
    requested = int(os.environ.get('FLYHARD_BUILD_JOBS', '16'))
    if requested < 1:
        raise ValueError('FLYHARD_BUILD_JOBS must be positive')
    workers = min(available, requested)
    workers = min(workers, quota_workers(available))
    unused = available - workers
    scratch = Path('/tmp') / ('flyhard-shader-work-' + str(os.getuid()))
    scratch.mkdir(exist_ok=True)
    print(' '.join([
        '-ShaderWorkingDir=' + str(scratch) + '/',
        '-ini:Engine:[DevOptions.Shaders]:NumUnusedShaderCompilingThreads=' + str(unused)
        + ',[DevOptions.Shaders]:NumUnusedShaderCompilingThreadsDuringGame=' + str(unused),
        '-DisablePlugins=USDImporter', '-stdout', '-FullStdOutLogOutput',
    ]))


if __name__ == '__main__':
    main()
