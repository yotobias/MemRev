"""The pairs stage: revision pairs from SWE-bench Verified metadata (V11, V13, V24, ADR 0001).

Source revisions are the distinct source revisions of the run's lessons. A source's
SWE-bench version is the version of the instance whose base_commit it is. Later
instances are ordered by the committer date of their base_commit (`created_at` is
the PR opening date and is not used). Per source, the nearest, middle and furthest
later instance of the same version are chosen, and each is kept only if S is a git
ancestor of T. Later instances of another version are recorded as cross-version.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from memrev.repository import Repository
from memrev.store import ExclusionReason, RevisionPair, RunStore
from memrev.swe_bench import Instance, load_instances

STAGE = "pairs"


@dataclass
class PairsSummary:
    sources: int = 0
    pairs: int = 0
    exclusions: list[tuple[str, ExclusionReason, str]] = field(default_factory=list)

    def excluded_per_reason(self) -> Counter:
        return Counter(str(reason) for _, reason, _ in self.exclusions)


def pair_id(source: str, target: str) -> str:
    return f"{source[:12]}..{target[:12]}"


def choose_targets(later: list[Instance]) -> list[tuple[str, Instance]]:
    """Nearest, middle and furthest of `later` (already in date order), without repeats."""
    if not later:
        return []
    picks: dict[int, str] = {}
    for index, role in ((0, "nearest"), (len(later) - 1, "furthest"), (len(later) // 2, "middle")):
        picks.setdefault(index, role)
    return [(role, later[index]) for index, role in sorted(picks.items())]


def build_pairs(store: RunStore, meta_path: Path) -> PairsSummary:
    summary = PairsSummary()
    for repository, local_path in store.repositories().items():
        sources = sorted({l.source_revision for l in store.lessons() if l.repository == repository})
        if sources:
            _PairBuilder(store, summary, repository, Repository(local_path), load_instances(meta_path, repository)).run(
                sources
            )
    return summary


class _PairBuilder:
    """Builds the pairs of one repository and records what it excludes."""

    def __init__(
        self,
        store: RunStore,
        summary: PairsSummary,
        repository: str,
        repo: Repository,
        instances: list[Instance],
    ):
        self.store = store
        self.summary = summary
        self.repository = repository
        self.repo = repo
        self.instances = instances
        self.by_commit = {i.base_commit: i for i in instances}

    def run(self, sources: list[str]) -> None:
        self.times = self.repo.commit_times([i.base_commit for i in self.instances] + sources)
        for source in sources:
            self.summary.sources += 1
            self._build_for_source(source)

    def _later_than(self, source: str) -> list[Instance]:
        """Instances whose base_commit is committed after `source`, in date order."""
        later = [
            i for i in self.instances if i.base_commit in self.times and self.times[i.base_commit] > self.times[source]
        ]
        return sorted(later, key=lambda i: (self.times[i.base_commit], i.instance_id))

    def _build_for_source(self, source: str) -> None:
        source_subject = f"source {source}"
        source_instance = self.by_commit.get(source)
        if source_instance is None:
            self._exclude(
                source_subject, ExclusionReason.NO_TARGET,
                f"not the base_commit of any SWE-bench Verified instance of {self.repository}",
            )
            return
        later = self._later_than(source)
        same_version = [i for i in later if i.version == source_instance.version]
        for other in later:
            if other.version != source_instance.version:
                self._exclude(
                    f"pair {pair_id(source, other.base_commit)}", ExclusionReason.CROSS_VERSION,
                    f"{source_instance.instance_id} is version {source_instance.version}, "
                    f"{other.instance_id} is version {other.version}",
                )
        if not same_version:
            self._exclude(
                source_subject, ExclusionReason.NO_TARGET,
                f"no later instance in version {source_instance.version} ({source_instance.instance_id})",
            )
            return
        self.store.clear_exclusion(STAGE, source_subject)
        for role, target in choose_targets(same_version):
            self._pair(source_instance, target, role)

    def _pair(self, source: Instance, target: Instance, role: str) -> None:
        pair = RevisionPair(
            pair_id=pair_id(source.base_commit, target.base_commit),
            repository=self.repository,
            version=source.version,
            source_revision=source.base_commit,
            target_revision=target.base_commit,
            source_instance=source.instance_id,
            target_instance=target.instance_id,
            target_role=role,
        )
        subject = f"pair {pair.pair_id}"
        if not self.repo.is_ancestor(source.base_commit, target.base_commit):
            self.store.remove_revision_pair(pair.pair_id)
            self._exclude(
                subject, ExclusionReason.ANCESTRY_FAILED,
                f"{source.instance_id} base_commit is not an ancestor of "
                f"{target.instance_id} base_commit ({role} target)",
            )
            return
        self.store.clear_exclusion(STAGE, subject)
        self.store.add_revision_pair(pair)
        self.summary.pairs += 1

    def _exclude(self, subject: str, reason: ExclusionReason, detail: str) -> None:
        self.store.record_exclusion(STAGE, subject, reason, detail)
        self.summary.exclusions.append((subject, reason, detail))
