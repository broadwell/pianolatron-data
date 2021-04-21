#!/usr/bin/env python3

""" Build per-DRUID metadata .json files for consumption by the Pianolatron app. """

import json
import logging
import re
from pathlib import Path

import requests
from lxml import etree
from mido import MidiFile, tempo2bpm

WRITE_TEMPO_MAPS = False

DRUIDS = [
    "zb497jz4405",
    "yj598pj2879",
    "pz594dj8436",
    "dj406yq6980",
    "rx870zt5437",
    "wt621xq0875",
    "kr397bv2881",
]

PURL_BASE = "https://purl.stanford.edu/"
NS = {"x": "http://www.loc.gov/mods/v3"}

CACHE_MODS = True


def get_metadata_for_druid(druid):
    def get_value_by_xpath(xpath):
        try:
            return xml_tree.xpath(
                xpath,
                namespaces=NS,
            )[0]
        except IndexError:
            return None

    logging.info(f"Processing {druid}...")

    mods_filepath = Path(f"mods/{druid}.mods")

    if mods_filepath.exists():
        xml_tree = etree.parse(mods_filepath.open())
    else:
        response = requests.get(f"{PURL_BASE}{druid}.mods")
        xml_tree = etree.fromstring(response.content)
        if CACHE_MODS:
            with mods_filepath.open("r") as _fh:
                _fh.write(
                    etree.tostring(xml_tree, encoding="unicode", pretty_print=True)
                )

    return {
        "title": get_value_by_xpath("(x:titleInfo/x:title)[1]/text()"),
        "composer": get_value_by_xpath(
            "x:name[descendant::x:roleTerm[text()='composer']]/"
            "x:namePart[not(@type='date')]/text()",
        ),
        "performer": get_value_by_xpath(
            "x:name[descendant::x:roleTerm[text()='instrumentalist']]/"
            "x:namePart[not(@type='date')]/text()",
        ),
        "label": get_value_by_xpath("x:identifier[@type='issue number']/text()"),
        "PURL": PURL_BASE + druid,
    }


def build_tempo_map_from_midi(druid):

    midi_filepath = Path(f"midi/{druid}.mid")
    midi = MidiFile(midi_filepath)

    tempo_map = []
    current_tick = 0

    for event in midi.tracks[0]:
        current_tick += event.time
        if event.type == "set_tempo":
            tempo_map.append((current_tick, tempo2bpm(event.tempo)))

    return tempo_map


def get_hole_data(druid):
    txt_filepath = Path(f"txt/{druid}.txt")

    if not txt_filepath.exists():
        return None, None

    needed_keys = [
        "NOTE_ATTACK",
        "WIDTH_COL",
        "ORIGIN_COL",
        "ORIGIN_ROW",
        "OFF_TIME",
        "TRACKER_HOLE",
    ]

    roll_data = {}
    hole_data = []

    with txt_filepath.open("r") as _fh:
        while (line := _fh.readline()) and line != "@@BEGIN: HOLES\n":
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                roll_data[key] = value

        while (line := _fh.readline()) and line != "@@END: HOLES\n":
            if line == "@@BEGIN: HOLE\n":
                hole = {}
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                if key in needed_keys:
                    hole[key] = int(value.removesuffix("px"))
            if line == "@@END: HOLE\n":
                if "NOTE_ATTACK" in hole:
                    assert hole["NOTE_ATTACK"] == hole["ORIGIN_ROW"]
                    del hole["NOTE_ATTACK"]

                hole_data.append(hole)

    return roll_data, hole_data


def write_json(druid, metadata, indent=2):
    output_path = Path(f"json/{druid}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as _fh:
        json.dump(metadata, _fh, indent=indent)


def main():
    """ Command-line entry-point. """

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    for druid in DRUIDS:
        metadata = get_metadata_for_druid(druid)
        if WRITE_TEMPO_MAPS:
            metadata["tempoMap"] = build_tempo_map_from_midi(druid)
        roll_data, hole_data = get_hole_data(druid)
        metadata["holeData"] = hole_data
        write_json(druid, metadata)


if __name__ == "__main__":
    main()
