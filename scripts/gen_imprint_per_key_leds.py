#!/usr/bin/env python3
"""Generate the Imprint per-key RGB LED maps for ZMK from QMK's rgb_matrix data.

Single source of truth: ``vial-qmk/keyboards/cyboard/imprint/<variant>/info.json``
``rgb_matrix.layout``. QMK already drives each switch's own addressable WS2812
LED and records, per cut, which LED sits under which matrix position. ZMK never
mapped that; this script ports it so the two firmwares never drift
(cyboard-wiki projects/studio-rgb-control.md, decision 2; zmk-private#54).

How the join works (verified 1:1 for all nine Imprint cuts):

* A QMK ``rgb_matrix.layout`` entry with ``flags: 4`` (LED_FLAG_KEYLIGHT) is a
  dedicated LED under one switch, tagged with that switch's electrical
  ``matrix: [row, col]``. The entry's position in the array is its index on the
  physical LED strip; ``split_count = [L, R]`` splits the array into the left
  half's strip (indices 0..L-1) and the right half's strip (the next R, whose
  own strip indices restart at 0).
* ZMK's ``zmk,matrix-transform`` for the same cut lists ``RC(row, col)`` in key-
  position order, and QMK's ``[row, col]`` is the *same* electrical coordinate
  (confirmed: e.g. the left thumb cluster is ``RC(0,3) RC(0,2) RC(0,1)`` /
  ``RC(0,7) RC(0,6) RC(0,5)`` in ZMK and ``[0,3] [0,2] [0,1]`` / ``[0,7] [0,6]
  [0,5]`` in QMK). So key position *p* -> its ``(row,col)`` -> the QMK LED whose
  ``matrix`` is that ``(row,col)`` -> that LED's within-its-own-half strip index.

Output: ``boards/shields/imprint/imprint-per-key-leds.dtsi`` -- one
``per_key_leds`` child (compatible ``zmk,per-key-leds``) per physical layout,
carrying a ``leds`` cell array indexed by key position, value = LED strip index
on that key's own half. The firmware's per-key render path (zmk-private#54)
reads it; stock ZMK ignores the unknown compatible, so the shield still builds
against upstream (same tactic as the status_indicators map, zmk-keyboards#31).

Regenerate after any QMK rgb_matrix change:
    python3 scripts/gen_imprint_per_key_leds.py
(run from the zmk-keyboards repo root, with vial-qmk cloned as a sibling).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ZMK physical-layout node label  ->  (ZMK transform label, QMK variant dir).
# The transform label is also read straight from the DT, but pinning it here
# lets the script assert the DT has not been reshaped under it.
VARIANTS = {
    "physical_layout_imprint_function_row_full_bottom_row": (
        "imprint_function_row_full_bottom_row", "imprint_function_row_5key_bottom_row"),
    "physical_layout_imprint_function_row": (
        "imprint_function_row", "imprint_function_row_2key_bottom_row"),
    "physical_layout_imprint_function_row_no_bottom_row": (
        "imprint_function_row_no_bottom_row", "imprint_function_row_no_bottom_row"),
    "physical_layout_imprint_number_row_full_bottom_row": (
        "imprint_number_row_full_bottom_row", "imprint_number_row_5key_bottom_row"),
    "physical_layout_imprint_number_row": (
        "imprint_number_row", "imprint_number_row_2key_bottom_row"),
    "physical_layout_imprint_number_row_no_bottom_row": (
        "imprint_number_row_no_bottom_row", "imprint_number_row_no_bottom_row"),
    "physical_layout_imprint_letters_only_full_bottom_row": (
        "imprint_letters_only_full_bottom_row", "imprint_letters_only_5key_bottom_row"),
    "physical_layout_imprint_letters_only": (
        "imprint_letters_only", "imprint_letters_only_2key_bottom_row"),
    "physical_layout_imprint_letters_only_no_bottom_row": (
        "imprint_letters_only_no_bottom_row", "imprint_letters_only_no_bottom_row"),
}

LED_FLAG_KEYLIGHT = 4


def strip_comments(text: str) -> str:
    """Drop // line and /* */ block comments so a `>` inside a comment can't
    truncate a non-greedy `< ... >` match downstream."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def parse_transforms(dtsi: str) -> dict[str, list[tuple[int, int]]]:
    """label -> ordered [(row, col), ...] for every zmk,matrix-transform."""
    dtsi = strip_comments(dtsi)
    out: dict[str, list[tuple[int, int]]] = {}
    for m in re.finditer(
        r"(\w+):\s*keymap_transform_\d+\s*\{.*?map\s*=\s*<(.*?)>\s*;", dtsi, re.S
    ):
        label, body = m.group(1), m.group(2)
        out[label] = [(int(r), int(c)) for r, c in re.findall(r"RC\(\s*(\d+)\s*,\s*(\d+)\s*\)", body)]
    return out


