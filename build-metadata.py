#!/usr/bin/env python3

""" Build per-DRUID metadata .json files, playable .mid MIDI files, and     """
""" catalog.json file listing all rolls available for consumption by the    """
""" Pianolatron app, downloading metadata files and the images themselves   """
""" (if not already cached), then using external tools to generate the roll """
""" image processing analysis output, MIDI file types and ultimately JSON   """
""" files needed to present the full roll collection in the app.            """

from csv import DictReader
import json
import logging
from os import system
from pathlib import Path
import re
from shutil import copy, copyfileobj
import sys

from lxml import etree
from mido import MidiFile, tempo2bpm
from PIL import Image
import requests

# Otherwise Pillow will refuse to open large images
Image.MAX_IMAGE_PIXELS = None

BUILD_CATALOG = True  # Write a new catalog.json file
PROCESS_IMAGE_FILES = False  # Download image (if needed) and parse to DRUID.txt
REPROCESS_IMAGES = False  # Re-parse the image even if a DRUID.txt file exists
EXTRACT_MIDI_FILES = False  # Extract raw and note MIDI from DRUID.txt output
REPROCESS_MIDI = False  # Extract MIDI files even if a DRUID.mid file exists
APPLY_MIDI_EXPRESSIONS = False  # Run midi2exp and use output as DRUID.mid
WRITE_TEMPO_MAPS = False

# XXX THIS IS NOT IDEMPOTENT -- it will keep flipping the image every time.
# Rolls should only be listed here for one execution of the script!
ROLLS_TO_MIRROR = [
    # "yt837kd6607",
    # "ws749sk4778",
    # "hs635sh6729"
    # "zw485gh6070",
    # "xr682fm1233",
    # "mx460bt7026",
    # "cs175wr2428",
    # "bz327kz4744",
    # "wv912mm2332",
    # "jw822wm2644",
    # "fv104hn7521",
    # "fy803vj4057",
]

DISREGARD_REWIND_HOLE = [
    "mh156nr8259",
    "cd381jt9273",
]

# These are either duplicates of existing rolls, or rolls that are listed in
# the DRUIDs files but have mysteriously disappeared from the catalog
ROLLS_TO_SKIP = ["rr052wh1991", "hm136vg1420"]

