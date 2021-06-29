#!/usr/bin/env python3

""" Build per-DRUID metadata .json files for consumption by the Pianolatron """
""" app, optionally using external tools to generate the roll image         """
""" processing analysis output and playable .midi files needed to present   """
""" each roll in the app.                                                   """

from csv import DictReader
import json
import logging
from os import system
from pathlib import Path
import re
from shutil import copy, copyfileobj

import requests
from lxml import etree
from PIL import Image
from mido import MidiFile, tempo2bpm

# Otherwise Pillow will refuse to open image, thinking it's a DOS attack vector
Image.MAX_IMAGE_PIXELS = None

BUILD_CATALOG = True
PROCESS_IMAGE_FILES = True
EXTRACT_MIDI_FILES = True
APPLY_MIDI_EXPRESSIONS = True
WRITE_TEMPO_MAPS = False

DRUIDS = [
    # "pk349zj4179",
    # "xy736dn5214",  # 65-note roll from G-C collection!
    # "jw822wm2644",  # Needs to be flipped left-right
    # "vj052cw2158",  # Spurious hole detected near top of roll
    "vs059bb4318",
    "bc072xf6791",
    "mf443ns5829",
    "wt621xq0875",
    "zb497jz4405",
    "dj406yq6980",
    "pz594dj8436",
    "cy287wz7683",
    "rx870zt5437",
]

ROLLS_TO_MIRROR = ["jw822wm2644"]

DUPLICATES_TO_SKIP = ["rr052wh1991"]

ROLL_TYPES = {
    "Welte-Mignon red roll (T-100).": "welte-red",
    "Welte-Mignon red roll (T-100)..": "welte-red",  # Ugh
    "Scale: 88n.": "88-note",
    "Scale: 65n.": "65-note",
}

ROLL_PARSER_DIR = "../roll-image-parser/"
BINASC_DIR = "../binasc/"
MIDI2EXP_DIR = "../midi2exp/"

PURL_BASE = "https://purl.stanford.edu/"
STACKS_BASE = "https://stacks.stanford.edu/file/"
NS = {"x": "http://www.loc.gov/mods/v3"}

CACHE_MODS = True
CACHE_MANIFESTS = True


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
                    etree.tostring(
                        xml_tree, encoding="unicode", pretty_print=True
                    )
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
        "label": get_value_by_xpath(
            "x:identifier[@type='issue number']/text()"
        ),
        # "responsibility": get_value_by_xpath(
        #    "x:note[@type='statement of responsibility']/text()"
        # ),
        "type": roll_type,
        "PURL": PURL_BASE + druid,
    }


def get_iiif_manifest(druid):

    iiif_filepath = Path(f"manifests/{druid}.json")
    if iiif_filepath.exists():
        iiif_manifest = json.load(open(iiif_filepath, "r"))
    else:
        response = requests.get(f"{PURL_BASE}{druid}/iiif/manifest")
        iiif_manifest = response.json()
        if CACHE_MANIFESTS:
            with iiif_filepath.open("w") as _fh:
                json.dump(iiif_manifest, _fh)
    return iiif_manifest


def get_tiff_url(iiif_manifest):
    if "rendering" not in iiif_manifest["sequences"][0]:
        return None

    for rendering in iiif_manifest["sequences"][0]["rendering"]:
        if (
            rendering["format"] == "image/tiff"
            or rendering["format"] == "image/x-tiff-big"
        ):
            return rendering["@id"]
    return None


def get_iiif_url(iiif_manifest):
    resource_id = iiif_manifest["sequences"][0]["canvases"][0]["images"][0][
        "resource"
    ]["@id"]
    return resource_id.replace("full/full/0/default.jpg", "info.json")


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
                    if hole["ORIGIN_ROW"] >= hole["OFF_TIME"]:
                        logging.info(f"WARNING: invalid note duration: {hole}")
                    hole_data.append(hole)
                else:
                    assert "OFF_TIME" not in hole
                    dropped_holes += 1

    logging.info(f"Dropped Holes: {dropped_holes}")
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
                "m": hole["MIDI_KEY"],
                "t": hole["TRACKER_HOLE"],
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
    for druid_file in Path("druids/").glob("*.csv"):
        with open(druid_file, "r", newline="") as druid_csv:
            druid_reader = DictReader(druid_csv)
            for row in druid_reader:
                druids_list.append(row["Druid"])
    return druids_list