def parse_layout_transforms(layouts_dtsi: str) -> dict[str, str]:
    """physical_layout node label -> its transform label (from the node body)."""
    layouts_dtsi = strip_comments(layouts_dtsi)
    out: dict[str, str] = {}
    for m in re.finditer(
        r"(\w+):\s*physical_layout_\d+\s*\{(.*?)\}", layouts_dtsi, re.S
    ):
        label, body = m.group(1), m.group(2)
        tm = re.search(r"transform\s*=\s*<&(\w+)>", body)
        if tm:
            out[label] = tm.group(1)
    return out


def parse_status_indicators(layouts_dtsi: str) -> dict[str, dict[str, list[int]]]:
    """physical_layout label -> {battery:[...], bt-profiles:[...], usb:[...]}.

    Hardware-confirmed LED strip indices (zmk-keyboards#31); used only to
    sanity-check that this generator lands LEDs in the same index space.
    """
    layouts_dtsi = strip_comments(layouts_dtsi)
    out: dict[str, dict[str, list[int]]] = {}
    for m in re.finditer(
        r"&(\w+)\s*\{\s*status_indicators\s*\{(.*?)\}\s*;\s*\}\s*;", layouts_dtsi, re.S
    ):
        label, body = m.group(1), m.group(2)
        d: dict[str, list[int]] = {}
        for prop in ("battery", "bt-profiles", "usb"):
            pm = re.search(rf"{prop}\s*=\s*<([^>]*)>", body)
            if pm:
                d[prop] = [int(x) for x in re.findall(r"\d+", pm.group(1))]
        out[label] = d
    return out


# ws2812 overlays whose chain-length must cover the largest single-half strip.
# One firmware serves every cut via runtime physical-layout selection, so the
# SPI pixel buffer must fit the biggest half; a smaller chain-length silently
# under-allocates (extra LEDs never driven, no build error).
CHAIN_LENGTH_OVERLAYS = (
    Path("boards") / "assimilator-bt.overlay",
    Path("boards") / "nice_nano_v2.overlay",
)


def check_chain_lengths(shield: Path, max_side: int) -> None:
    """Fail if any imprint ws2812 overlay's chain-length is below max_side."""
    for rel in CHAIN_LENGTH_OVERLAYS:
        path = shield / rel
        text = strip_comments(path.read_text())
        m = re.search(r"chain-length\s*=\s*<\s*(\d+)\s*>", text)
        if not m:
            raise SystemExit(f"{path}: no ws2812 chain-length found")
        chain_length = int(m.group(1))
        if chain_length < max_side:
            raise SystemExit(
                f"{path}: chain-length {chain_length} < largest half-strip "
                f"{max_side} LEDs -- the SPI pixel buffer under-allocates; "
                f"bump chain-length to >= {max_side}")


