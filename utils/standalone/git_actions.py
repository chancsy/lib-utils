"""Thin subprocess wrappers for driving git as an action against an arbitrary repo path.

Distinct from ``get_git_info()`` in ``utils._internal.util_runtime`` (read-only info,
via the ``python-git-info`` package, about the *currently running* repo) - these
functions operate on any repo path passed in, for scripts that manage other repos
(e.g. propagating updates between a git remote, a shared-drive mirror, and local
clones).

Typical usage::

    from utils.standalone.git_actions import git_fetch, git_pull, git_has_uncommitted_changes

    git_fetch('path/to/repo', 'main')
    if not git_has_uncommitted_changes('path/to/repo'):
        git_pull('path/to/repo')
"""

import subprocess


def _run_git(args, check=True):
    """Run ``git <args>`` and return stripped stdout; raises RuntimeError on failure if check=True."""
    result = subprocess.run(['git', *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_clone_bare(remote_url, dest_path):
    """Bare-clone ``remote_url`` to ``dest_path`` (dest_path must not already exist)."""
    _run_git(['clone', '--bare', remote_url, str(dest_path)])


def git_fetch(repo_path, branch, remote='origin'):
    """Fetch ``branch`` from ``remote`` into the local ``branch`` ref (force-updates it)."""
    _run_git(['-C', str(repo_path), 'fetch', remote, f'+{branch}:{branch}'])


def git_last_commit_info(repo_path, branch):
    """Return ``'<YYYYMMDD_HHMM>_<short-hash>'`` for the tip of ``branch``."""
    return _run_git(['-C', str(repo_path), 'log', '-1', branch,
                      '--pretty=format:%ad_%h', '--date=format:%Y%m%d_%H%M'])


def git_archive_zip(repo_path, branch, output_zip, prefix):
    """Archive ``branch`` to ``output_zip``, with all paths under ``<prefix>/``."""
    _run_git(['-C', str(repo_path), 'archive', '--format=zip',
              f'--prefix={prefix}/', f'--output={output_zip}', branch])


def git_remote_url(repo_path, remote='origin'):
    """Return the URL/path configured for ``remote``."""
    return _run_git(['-C', str(repo_path), 'remote', 'get-url', remote])


def git_set_remote_url(repo_path, url, remote='origin'):
    """Point ``remote`` at ``url``."""
    _run_git(['-C', str(repo_path), 'remote', 'set-url', remote, url])


def git_has_uncommitted_changes(repo_path):
    """True if tracked files in ``repo_path`` have uncommitted changes (ignores untracked files)."""
    return bool(_run_git(['-C', str(repo_path), 'status', '--porcelain', '-uno']))


def git_pull(repo_path):
    """Pull the current branch's upstream into ``repo_path``; returns git's combined output."""
    result = subprocess.run(['git', '-C', str(repo_path), 'pull'], capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(f'git pull failed in {repo_path}: {output}')
    return output
