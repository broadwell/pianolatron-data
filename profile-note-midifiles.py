#!/usr/bin/env python3

import json
import logging
from pathlib import Path
import statistics

from mido import MidiFile

RECOMPUTE_STATS = False

SUMMARIZE_ALL = True

# This threshold is roughly the mean inter-note-on distance (23.4) plus five
# average standard deviations of roll inter-note-on distances (57 * 5)
NOTE_ON_DIST_OUTLIER_THRESHOLD = 308


def get_midi_hole_events(midi_filepath):

    midi = MidiFile(midi_filepath)

    # Track 1 contains tempo events and metadata for all rolls; rolls parsed as
    # reproducing rolls will have 4 further tracks containing bass/treble notes
    # (2-3) and control (4-5) perforations in their _raw.mid and _note.mid
    # files, and just 1 track of these for non-reproducing rolls. Adjacent/
    # contiguous perforations on these tracks are consolidated in the _note.mid
    # files.

    EVENT_TYPES = ["note_on", "note_off"]

    total_notes = 0

    event_timings = {event_type: {} for event_type in EVENT_TYPES}

    for track in midi.tracks[1:]:
        current_tick = 0
        for event in track:
            # Hole groupings are bounded by note_on and note_off events
            if event.type not in EVENT_TYPES:
                continue

            if event.type == "note_on":
                total_notes += 1

            current_tick += event.time
            if current_tick in event_timings[event.type]:
                event_timings[event.type][current_tick] += 1
            else:
                event_timings[event.type][current_tick] = 1

            # XXX Can use event.note (MIDI note number) to build a full note:
            # time matrix, which could be compressed/processed with SciPy

    return {"total_notes": total_notes, "event_timings": event_timings}


def get_note_on_distances(note_events_report, druid):
    note_on_distances = []

    note_on_ticks = sorted(
        [
            int(x)
            for x in list(note_events_report["event_timings"]["note_on"].keys())
        ]
    )

    for i, tick in enumerate(note_on_ticks):

        if i == 0:
            continue

        previous_tick = note_on_ticks[i - 1]

        distance_to_last = int(tick) - int(previous_tick)

        if ((float(tick) / float(len(note_on_ticks))) < 0.10) and (
            distance_to_last > NOTE_ON_DIST_OUTLIER_THRESHOLD
        ):
            logging.info(
                f"{druid}: large inter-note distance in first 10% of roll: {distance_to_last} btwn ticks {previous_tick}-{tick}"
            )

        note_on_distances.append(distance_to_last)

    return note_on_distances


def get_note_on_stats(druid):

    if not RECOMPUTE_STATS and Path(f"reports/{druid}.json").exists():
        note_events_report = json.load(open(Path(f"reports/{druid}.json"), "r"))
        return note_events_report["note_on_statistics"]

    note_midi_filepath = Path(f"midi/note/{druid}_note.mid")

    note_events_report = get_midi_hole_events(note_midi_filepath)

    note_on_distances = get_note_on_distances(note_events_report, druid)

    note_on_statistics = {}
    note_on_statistics["median_note_on_distance"] = statistics.median(
        note_on_distances
    )
    note_on_statistics["mean_note_on_distance"] = statistics.mean(
        note_on_distances
    )
    note_on_statistics["note_on_distance_stdev"] = statistics.stdev(
        note_on_distances
    )

    # logging.info(f"{druid}\n{note_on_statistics}")

    note_events_report["note_on_statistics"] = note_on_statistics

    # Dump these to JSON files
    with open(f"reports/{druid}.json", "w") as jsonfile:
        json.dump(note_events_report, jsonfile)

    return note_on_statistics


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    all_note_on_stats = []

    all_note_on_distances = []

    for note_midi_filepath in Path("midi/note/").glob("*_note.mid"):
        druid = note_midi_filepath.stem.split("_")[0]

        note_on_stats = get_note_on_stats(druid)

        all_note_on_stats.append(note_on_stats)

        if SUMMARIZE_ALL:
            note_events_report = json.load(
                open(Path(f"reports/{druid}.json"), "r")
            )
            note_on_distances = get_note_on_distances(note_events_report, druid)
            all_note_on_distances.extend(note_on_distances)

    logging.info(
        f"median of all note on distances: {statistics.median(all_note_on_distances)}"
    )
    logging.info(
        f"mean of all note on distances: {statistics.mean(all_note_on_distances)}"
    )
    logging.info(
        f"stdev of all note on distances: {statistics.stdev(all_note_on_distances)}"
    )

    all_note_on_means = []
    all_note_on_medians = []
    all_note_on_stdevs = []
    for note_on_stats in all_note_on_stats:
        all_note_on_medians.append(note_on_stats["median_note_on_distance"])
        all_note_on_means.append(note_on_stats["mean_note_on_distance"])
        all_note_on_stdevs.append(note_on_stats["note_on_distance_stdev"])

    logging.info(
        f"mean of all note on distance medians: {statistics.median(all_note_on_medians)}"
    )
    logging.info(
        f"stdev of all note on distance medians: {statistics.stdev(all_note_on_medians)}"
    )
    logging.info(
        f"mean of all note on distance means: {statistics.mean(all_note_on_means)}"
    )
    logging.info(
        f"stdev of all note on distance means: {statistics.stdev(all_note_on_means)}"
    )
    logging.info(
        f"mean of all note on distance stdevs: {statistics.mean(all_note_on_stdevs)}"
    )
    logging.info(
        f"stdev of all note on distance stdevs: {statistics.stdev(all_note_on_stdevs)}"
    )


if __name__ == "__main__":
    main()