def qmk_led_index(variant_dir: Path) -> tuple[dict[tuple[int, int], int], int, int]:
    """Return ((row,col) -> within-half strip index), left_count, right_count.

    Side is implied by the array position (first L entries = left strip, the
    next R = right strip); the within-half index restarts at 0 on the right.
    """
    info = json.loads((variant_dir / "info.json").read_text())
    rm = info["rgb_matrix"]
    left_count, right_count = rm["split_count"]
    layout = rm["layout"]
    if len(layout) != left_count + right_count:
        raise ValueError(
            f"{variant_dir.name}: layout has {len(layout)} entries but "
            f"split_count sums to {left_count + right_count}"
        )
    mapping: dict[tuple[int, int], int] = {}
    for g, entry in enumerate(layout):
        if entry.get("flags") != LED_FLAG_KEYLIGHT:
            continue
        row, col = entry["matrix"]
        side_left = g < left_count
        strip_idx = g if side_left else g - left_count
        # Cross-check: QMK's own row bucket must agree with the array split.
        row_is_left = row < 7
        if row_is_left != side_left:
            raise ValueError(
                f"{variant_dir.name}: LED {g} matrix [{row},{col}] sits in the "
                f"{'left' if side_left else 'right'} array block but its row "
                f"implies the {'left' if row_is_left else 'right'} half"
            )
        key = (row, col)
        if key in mapping:
            raise ValueError(f"{variant_dir.name}: duplicate flag-4 matrix {key}")
        mapping[key] = strip_idx
    return mapping, left_count, right_count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parent.parent,
        help="zmk-keyboards repo root (default: parent of this script's dir)")
    ap.add_argument(
        "--vial-qmk", type=Path, default=None,
        help="path to vial-qmk checkout (default: sibling of repo root)")
    ap.add_argument(
        "--check", action="store_true",
        help="fail if the generated file is out of date instead of writing it")
    args = ap.parse_args()

    repo = args.repo_root
    vial_qmk = args.vial_qmk or repo.parent / "vial-qmk"
    shield = repo / "boards" / "shields" / "imprint"
    qmk_imprint = vial_qmk / "keyboards" / "cyboard" / "imprint"

    dtsi = (shield / "imprint.dtsi").read_text()
    layouts_dtsi = (shield / "imprint-layouts.dtsi").read_text()
    transforms = parse_transforms(dtsi)
    layout_transforms = parse_layout_transforms(layouts_dtsi)
    status = parse_status_indicators(layouts_dtsi)

    blocks: list[str] = []
    max_side = 0
    for node_label, (xform_label, qmk_dir) in VARIANTS.items():
        if layout_transforms.get(node_label) != xform_label:
            raise SystemExit(
                f"{node_label}: DT transform is "
                f"{layout_transforms.get(node_label)!r}, expected {xform_label!r} "
                f"-- the layout file was reshaped; update VARIANTS.")
        positions = transforms[xform_label]
        mapping, left_count, right_count = qmk_led_index(qmk_imprint / qmk_dir)
        max_side = max(max_side, left_count, right_count)

        leds: list[int] = []
        for pos, (row, col) in enumerate(positions):
            if (row, col) not in mapping:
                raise SystemExit(
                    f"{node_label}: key position {pos} RC({row},{col}) has no "
                    f"flag-4 LED in QMK {qmk_dir}")
            leds.append(mapping[(row, col)])

        # Sanity: left positions index into [0,left_count), right into [0,right_count).
        for pos, ((row, col), led) in enumerate(zip(positions, leds)):
            limit = left_count if row < 7 else right_count
            if not 0 <= led < limit:
                raise SystemExit(
                    f"{node_label}: position {pos} LED {led} out of range "
                    f"[0,{limit})")

        # Sanity: the hardware-confirmed status-indicator LED indices
        # (zmk-keyboards#31) must actually appear in this cut's generated
        # left-half map -- not merely sit in range. This enforces the
        # cross-check claim; an in-range but wrong index would otherwise pass.
        left_leds = {led for (row, _col), led in zip(positions, leds) if row < 7}
        for prop, idxs in status.get(node_label, {}).items():
            for idx in idxs:
                if idx not in left_leds:
                    raise SystemExit(
                        f"{node_label}: status {prop} index {idx} is not in the "
                        f"generated left-half LED map (expected a key-light LED)")

        # Wrap the cell list for readability (12 per line).
        wrapped = "\n".join(
            "            " + " ".join(str(x) for x in leds[i:i + 12])
            for i in range(0, len(leds), 12)
        )
        blocks.append(
            f"&{node_label} {{\n"
            f"    per_key_leds {{\n"
            f"        compatible = \"zmk,per-key-leds\";\n"
            f"        // key position -> LED index on that key's own half's strip\n"
            f"        // ({len(leds)} keys; from QMK {qmk_dir})\n"
            f"        leds = <\n{wrapped}\n        >;\n"
            f"    }};\n"
            f"}};\n"
        )

    # The hardcoded ws2812 chain-length must cover the largest half-strip.
    check_chain_lengths(shield, max_side)

    header = f"""\
// GENERATED by scripts/gen_imprint_per_key_leds.py -- DO NOT EDIT BY HAND.
//
// Per-key RGB LED maps for the nine Imprint physical layouts, ported from QMK's
// rgb_matrix.layout (vial-qmk keyboards/cyboard/imprint/<cut>/info.json) so the
// wireless (ZMK) firmware can address each switch's own LED the way the wired
// (QMK) firmware already does. One source of truth; regenerate on QMK changes.
// See cyboard-wiki projects/studio-rgb-control.md (zmk-private#54, decision 2).
//
// Each map is a `per_key_leds` child of its zmk,physical-layout node, carrying
// `leds` indexed by key position (value = LED index on that key's own half's
// strip). A custom compatible keeps stock ZMK building (it ignores the unknown
// node) -- the same tactic as the status_indicators map (zmk-keyboards#31).
//
// Largest single-half strip across all cuts: {max_side} LEDs (flagship 5-key
// function-row). The shield's ws2812 chain-length must be >= that.

"""
    out_text = header + "\n".join(blocks)
    out_path = shield / "imprint-per-key-leds.dtsi"

    if args.check:
        current = out_path.read_text() if out_path.exists() else ""
        if current != out_text:
            print(f"OUT OF DATE: {out_path} -- rerun scripts/gen_imprint_per_key_leds.py",
                  file=sys.stderr)
            return 1
        print(f"up to date: {out_path}")
        return 0

    out_path.write_text(out_text)
    print(f"wrote {out_path} ({len(blocks)} layouts, max half-strip {max_side} LEDs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
