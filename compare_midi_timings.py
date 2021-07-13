#!/usr/bin/env python3

import logging
import operator
from pathlib import Path

import pickle

from Bio import pairwise2
import mido

EVENT_TYPES = ["note_on", "set_tempo"]  # , "note_off"]

# The unaccelerated note MIDI file for the roll
unaccel = "11381959_no_accel-exp_420tpq.mid"
# A MIDI file generated from the same roll, with acceleration
accel = "11381959-peter-Figaro Fantasie, Horowitz GW.mid"

# Used for all output filenames
roll_id = unaccel.split("-")[0].split("_")[0]
# Used in visualization plots
roll_title = "Liszt/Busoni-Horowitz Figaro Fantasy Welte 4128"

NOTES = ["A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"]
midiNumberNames = {}

for midi_number in range(21, 109):
    note_name = NOTES[(midi_number - 21) % 12]
    octave_number = int((midi_number - 12) / 12)
    midiNumberNames[midi_number] = note_name + str(octave_number)


def get_midi_speed(midi_filepath):
    midifile = mido.MidiFile(midi_filepath)

    tpb = midifile.ticks_per_beat
    starting_tempo = 0.0

    logging.info(f"{midi_filepath} ticks per beat: {tpb}")

    if len(midifile.tracks) > 3:
        unitrack = mido.merge_tracks(midifile.tracks[:3])
    else:
        unitrack = mido.merge_tracks(midifile.tracks)

    for event in unitrack:
        if event.type == "set_tempo":
            starting_tempo = event.tempo
            break

    return (tpb, starting_tempo)


