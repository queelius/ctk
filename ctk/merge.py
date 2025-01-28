from .utils import load_conversations, save_conversations
from rich.console import Console

console = Console()


def union_libs(libdirs, output_dir, conflict_resolution="skip"):
    """
    @brief Take the union of multiple conversation libraries.
    @param libdirs List of library directories to merge.
    @param conflict_resolution How to handle duplicate conversation ids. Options: "skip", "overwrite-old", "error"
    @param output_dir Output library directory.
    """

    union_lib = load_conversations(libdirs[0])
    for d in libdirs[1:]:
        # check if unique ids conflict
        lib = load_conversations(d)
        if not lib:
            continue
        for conv in lib:
            if conv["id"] in [c["id"] for c in union_lib]:
                union_conv = lib[conv["id"]]
                if conflict_resolution == "skip":
                    console.print(f"Skipping duplicate id {conv['id']}")
                    continue
                elif conflict_resolution == "overwrite-old":
                    # keep the one with the newest update_time or if that doesn't exist, the newest create_time
                    latest_time_lib = max(
                        conv.get("update_time", 0), conv.get("create_time", 0))
                    latest_time_union = max(union_conv.get(
                        "update_time", 0), union_conv.get("create_time", 0))
                    if latest_time_lib > latest_time_union:
                        union_lib[conv["id"]] = conv
                        console.print(
                            f"Overwriting with newer id {conv['id']}")
                    else:
                        console.print(f"Keeping existing id {conv['id']}")
                elif conflict_resolution == "error":
                    raise ValueError(
                        f"Duplicate id {conv['id']} found in libraries")
            else:
                union_lib.append(conv)

    save_conversations(output_dir, union_lib)


def intersect_libs(libdirs, output_dir, conflict_resolution="skip"):
    """
    @brief Take the intersection of multiple conversation libraries.
    @param libdirs List of library directories to merge.
    @param conflict_resolution How to handle duplicate conversation ids. Options: "skip", "overwrite-old", "error"
    @param output_dir Output library directory.
    """

    intersection_lib = []
    for d in libdirs:
        lib = load_conversations(d)
        if not lib:
            continue
        for conv in lib:
            if conv["id"] in [c["id"] for c in intersection_lib]:
                union_conv = lib[conv["id"]]
                if conflict_resolution == "skip":
                    console.print(f"Skipping duplicate id {conv['id']}")
                    continue
                elif conflict_resolution == "overwrite-old":
                    # keep the one with the newest update_time or if that doesn't exist, the newest create_time
                    latest_time_lib = max(
                        conv.get("update_time", 0), conv.get("create_time", 0))
                    latest_time_union = max(union_conv.get(
                        "update_time", 0), union_conv.get("create_time", 0))
                    if latest_time_lib > latest_time_union:
                        intersection_lib[conv["id"]] = conv
                        console.print(
                            f"Overwriting with newer id {conv['id']}")
                    else:
                        console.print(f"Keeping existing id {conv['id']}")
                elif conflict_resolution == "error":
                    raise ValueError(
                        f"Duplicate id {conv['id']} found in libraries")
            else:
                intersection_lib.append(conv)

    save_conversations(output_dir, intersection_lib)


def diff_libs(libdirs, output_dir):
    """
    @brief Find the difference between the first lib (libdirs[0]) and the union of the remaining libs.
    @param libdirs List of library directories to take the difference of.
    @param output_dir Output library directory.
    """

    diff_lib = load_conversations(libdirs[0])
    for d in libdirs[1:]:
        lib = load_conversations(d)
        for conv in lib:
            if conv["id"] in [c["id"] for c in diff_lib]:
                diff_lib.remove(conv)

    save_conversations(output_dir, diff_lib)
