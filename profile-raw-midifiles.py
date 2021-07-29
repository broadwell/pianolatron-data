#!/usr/bin/env python3

import json
import logging
import matplotlib.pyplot as plt
import numpy as np
import operator
from pathlib import Path
import statistics

from mido import MidiFile

RECOMPUTE_STATS = True

SUMMARIZE_ALL = True

PLOT_DISTRIBUTIONS = True


def get_midi_hole_events(midi_filepath):

    midi = MidiFile(midi_filepath)

    # Track 1 contains tempo events and metadata for all rolls; rolls parsed as
    # reproducing rolls will have 4 further tracks containing bass/treble notes
    # (2-3) and control (4-5) perforations in their _raw.mid and _note.mid
    # files, and just 1 track of these for non-reproducing rolls.

    total_notes = 0
    note_offs = 0
    types_seen = set()
    druid = midi_filepath.stem.split("_")[0]

    events_by_note = {}

    for track in midi.tracks[1:]:
        current_tick = 0
        for event in track:
            # Holes are bounded by note_on and note_off events
            types_seen.add(event.type)

            if event.type != "note_on":
                continue

            if event.velocity == 0:
                event_name = "END"
                note_offs += 1
            else:
                event_name = "BEGIN"
                total_notes += 1

            current_tick += event.time

            if event.note in events_by_note:
                events_by_note[event.note].append([current_tick, event_name])
            else:
                events_by_note[event.note] = [[current_tick, event_name]]

    return {"total_notes": total_notes, "events_by_note": events_by_note}


def get_inter_note_distances(note_events_report, druid):

    events_by_note = note_events_report["events_by_note"]
    inter_note_distances = []

    hole_diameters = []

    for note in events_by_note:
        # Sort events by tick, then by BEGIN -> END
        note_events = events_by_note[note]
        note_events.sort(key=operator.itemgetter(0, 1))

        last_note_end = None
        last_note_start = None
        for event in note_events:
            if event[1] == "BEGIN":
                if last_note_end is not None:
                    inter_note_distance = event[0] - last_note_end
                    inter_note_distances.append(inter_note_distance)
                last_note_end = None
                last_note_start = event[0]
            elif event[1] == "END":
                last_note_end = event[0]
                if last_note_start is not None:
                    hole_diameter = event[0] - last_note_start
                    hole_diameters.append(hole_diameter)
                last_note_start = None
            else:
                logging.error(
                    f"NON-NOTE EVENT! {event[1]} at {event[0]} ticks for note {note}"
                )

    return inter_note_distances, hole_diameters


