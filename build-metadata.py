#!/usr/bin/env python3

""" Build per-DRUID metadata .json files for consumption by the Pianolatron app. """

import json
import logging
import re
from pathlib import Path

import requests
import shutil
from lxml import etree
from mido import MidiFile, tempo2bpm
from csv import DictReader

PROCESS_IMAGE_FILES = True

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
STACKS_BASE = "https://stacks.stanford.edu/file/"
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

    dropped_holes = 0

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
                    assert "OFF_TIME" in hole
                    assert hole["NOTE_ATTACK"] == hole["ORIGIN_ROW"]
                    del hole["NOTE_ATTACK"]
                    hole_data.append(hole)
                else:
                    assert "OFF_TIME" not in hole
                    dropped_holes += 1

    print(f"Dropped Holes: {dropped_holes}")
    return roll_data, hole_data


def remap_hole_data(roll_data, hole_data):

    new_hole_data = []

    for hole in hole_data:
        new_hole_data.append(
            {
                "x": hole["ORIGIN_COL"],
                "y": hole["ORIGIN_ROW"],
                "w": hole["WIDTH_COL"],
                "h": hole["OFF_TIME"] - hole["ORIGIN_ROW"],
            }
        )

    return new_hole_data


def write_json(druid, metadata, indent=2):
    output_path = Path(f"json/{druid}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as _fh:
        json.dump(metadata, _fh)


def get_druids_from_files():
    druids_list = []
    for druid_file in Path('druids/').glob('*.csv'):
        with open(druid_file, 'r', newline='') as druid_csv:
            druid_reader = DictReader(druid_csv)
            for row in druid_reader:
                druids_list.append(row['Druid'])
    return druids_list

def request_image(image_url):
    print("Downloading",image_url)
    response = requests.get(image_url, stream=True)
    if response.status_code == 200:
        return response
    else:
        print("Unable to download",image_url,response)
        return None

def get_roll_image(druid):
    roll_image = Path(f"images/{druid}_0001_gr.tif")
    if not roll_image.is_file():
        image_url = f"{STACKS_BASE}{druid}/{druid}_0001_gr.tif"
        response = request_image(image_url)
        if response is None:
            # Ugh
            image_url = image_url.replace('.tif','.tiff')
            response = request_image(image_url)
        if response is not None:
            roll_image = f"images/{druid}_0001_gr.tif"
            with open(roll_image, "wb") as image_file:
                shutil.copyfileobj(response.raw, image_file)
        else:
            roll_image = None
        del response
    return roll_image

def main():
    """ Command-line entry-point. """

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    DRUIDS = get_druids_from_files()

    for druid in DRUIDS:

        metadata = get_metadata_for_druid(druid)
        if WRITE_TEMPO_MAPS:
            metadata["tempoMap"] = build_tempo_map_from_midi(druid)
        roll_data, hole_data = get_hole_data(druid)
        if hole_data:
            metadata["holeData"] = remap_hole_data(roll_data, hole_data)
        else:
            metadata["holeData"] = None
        write_json(druid, metadata, indent=0)


if __name__ == "__main__":
    main()