def request_image(image_url):
    logging.info(f"Downloading roll image {image_url}")
    response = requests.get(image_url, stream=True)
    if response.status_code == 200:
        response.raw.decode_content = True
        return response
    else:
        logging.info("Unable to download {image_url} - {response}")
        return None


def get_roll_image(image_url, druid):
    image_fn = re.sub("\.tif$", ".tiff", image_url.split("/")[-1])
    image_filepath = Path(f"images/{image_fn}")
    if image_filepath.exists():
        return image_filepath
    response = request_image(image_url)
    with open(image_filepath, "wb") as image_file:
        copyfileobj(response.raw, image_file)
    del response
    if druid in ROLLS_TO_MIRROR:
        flip_image_left_right(image_filepath)
    return image_filepath


def flip_image_left_right(image_filepath):
    logging.info(f"Flipping image left-right: {image_filepath}")
    im = Image.open(image_filepath)
    out = im.transpose(Image.FLIP_LEFT_RIGHT)
    out.save(image_filepath)
    return image_filepath


def parse_roll_image(druid, image_filepath, roll_type):
    print("In parse_roll_image", druid, image_filepath, roll_type)
    if (
        image_filepath is None
        or roll_type == "NA"
        or not Path(f"{ROLL_PARSER_DIR}bin/tiff2holes").exists()
        or Path(f"txt/{druid}.txt").exists()
    ):
        return
    if roll_type == "welte-red":
        t2h_switches = "-m -r"
    elif roll_type == "88-note":
        t2h_switches = "-m -8"
    elif roll_type == "65-note":
        t2h_switches = "-m -5"
    # XXX Is it helpful to save analysis stderr output to a file (2> logs/{druid}.err)?
    cmd = f"{ROLL_PARSER_DIR}bin/tiff2holes {t2h_switches} {image_filepath} > txt/{druid}.txt 2> logs/{druid}.err"
    logging.info(
        f"Running image parser on {druid} {image_filepath} {roll_type}"
    )
    system(cmd)


def convert_binasc_to_midi(binasc_data, druid, midi_type):
    binasc_file_path = f"binasc/{druid}_{midi_type}.binasc"
    with open(binasc_file_path, "w") as binasc_file:
        binasc_file.write(binasc_data)
    if Path(f"{BINASC_DIR}binasc").exists():
        cmd = f"{BINASC_DIR}binasc {binasc_file_path} -c midi/{druid}_{midi_type}.mid"
        system(cmd)


def extract_midi_from_analysis(druid):
    if not Path(f"txt/{druid}.txt").exists():
        return
    if Path(f"midi/{druid}.mid").exists():
        return
    logging.info(f"Extracting MIDI from txt/{druid}.txt")
    with open(f"txt/{druid}.txt", "r") as analysis:
        contents = analysis.read()
        # NOTE: the binasc utility *requires* a trailing blank line at the end of the text input
        holes_data = (
            re.search(r"^@HOLE_MIDIFILE:$(.*)", contents, re.M | re.S)
            .group(1)
            .split("\n@")[0]
        )
        convert_binasc_to_midi(holes_data, druid, "raw")
        notes_data = (
            re.search(r"^@MIDIFILE:$(.*)", contents, re.M | re.S)
            .group(1)
            .split("\n@")[0]
        )
        convert_binasc_to_midi(notes_data, druid, "note")


def apply_midi_expressions(druid, roll_type):
    if (
        not Path(f"midi/{druid}_note.mid").exists()
        or not Path(f"{MIDI2EXP_DIR}bin/midi2exp").exists()
    ):
        return
    # There's a switch, -r, to remove the control tracks (3-4(5))
    m2e_switches = ""
    if roll_type == "welte-red":
        m2e_switches = "-w -r"
    cmd = f"{MIDI2EXP_DIR}bin/midi2exp {m2e_switches} midi/{druid}_note.mid midi/{druid}_exp.mid"
    logging.info(f"Running expression extraction on midi/{druid}_note.mid")
    system(cmd)
    return True


