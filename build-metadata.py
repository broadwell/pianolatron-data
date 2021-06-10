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
from os import system
import re
from shutil import copy

PROCESS_IMAGE_FILES = True

EXTRACT_MIDI_FILES = True

APPLY_MIDI_EXPRESSIONS = True

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

ROLL_TYPES = {
    "Welte-Mignon red roll (T-100).": "welte-red",
    "Scale: 88n.": "88-note",
}

ROLL_PARSER_DIR = "../roll-image-parser/"
BINASC_DIR = "../binasc/"
MIDI2EXP_DIR = "../midi2exp/"

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
            with mods_filepath.open("w") as _fh:
                _fh.write(
                    etree.tostring(xml_tree, encoding="unicode", pretty_print=True)
                )

    roll_type = "NA"
    for note in xml_tree.xpath("(x:note)", namespaces=NS):
        if note is not None and note.text in ROLL_TYPES:
            roll_type = ROLL_TYPES[note.text]

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
        "type": roll_type,
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
        "MIDI_KEY",
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
                    if hole["ORIGIN_ROW"] >= hole["OFF_TIME"]:
                        print("WARNING: invalid note duration",hole["ORIGIN_ROW"],hole["OFF_TIME"],hole["MIDI_KEY"])
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
        response.raw.decode_content = True
        return response
    else:
        print("Unable to download",image_url,response)
        return None

def get_roll_image(druid):
    roll_image = None
    matches = list(Path("images/").glob(f"{druid}_0001_gr.tif*"))
    if not len(matches):
        roll_fn = f"{druid}_0001_gr.tiff"
        image_url = f"{STACKS_BASE}{druid}/{roll_fn}"
        response = request_image(image_url)
        if response is None:
            # Ugh
            image_url = image_url.replace('.tiff','.tif')
            response = request_image(image_url)
        if response is not None:
            roll_image = f"images/{roll_fn}"
            with open(roll_image, "wb") as image_file:
                shutil.copyfileobj(response.raw, image_file)
        del response
    else:
        roll_image = matches[0]
    return roll_image

def parse_roll_image(druid, roll_image, roll_type):
    print("Running image parser on",druid,roll_image,roll_type)
    if roll_image is None or roll_type == "NA" or not Path(f"{ROLL_PARSER_DIR}bin/tiff2holes").is_file() or Path(f"txt/{druid}.txt").is_file():
        print("bailing out")
        return 
    if roll_type == "welte-red":
        t2h_switches = "-m -r"
    elif roll_type == "88-note":
        t2h_switches = "-m -8"
    # XXX Save analysis stderr output to a file (2> {druid}_image_parse_errors.txt)?
    cmd = f"{ROLL_PARSER_DIR}bin/tiff2holes {t2h_switches} {roll_image} > txt/{druid}.txt 2> image_parse_errors.txt"
    print("Parsing command:",cmd)
    system(cmd)

def convert_binasc_to_midi(binasc_data, druid, midi_type):
    binasc_file_path = f"binasc/{druid}_{midi_type}.binasc"
    with open(binasc_file_path, "w") as binasc_file:
        binasc_file.write(binasc_data)
    if Path(f"{BINASC_DIR}binasc").is_file():
        cmd = f"{BINASC_DIR}binasc {binasc_file_path} -c midi/{druid}_{midi_type}.mid"
        system(cmd)

def extract_midi_from_analysis(druid):
    print("Extracting MIDI from",f"txt/{druid}.txt")
    if not Path(f"txt/{druid}.txt").is_file():
        print("Analysis file not found")
        return
    with open(f"txt/{druid}.txt", 'r') as analysis:
        contents = analysis.read()
        # NOTE: the binasc utility *requires* a trailing blank line at the end of the text input
        holes_data = re.search(r"^@HOLE_MIDIFILE:$(.*)", contents, re.M | re.S).group(1).split("\n@")[0]
        convert_binasc_to_midi(holes_data, druid, "raw")
        notes_data = re.search(r"^@MIDIFILE:$(.*)", contents, re.M | re.S).group(1).split("\n@")[0]
        convert_binasc_to_midi(notes_data, druid, "note")
    print("Finished MIDI extraction")

def apply_midi_expressions(druid, roll_type):
    if not Path(f"midi/{druid}_note.mid").is_file() or not Path(f"{MIDI2EXP_DIR}bin/midi2exp").is_file():
        print("Bailing out")
        return
    # There's a switch, -r, to remove the control tracks (3-4(5))
    if roll_type == "welte-red":
        m2e_switches = "-w -r"
    elif roll_type == "88-note":
        m2e_switches = ""
    cmd = f"{MIDI2EXP_DIR}bin/midi2exp {m2e_switches} midi/{druid}_note.mid midi/{druid}_exp.mid"
    print("Running expression extraction cmd",cmd)
    system(cmd)
    return True

def main():
    """ Command-line entry-point. """

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    #DRUIDS = get_druids_from_files()

    for druid in DRUIDS:

        metadata = get_metadata_for_druid(druid)

        print("Processed metadata for",druid)

        if PROCESS_IMAGE_FILES:
            roll_image = get_roll_image(druid)
            print("Parsing roll image file",roll_image)
            parse_roll_image(druid, roll_image, metadata['type'])

        print("Extracting midi for",druid)

        if EXTRACT_MIDI_FILES:
            extract_midi_from_analysis(druid)

            if APPLY_MIDI_EXPRESSIONS:
                apply_midi_expressions(druid, metadata['type'])
            
            # Use the expression MIDI if available, otherwise use the notes MIDI
            if Path(f"midi/{druid}_exp.mid").is_file():
                copy(Path(f"midi/{druid}_exp.mid"), Path(f"midi/{druid}.mid"))
            elif Path(f"midi/{druid}_note.mid").is_file():
                copy(Path(f"midi/{druid}_note.mid"), Path(f"midi/{druid}.mid"))

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
