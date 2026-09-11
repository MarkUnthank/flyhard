"""Unreal command-line settings for the current Pod's shader compiler."""
import os
from pathlib import Path


def main():
    available = len(os.sched_getaffinity(0))
    requested = int(os.environ.get('FLYHARD_BUILD_JOBS', '16'))
    if requested < 1:
        raise ValueError('FLYHARD_BUILD_JOBS must be positive')
    workers = min(available, requested)
    quota_file = Path('/sys/fs/cgroup/cpu.max')
    if quota_file.exists():
        quota, period = quota_file.read_text().split()
        if quota != 'max':
            workers = min(workers, max(1, int(quota) // int(period)))
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
