"""Image naming rules shared by the Lane R scripts (build_derived.sh repeats derived_tag in bash)."""


def image_for(iid, kind):
    """Benchmark image of a Lite task: jiayuanz3 for related tasks, swebench for experience tasks."""
    if kind == "related":
        return "jiayuanz3/swecontextbench:" + iid.replace("__", ".")
    return "swebench/sweb.eval.x86_64." + iid.replace("__", "_1776_").lower() + ":latest"


def derived_tag(iid):
    """Local image rebuilt by build_derived.sh."""
    return f"pilot-a/{iid.replace('__', '.', 1)}:built"