def concoct_roll_description(metadata, iiif_manifest):
    # Note that the CSV lists of DRUIDs also provide descriptions for each roll, but
    # this may not always be the case.
    composer = None
    performer = None
    description = None

    for item in iiif_manifest["metadata"]:
        if item["label"] == "Contributor":
            if item["value"].find("composer") != -1:
                composer = item["value"]
            if item["value"].find("instrumentalist") != -1:
                performer = item["value"]

    if metadata["composer"]:
        composer = metadata["composer"]
    if metadata["performer"]:
        performer = metadata["performer"]

    if composer is not None:
        composer = composer.split(",")[0].strip()

    # It might be preferable to use the "Statement of Responsiblity" instead of
    # combining the composer and performer surnames, because it is more likely
    # to provide better composer/arranger information, e.g., "Wagner-Brassin".
    # Practically, however, this content has a wide range of formats --
    # parentheticals and semicolons abound -- and also uses different and
    # inconsistent name spelling conversations relative to the rest of the
    # metadata, so on the whole it probably should not be used.
    # if metadata["responsibility"]:
    #    composer = metadata["responsibility"].lstrip().rstrip(" .,")

    if composer is not None:
        description = composer

    if performer is not None:
        if description is not None:
            description += "/" + performer.split(",")[0].strip()
        else:
            description = performer.split(",")[0].strip()

    # The IIIF manifest has already concocted a title from the MODS, so use it
    title = iiif_manifest["label"].replace(" : ", ": ").strip().capitalize()

    if description is not None:
        description += " - " + title
    else:
        description = title

    return description


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    DRUIDS = get_druids_from_files()

    catalog_entries = []

    for druid in DRUIDS:

        if druid in DUPLICATES_TO_SKIP:
            continue

        metadata = get_metadata_for_druid(druid)

        iiif_manifest = get_iiif_manifest(druid)

        if PROCESS_IMAGE_FILES:
            tiff_url = get_tiff_url(iiif_manifest)
            if tiff_url is None:
                logging.error(
                    f"Image URL not found in manifest for {druid}, skpping roll"
                )
                continue
            roll_image = get_roll_image(get_tiff_url(iiif_manifest), druid)
            parse_roll_image(druid, roll_image, metadata["type"])

        if EXTRACT_MIDI_FILES:
            extract_midi_from_analysis(druid)

            if APPLY_MIDI_EXPRESSIONS:
                apply_midi_expressions(druid, metadata["type"])

            # Use the expression MIDI if available, otherwise use the notes MIDI
            if Path(f"midi/{druid}_exp.mid").exists():
                copy(Path(f"midi/{druid}_exp.mid"), Path(f"midi/{druid}.mid"))
            elif Path(f"midi/{druid}_note.mid").exists():
                copy(Path(f"midi/{druid}_note.mid"), Path(f"midi/{druid}.mid"))

        if WRITE_TEMPO_MAPS:
            metadata["tempoMap"] = build_tempo_map_from_midi(druid)

        roll_data, hole_data = get_hole_data(druid)
        if hole_data:
            metadata["holeData"] = remap_hole_data(roll_data, hole_data)
        else:
            metadata["holeData"] = None
        write_json(druid, metadata)

        if BUILD_CATALOG:
            catalog_entries.append(
                {
                    "druid": druid,
                    "title": concoct_roll_description(metadata, iiif_manifest),
                    "image_url": get_iiif_url(iiif_manifest),
                    "type": metadata["type"],
                    "label": metadata["label"],
                }
            )

    if BUILD_CATALOG:
        sorted_catalog = sorted(catalog_entries, key=lambda i: i["title"])
        with open("catalog.json", "w", encoding="utf8") as catalog_file:
            json.dump(
                sorted_catalog,
                catalog_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )


if __name__ == "__main__":
    main()