def get_inter_note_stats(druid):

    if not RECOMPUTE_STATS and Path(f"reports/{druid}_raw.json").exists():
        note_events_report = json.load(
            open(Path(f"reports/{druid}_raw.json"), "r")
        )
        return note_events_report["inter_note_statistics"]

    midi_filepath = Path(f"midi/raw/{druid}_raw.mid")

    note_events_report = get_midi_hole_events(midi_filepath)

    inter_note_distances, hole_diameters = get_inter_note_distances(
        note_events_report, druid
    )

    inter_note_statistics = {}
    inter_note_statistics["median_inter_note_distance"] = statistics.median(
        inter_note_distances
    )
    inter_note_statistics["mean_inter_note_distance"] = statistics.mean(
        inter_note_distances
    )
    inter_note_statistics["inter_note_distance_stdev"] = statistics.stdev(
        inter_note_distances
    )
    inter_note_statistics["inter_note_distance_mode"] = statistics.mode(
        inter_note_distances
    )

    inter_note_statistics["hole_length_median"] = statistics.median(
        hole_diameters
    )
    inter_note_statistics["hole_length_mean"] = statistics.mean(hole_diameters)

    if (
        inter_note_statistics["hole_length_median"]
        < inter_note_statistics["median_inter_note_distance"]
    ):
        logging.info(
            f"{druid} hole length median: {inter_note_statistics['hole_length_median']}, median inter-hole distance: {inter_note_statistics['median_inter_note_distance']}, mode: {inter_note_statistics['inter_note_distance_mode']}"
        )

        if PLOT_DISTRIBUTIONS:

            dist_bins = {}
            for dist in inter_note_distances:
                if dist in dist_bins:
                    dist_bins[dist] += 1
                else:
                    dist_bins[dist] = 1

            dist_x = [key for key in sorted(dist_bins)]
            dist_y = [dist_bins[dist] for dist in dist_x]

            dist_series = []
            for x in range(0, max(inter_note_distances)):
                if x in dist_bins:
                    dist_series.append(dist_bins[x])
                else:
                    dist_series.append(0)

            # plt.yscale("log")
            # plt.plot(dist_x[:100], dist_y[:100], "ro")
            # plt.title("Inter-hole distances for " + druid)
            # plt.xlabel("Distance between holes in pixels")
            # plt.ylabel("Occurrences of distance value")
            # plt.savefig("plots/" + druid + "_inter_hole_distances.png")

            # plt.clf()

            plt.plot(dist_series[:200])
            # plt.yscale("log")
            # plt.xscale("log")
            plt.title("Inter-hole distances for " + druid + " (log scales)")
            plt.xlabel("Distance between holes in pixels")
            plt.ylabel("Occurrences of distance value")
            plt.savefig("plots/" + druid + "_distance_series.png")

            plt.clf()

    # logging.info(f"{druid}\n{note_on_statistics}")

    note_events_report["inter_note_statistics"] = inter_note_statistics

    # Dump these to JSON files
    with open(f"reports/{druid}_raw.json", "w") as jsonfile:
        json.dump(note_events_report, jsonfile)

    return inter_note_statistics


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    all_inter_note_stats = []

    all_inter_note_distances = []

    for midi_filepath in Path("midi/raw/").glob("*_raw.mid"):
        druid = midi_filepath.stem.split("_")[0]

        inter_note_stats = get_inter_note_stats(druid)

        # logging.info(
        #     f"{druid} inter-note distance median: {inter_note_stats['median_inter_note_distance']}, mode: {inter_note_stats['inter_note_distance_mode']}, mean: {inter_note_stats['mean_inter_note_distance']:.4f})"
        # )

        all_inter_note_stats.append(inter_note_stats)

        if SUMMARIZE_ALL:
            note_events_report = json.load(
                open(Path(f"reports/{druid}_raw.json"), "r")
            )
            inter_note_distances, hole_diameters = get_inter_note_distances(
                note_events_report, druid
            )
            all_inter_note_distances.extend(inter_note_distances)

        # midi_file = MidiFile(midi_filepath)
        # duration = midi_file.length

    logging.info(
        f"median of all inter-note distances: {statistics.median(all_inter_note_distances)}"
    )
    logging.info(
        f"mean of all inter-note distances: {statistics.mean(all_inter_note_distances)}"
    )
    logging.info(
        f"stdev of all inter-note distances: {statistics.stdev(all_inter_note_distances)}"
    )

    all_inter_note_means = []
    all_inter_note_medians = []
    all_inter_note_stdevs = []
    for inter_note_stats in all_inter_note_stats:
        all_inter_note_medians.append(
            inter_note_stats["median_inter_note_distance"]
        )
        all_inter_note_means.append(
            inter_note_stats["mean_inter_note_distance"]
        )
        all_inter_note_stdevs.append(
            inter_note_stats["inter_note_distance_stdev"]
        )

    logging.info(
        f"mean of all inter-note distance medians: {statistics.median(all_inter_note_medians)}"
    )
    logging.info(
        f"stdev of all inter-note distance medians: {statistics.stdev(all_inter_note_medians)}"
    )
    logging.info(
        f"mean of all inter-note distance means: {statistics.mean(all_inter_note_means)}"
    )
    logging.info(
        f"stdev of all inter-note distance means: {statistics.stdev(all_inter_note_means)}"
    )
    logging.info(
        f"mean of all inter-note distance stdevs: {statistics.mean(all_inter_note_stdevs)}"
    )
    logging.info(
        f"stdev of all inter-note distance stdevs: {statistics.stdev(all_inter_note_stdevs)}"
    )


if __name__ == "__main__":
    main()