def get_note_timings(midi_filepath, use_this_tpb=None, use_this_tempo=None):
    logging.info(f"Getting note timings for {midi_filepath}")

    midifile = mido.MidiFile(midi_filepath)

    if use_this_tpb is not None:
        midifile.ticks_per_beat = use_this_tpb

    tpb = midifile.ticks_per_beat

    logging.info(f"Ticks per beat: {tpb}")

    if len(midifile.tracks) > 3:
        unitrack = mido.merge_tracks(midifile.tracks[:3])
    else:
        unitrack = mido.merge_tracks(midifile.tracks)

    logging.info(f"Total messages in combined track: {len(unitrack)}")

    current_tick = 0
    total_notes = 0
    current_tempo = 0.0  # In microseconds per beat

    note_events = []

    for event in unitrack:
        # Hole groupings are bounded by note_on and note_off events

        current_tick += event.time

        if event.type not in EVENT_TYPES:
            continue

        if event.type == "set_tempo":

            logging.info(
                f"Tempo at {event.time}: {event.tempo} ms per beat ({mido.tempo2bpm(event.tempo)} bpm)"
            )
            if use_this_tempo is not None:
                logging.info(
                    f"Overriding tempo at {event.time} to {use_this_tempo} ms per beat ({mido.tempo2bpm(use_this_tempo)} bpm)"
                )
                event.tempo = use_this_tempo

            current_tempo = event.tempo

        if event.type == "note_on":
            total_notes += 1
            event_time_in_seconds = mido.tick2second(
                current_tick, tpb, current_tempo
            )
            note_events.append(
                (
                    event.note,
                    event.time,
                    current_tick,
                    event_time_in_seconds,
                )
            )

    logging.info(f"Total note_on events: {total_notes}")

    # Sort simultaneous note events by note number, low to high
    note_events.sort(key=operator.itemgetter(2, 0))

    return note_events


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # accel_file_tpb, accel_file_tempo = get_midi_speed(accel)

    # unaccel_events = get_note_timings(unaccel, accel_file_tpb, accel_file_tempo)
    unaccel_events = get_note_timings(unaccel)
    accel_events = get_note_timings(accel)

    unaccel_notes = [item[0] for item in unaccel_events]
    accel_notes = [item[0] for item in accel_events]

    unaccel_chars = []

    unaccel_chars = [chr(note).replace("-", "~") for note in unaccel_notes]
    accel_chars = [chr(note).replace("-", "~") for note in accel_notes]

    gap_char = "-"

    # This shouldn't happen, but check to be sure
    if (gap_char in unaccel_chars) or (gap_char in accel_chars):
        logging.info(
            f"{gap_char} is in the characterized strings, need to use a different gap char"
        )
        return

    alignment_fn = roll_id + "alignment.p"

    # The pickled alignment data is just the two sequences
    if Path(f"{alignment_fn}").exists():
        logging.info("Loading pairwise alignment")
        unaccel_seq, accel_seq = pickle.load(open(alignment_fn, "rb"))
    else:
        logging.info("Computing pairwise alignment")
        alignments = pairwise2.align.globalxx(
            unaccel_chars,
            accel_chars,
            gap_char=gap_char,
            one_alignment_only=True,
        )
        alignment = alignments[0]
        unaccel_seq = alignment.seqA
        accel_seq = alignment.seqB
        pickle.dump((unaccel_seq, accel_seq), open(alignment_fn, "wb"))

    # logging.info(f"Found {len(alignments)} alignments")
    # 'count', 'end', 'index', 'score', 'seqA', 'seqB', 'start'

    # for alignment in alignments:
    #     logging.info(
    #         f"{alignment.start} {alignment.end} {len(alignment.seqA)} {len(alignment.seqB)} {alignment.score}"
    #     )

    unaccel_counter = 0
    accel_counter = 0

    logging.info(
        f"total unmatched notes in unaccelerated MIDI: {unaccel_seq.count('-')}"
    )
    logging.info(
        f"total unmatched notes in accelerated MIDI: {accel_seq.count('-')}"
    )

    # Accumulate data about matched MIDI messages between the sequences
    logging.info("ACCEL MATCH_INFO UNACCEL MATCH_INFO")

    divergences_by_sec = {}

    pct_divergences_by_sec = {}

    matched_events_by_unaccel_ticks = {}

    for i, unaccel_item in enumerate(unaccel_seq):

        accel_item = accel_seq[i]

        if accel_item != "-" and unaccel_item != "-":
            unaccel_midi_number = ord(unaccel_item.replace("~", "-"))
            accel_midi_number = ord(accel_item.replace("~", "-"))
            unaccel_event = unaccel_events[unaccel_counter]
            unaccel_note_name = midiNumberNames[unaccel_event[0]]
            accel_event = accel_events[accel_counter]
            accel_note_name = midiNumberNames[accel_event[0]]

            if unaccel_midi_number != unaccel_event[0]:
                logging.error(
                    f"Unaccel MIDI numbers don't align: {unaccel_midi_number}, {unaccel_event[0]}"
                )
                return
            if accel_midi_number != accel_event[0]:
                logging.error(
                    f"Accel MIDI numbers don't align: {accel_midi_number}, {accel_event[0]}"
                )
                return
            if accel_midi_number != unaccel_midi_number:
                logging.error(
                    f"Matched MIDI numbers don't align! {accel_midi_number}, {accel_midi_number}"
                )
                return

            unaccel_sec = unaccel_event[3]
            accel_sec = accel_event[3]

            sec = int(unaccel_sec)

            divergence = unaccel_sec - accel_sec

            pct_divergence = (unaccel_sec - accel_sec) / unaccel_sec * 100

            if sec not in divergences_by_sec:
                divergences_by_sec[sec] = [divergence]
                pct_divergences_by_sec[sec] = [pct_divergence]
            else:
                divergences_by_sec[sec].append(divergence)
                pct_divergences_by_sec[sec].append(pct_divergence)

            unaccel_tick = unaccel_event[2]

            if unaccel_tick not in matched_events_by_unaccel_ticks:
                matched_events_by_unaccel_ticks[unaccel_tick] = [
                    [unaccel_event, accel_event]
                ]
            else:
                matched_events_by_unaccel_ticks[unaccel_tick].append(
                    [unaccel_event, accel_event]
                )

            # logging.info(
            #     f"{unaccel_note_name} at {unaccel_event[3]}s matches {accel_note_name} at {accel_event[3]}s"
            # )

        if str(unaccel_item) != "-":
            unaccel_counter += 1

        if str(accel_item) != "-":
            accel_counter += 1

    # Calculate overall and recent velocities at roughly each foot of the
    # unaccelerated roll

    foot = 0
    last_unaccel_time = 0.0
    last_unaccel_tick = 0
    last_accel_time = 0.0

    accel_v = []
    accel_t = []

    for unaccel_tick in sorted(matched_events_by_unaccel_ticks):
        if int(unaccel_tick / 3600) > foot:
            foot += 1
            actual_feet_overall = float(unaccel_tick) / 3600.0
            actual_feet_delta = (
                float(unaccel_tick) - float(last_unaccel_tick)
            ) / 3600.0
            matched_event = matched_events_by_unaccel_ticks[unaccel_tick][0]
            if unaccel_tick != matched_event[0][2]:
                logging.error(
                    f"Unaccel ticks do not match: {unaccel_tick}, {matched_event[0][2]}"
                )
                return
            unaccel_time = matched_event[0][3]
            accel_tick = matched_event[1][2]
            accel_time = matched_event[1][3]
            last_unaccel_fpm = (
                actual_feet_delta / (unaccel_time - last_unaccel_time) * 60
            )
            last_accel_fpm = (
                actual_feet_delta / (accel_time - last_accel_time) * 60
            )
            overall_unaccel_fpm = actual_feet_overall / unaccel_time * 60
            overall_accel_fpm = actual_feet_overall / accel_time * 60

            acceleration = 0.0
            if len(accel_v) > 11:
                acceleration = (last_accel_fpm - accel_v[11]) / (
                    (accel_time - accel_t[11])
                )

            logging.info(
                f"After {actual_feet_overall}ft ({unaccel_tick} unaccel ticks), unaccel time is {unaccel_time}s, accel tick is {accel_tick}, time is {accel_time}s"
            )
            logging.info(
                f"Unaccelerated last v: {last_unaccel_fpm}ft/m, overall: {overall_unaccel_fpm}ft/m, accelerated last v: {last_accel_fpm}ft/m, overall: {overall_accel_fpm}ft/m"
            )
            logging.info(
                f"Average acceleration since ft 10: {acceleration}ft/m^2"
            )
            accel_t.append(accel_time / 60.0)
            accel_v.append(overall_accel_fpm)
            last_unaccel_time = unaccel_time
            last_unaccel_tick = unaccel_tick
            last_accel_time = accel_time

    # Derive average acceleration over the roll and plot it

    acceleration = (accel_v[-1] - accel_v[1]) / ((accel_t[-1] - accel_t[1]))
    logging.info(f"Average acceleration since ft 1: {acceleration}ft/m^2")

    import numpy as np
    import matplotlib.pyplot as plt
    from scipy.stats import linregress

    regression = linregress(accel_t, accel_v)
    print(regression)

    coef = np.polyfit(accel_t, accel_v, 1)
    poly1d_fn = np.poly1d(coef)
    plt.plot(accel_t, accel_v, "co", accel_t, poly1d_fn(accel_t), "--k")
    plt.xlim(0, int(max(accel_t) + 1))
    plt.ylim(int(min(accel_v)), int(max(accel_v)) + 1)
    plt.title(roll_title)
    plt.xlabel("minutes")
    plt.ylabel("feet/minute")
    plt.legend(["Observed velocities", "Best-fit acceleration"])
    plt.savefig(roll_id + "_acceleration.png")


if __name__ == "__main__":
    main()