ROLL_TYPES = {
    "Welte-Mignon red roll (T-100)": "welte-red",
    "Welte-Mignon red roll (T-100).": "welte-red",
    "Welte-Mignon red roll (T-100)..": "welte-red",  # Ugh
    "Scale: 88n.": "88-note",
    "Scale: 65n.": "65-note",
    "88n": "88-note",
    "standard": "88-note",
    "non-reproducing": "88-note",
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

    # Takes an array of potential xpaths, returns the first one that matches,
    # or None
    def get_value_by_xpaths(xpaths):
        for xpath in xpaths:
            value = get_value_by_xpath(xpath)
            if value is not None:
                return value
        return value

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

    roll_type = None
    type_note = get_value_by_xpath(
        "x:physicalDescription/x:note[@displayLabel='Roll type']/text()"
    )
    if type_note is not None and type_note in ROLL_TYPES:
        roll_type = ROLL_TYPES[type_note]

    if roll_type == None:
        for note in xml_tree.xpath("(x:note)", namespaces=NS):
            if note is not None and note.text in ROLL_TYPES:
                roll_type = ROLL_TYPES[note.text]

    if roll_type == None:
        roll_type = "NA"

    metadata = {
        "title": get_value_by_xpath("(x:titleInfo/x:title)[1]/text()"),
        "composer": get_value_by_xpath(
            "x:name[descendant::x:roleTerm[text()='composer']]/"
            "x:namePart[not(@type='date')]/text()"
        ),
        "performer": get_value_by_xpath(
            "x:name[descendant::x:roleTerm[text()='instrumentalist']]/"
            "x:namePart[not(@type='date')]/text()"
        ),
        "arranger": get_value_by_xpaths(
            [
                "x:name[descendant::x:roleTerm[text()='arranger of music']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='arranger']]/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "original_composer": get_value_by_xpaths(
            [
                "x:relatedItem[@otherType='Based on (work) :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@otherType='Based on']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@otherType='Adaptation of (work) :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@otherType='Adaptation of']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@otherType='Arrangement of :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@otherType='Arrangement of']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "label": get_value_by_xpaths(
            [
                "x:identifier[@type='issue number' and @displayLabel='Roll number']/text()",
                "x:identifier[@type='issue number']/text()",
            ]
        ),
        "publisher": get_value_by_xpaths(
            [
                "x:identifier[@type='publisher']/text()",
                "x:originInfo[@eventType='publication']/publisher/text()",
            ]
        ),
        "number": get_value_by_xpath(
            "x:identifier[@type='publisher number']/text()"
        ),
        "publish_date": get_value_by_xpath(
            "x:originInfo[@eventType='publication']/x:dateIssued[@keyDate='yes']/text()"
        ),
        "recording_date": get_value_by_xpaths(
            [
                "x:note[@type='venue']/text()",
                "x:originInfo[@eventType='publication']/x:dateCaptured/text()",
            ]
        ),
        "call_number": get_value_by_xpath("x:location/x:shelfLocator/text()"),
        "type": roll_type,
        "PURL": PURL_BASE + druid,
    }

    return metadata


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


def merge_midi_velocities(roll_data, hole_data, druid):

    midi_filepath = Path(f"midi/{druid}.mid")

    if not midi_filepath.exists():
        return hole_data

    first_music_px = int(roll_data["FIRST_HOLE"].removesuffix("px"))

    midi = MidiFile(midi_filepath)

    tick_notes_velocities = {}

    for note_track in midi.tracks[1:3]:
        current_tick = 0
        for event in note_track:
            current_tick += event.time
            if event.type == "note_on":
                # XXX Not sure why some note events have velocity=1
                if event.velocity > 1:
                    if current_tick in tick_notes_velocities:
                        tick_notes_velocities[current_tick][
                            event.note
                        ] = event.velocity
                    else:
                        tick_notes_velocities[current_tick] = {
                            event.note: event.velocity
                        }

    for i in range(len(hole_data)):
        hole = hole_data[i]

        hole_tick = int(hole["ORIGIN_ROW"]) - first_music_px
        hole_midi = int(hole["MIDI_KEY"])

        if (
            hole_tick in tick_notes_velocities
            and hole_midi in tick_notes_velocities[hole_tick]
        ):
            hole_data[i]["VELOCITY"] = tick_notes_velocities[hole_tick][
                hole_midi
            ]

    return hole_data


def get_hole_data(druid):
    txt_filepath = Path(f"txt/{druid}.txt")

    if not txt_filepath.exists():
        return None, None

    roll_keys = [
        "AVG_HOLE_WIDTH",
        "FIRST_HOLE",
        "IMAGE_WIDTH",
        "IMAGE_LENGTH",
        # "TRACKER_HOLES",
        # "ROLL_WIDTH",
        # "HARD_MARGIN_BASS",
        # "HARD_MARGIN_TREBLE",
        # "HOLE_SEPARATION",
        # "HOLE_OFFSET",
    ]

    hole_keys = [
        "NOTE_ATTACK",
        "WIDTH_COL",
        "ORIGIN_COL",
        "ORIGIN_ROW",
        "OFF_TIME",
        "MIDI_KEY",
        # "TRACKER_HOLE",
    ]

    roll_data = {}
    hole_data = []

    dropped_holes = 0

    with txt_filepath.open("r") as _fh:
        while (line := _fh.readline()) and line != "@@BEGIN: HOLES\n":
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                if key in roll_keys:
                    roll_data[key] = value.replace("px", "").strip()

        while (line := _fh.readline()) and line != "@@END: HOLES\n":
            if line == "@@BEGIN: HOLE\n":
                hole = {}
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                if key in hole_keys:
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


def remap_hole_data(hole_data):

    new_hole_data = []

    for hole in hole_data:

        new_hole = {
            "x": hole["ORIGIN_COL"],
            "y": hole["ORIGIN_ROW"],
            "w": hole["WIDTH_COL"],
            "h": hole["OFF_TIME"] - hole["ORIGIN_ROW"],
            "m": hole["MIDI_KEY"],
            # "t": hole["TRACKER_HOLE"],
        }
        if "VELOCITY" in hole:
            new_hole["v"] = hole["VELOCITY"]

        new_hole_data.append(new_hole)

    return new_hole_data


def write_json(druid, metadata):
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
    if not image_filepath.exists():
        response = request_image(image_url)
        with open(image_filepath, "wb") as image_file:
            copyfileobj(response.raw, image_file)
        del response
    if druid in ROLLS_TO_MIRROR:
        image_filepath = flip_image_left_right(image_filepath)
    return image_filepath


def flip_image_left_right(image_filepath):
    logging.info(f"Flipping image left-right: {image_filepath}")
    im = Image.open(image_filepath)
    out = im.transpose(Image.FLIP_LEFT_RIGHT)
    out.save(image_filepath)
    return image_filepath


def parse_roll_image(druid, image_filepath, roll_type):
    if (
        image_filepath is None
        or roll_type == "NA"
        or not Path(f"{ROLL_PARSER_DIR}bin/tiff2holes").exists()
        or (Path(f"txt/{druid}.txt").exists() and not REPROCESS_IMAGES)
    ):
        return

    if roll_type == "welte-red":
        t2h_switches = "-m -r"
    elif roll_type == "88-note":
        t2h_switches = "-m -8"
    elif roll_type == "65-note":
        t2h_switches = "-m -5"

    if druid in DISREGARD_REWIND_HOLE:
        t2h_switches += " -s"

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
        cmd = f"{BINASC_DIR}binasc {binasc_file_path} -c midi/{midi_type}/{druid}_{midi_type}.mid"
        system(cmd)


def extract_midi_from_analysis(druid):
    if not Path(f"txt/{druid}.txt").exists() or (
        not REPROCESS_MIDI and Path(f"midi/{druid}.mid").exists()
    ):
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
        not Path(f"midi/note/{druid}_note.mid").exists()
        or not Path(f"{MIDI2EXP_DIR}bin/midi2exp").exists()
    ):
        return
    # There's a switch, -r, to remove the control tracks (3-4, 0-indexed)
    m2e_switches = ""
    if roll_type == "welte-red":
        m2e_switches = (
            "-w -r -adjust-hole-lengths"  # add --ac 0 for no acceleration
        )
    cmd = f"{MIDI2EXP_DIR}bin/midi2exp {m2e_switches} midi/note/{druid}_note.mid midi/exp/{druid}_exp.mid"
    logging.info(f"Running expression extraction on midi/note/{druid}_note.mid")
    system(cmd)
    return True


def merge_iiif_metadata(metadata, iiif_manifest):
    # Note that the CSV lists of DRUIDs also provide descriptions for each roll, but
    # these may not always be available.
    composer = None
    performer = None
    arranger = None
    description = None
    publisher = None
    number = None

    for item in iiif_manifest["metadata"]:
        if item["label"] == "Contributor":
            if item["value"].lower().find("composer") != -1:
                composer = item["value"].split("(")[0].strip()
            if item["value"].lower().find("instrumentalist") != -1:
                performer = item["value"].split("(")[0].strip()
            if item["value"].lower().find("arranger of music") != -1:
                arranger = item["value"].split("(")[0].strip()
            # This is usually more verbose than the value from the MODS
            # or from the first-level "Publisher" key below
            # if item["value"].lower().find("publisher") != -1:
            #    publisher = item["value"].split("(")[0].strip()
        elif item["label"] == "Publisher":
            publisher = item["value"].strip()

    if metadata["composer"] is not None:
        composer = metadata["composer"]
    if metadata["performer"] is not None:
        performer = metadata["performer"]
    if metadata["arranger"] is not None:
        arranger = metadata["arranger"]
    if metadata["publisher"] is not None:
        publisher = metadata["publisher"]
    if metadata["number"] is not None:
        number = metadata["number"]
    else:
        if (
            metadata["label"] is not None
            and len(metadata["label"].split(" ")) == 2
        ):
            number = metadata["label"].split(" ")[0]

    if metadata["label"] is None:
        if number is None:
            number = "----"
        metadata["label"] = number + " " + publisher

    original_composer = metadata["original_composer"]

    if (
        original_composer is not None
        and composer is not None
        and original_composer.split(",")[0].strip()
        != composer.split(",")[0].strip()
    ):
        description = f"{original_composer.split(',')[0].strip()}-{composer.split(',')[0].strip()}"
    elif composer is not None:
        description = composer.split(",")[0].strip()

    if (
        arranger is not None
        and description is not None
        and arranger.split(",")[0].strip() != composer.split(",")[0].strip()
    ):
        description += f"-{arranger.split(',')[0].strip()}"
    elif arranger is not None:
        description = arranger.split(",")[0].strip()

    if performer is not None and description is not None:
        description += "/" + performer.split(",")[0].strip()
    elif performer is not None:
        description = performer.split(",")[0].strip()

    # The IIIF manifest has already concocted a title from the MODS
    title = iiif_manifest["label"].replace(" : ", ": ").strip().capitalize()

    if description is not None:
        description += " - " + title
    else:
        description = title

    # Update the values that may have been changed above during the merge
    metadata["title"] = description
    metadata["composer"] = composer
    metadata["performer"] = performer
    metadata["arranger"] = arranger
    metadata["publisher"] = publisher
    metadata["number"] = number

    return metadata


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    DRUIDS = [
        "bs533ns1949",
        "jg717nb8731",
        "mf443ns5829",
        "hg709nf1997",
        "ht999gf1829",
        "jg489yw0942",
    ]

    # Providing a single DRUID on the cmd line overrides the list above
    if len(sys.argv) > 1:
        DRUIDS = [sys.argv[1]]

    if len(DRUIDS) == 0:
        DRUIDS = get_druids_from_files()

    catalog_entries = []

    for druid in DRUIDS:

        if druid in ROLLS_TO_SKIP:
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

            # Use expression MIDI if there & enabled, otherwise use note MIDI
            if (
                APPLY_MIDI_EXPRESSIONS
                and Path(f"midi/exp/{druid}_exp.mid").exists()
            ):
                copy(
                    Path(f"midi/exp/{druid}_exp.mid"), Path(f"midi/{druid}.mid")
                )
            elif Path(f"midi/note/{druid}_note.mid").exists():
                copy(
                    Path(f"midi/note/{druid}_note.mid"),
                    Path(f"midi/{druid}.mid"),
                )

        note_midi = MidiFile(Path(f"midi/note/{druid}_note.mid"))
        metadata["NOTE_MIDI_TPQ"] = note_midi.ticks_per_beat

        if WRITE_TEMPO_MAPS:
            metadata["tempoMap"] = build_tempo_map_from_midi(druid)

        roll_data, hole_data = get_hole_data(druid)

        metadata = merge_iiif_metadata(metadata, iiif_manifest)

        for key in roll_data:
            metadata[key] = roll_data[key]

        if hole_data:
            if metadata["type"] != "65-note":
                hole_data = merge_midi_velocities(roll_data, hole_data, druid)
            metadata["holeData"] = remap_hole_data(hole_data)
        else:
            metadata["holeData"] = None

        write_json(druid, metadata)

        if BUILD_CATALOG:
            catalog_entries.append(
                {
                    "druid": druid,
                    "title": metadata["title"],
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
            catalog_file.write("\n")


if __name__ == "__main__":
    main()
