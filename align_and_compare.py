#!/usr/bin/env python3

import logging
import operator
from pathlib import Path

from Bio import pairwise2
import librosa
import mido
import numpy as np
import pickle
import statistics

EVENT_TYPES = ["note_on", "set_tempo"]  # , "note_off"]

# The unaccelerated note MIDI file for the roll
unaccel = "red/mw870hc7232_no_accel-note.mid"
# unaccel = "green/11381959_no_accel-exp.mp3"
# unaccel = "green/11373080_no_accel-note.mid"
# A MIDI file generated from the same roll, with acceleration
accel = "red/Symphony 2-2,3 (Bthvn), Kiek RW.mid"
# accel = "green_figaro_mp3/JH493UyQ70E_NAXOS_Schmitz.mp3"
# accel = "green_figaro_mp3/UqinWTyQTKM_Julian_Dyer.mp3"
# accel = "green/11381959-exp-tempo72.mp3"
# accel = "green_figaro_mp3/Eipy7tcMUb4_Orchard_Bringins.mp3"
# accel = "green/11373080-peter-Hungarian Rhapsody 14, Gieseking GW.mid"

# unaccel_tps = None
unaccel_tps = 433  # Needs to be set if non-accelerated input is an audio file
# Number of audio samples per "window" for various time-series analyses
hop_length = 1024

# Used to differentiate multiple comparisons of the same roll ID
roll_tag = "peterp"
# Used for all output filenames
roll_id = unaccel.split("/")[-1].split("-")[0].split("_")[0] + "_" + roll_tag
# Used in visualization plots
roll_title = "Liszt/Busoni Horowitz Figaro Fantasy Welte 4128"
# roll_title = "Beethoven/Kiek Symphony 2, mvts. 2-3 Welte 3156"

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


def get_midi_timings(
    midi_filepath,
    use_this_tpb=None,
    use_this_tempo=None,
    use_chroma_numbers=False,
):
    logging.info(f"Getting note timings for {midi_filepath}")

    midifile = mido.MidiFile(midi_filepath)

    logging.info(f"MIDI duration is {midifile.length:.2f}s")

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
    current_tempo_start_tick = 0
    seconds_before_current_tempo = 0.0

    note_events = []

    for event in unitrack:
        # Hole groupings are bounded by note_on and note_off events

        current_tick += event.time

        if event.type not in EVENT_TYPES:
            continue

        if event.type == "set_tempo":

            logging.info(
                f"Setting tempo at {event.time} to {event.tempo} ms per beat ({mido.tempo2bpm(event.tempo)} bpm)"
            )

            if use_this_tempo is not None:
                logging.info(
                    f"Overriding tempo at {event.time} to {use_this_tempo} ms per beat ({mido.tempo2bpm(use_this_tempo)} bpm)"
                )
                event.tempo = use_this_tempo

            ticks_at_this_tempo = current_tick - current_tempo_start_tick
            seconds_before_current_tempo += mido.tick2second(
                ticks_at_this_tempo, tpb, current_tempo
            )

            current_tempo = event.tempo
            current_tempo_start_tick = current_tick

        if event.type == "note_on":
            total_notes += 1

            ticks_at_this_tempo = current_tick - current_tempo_start_tick

            event_time_in_seconds = (
                seconds_before_current_tempo
                + mido.tick2second(ticks_at_this_tempo, tpb, current_tempo)
            )

            note_number = event.note
            if use_chroma_numbers:
                note_number = event.note % 12

            note_events.append(
                (
                    note_number,
                    # event.time, # Delta from previous event; never used
                    current_tick,
                    event_time_in_seconds,
                )
            )

    logging.info(f"Total note_on events: {total_notes}")
    logging.info(
        f"Last event tick: {current_tick}, last note event time: {event_time_in_seconds:.4f}"
    )

    # Sort note events by tick, then by note number, low to high
    note_events.sort(key=operator.itemgetter(1, 0))

    return note_events


def get_chroma_features(audio_filepath):
    if Path(audio_filepath.replace(".mp3", "p")).exists():
        y, fs = pickle.load(open(audio_filepath.replace(".mp3", ".p"), "rb"))
    else:
        y, fs = librosa.load(audio_filepath)  # , sr=None)
        pickle.dump([y, fs], open(audio_filepath.replace(".mp3", ".p"), "wb"))

    duration = librosa.get_duration(y)

    logging.info(f"Duration: {duration}, Loaded sample rate: {fs}")
    total_samples = y.size
    logging.info(f"Length of samples: {total_samples}")

    # n_fft = int(fs / 2)

    # onsets = librosa.onset.onset_detect(
    #    y=y, sr=fs, hop_length=hop_length, units="time"
    # )

    logging.info(f"Getting pitch class chroma for {audio_filepath}")
    chroma = librosa.feature.chroma_stft(y=y, sr=fs, hop_length=hop_length)

    return [chroma, fs, duration, total_samples]


def get_chroma_timings(audio_filepath, ticks_per_second=None):

    chroma, fs, duration, total_samples = get_chroma_features(audio_filepath)

    chroma_time_bins = len(chroma[0])
    logging.info(f"Number of chroma time bins: {chroma_time_bins}")

    chroma_time_quantum = duration / chroma_time_bins
    samples_per_chroma_quantum = total_samples / chroma_time_bins
    logging.info(f"Duration of a chroma time bin: {chroma_time_quantum:.4f}s")
    logging.info(
        f"Samples per chroma time bin: {samples_per_chroma_quantum:.2f}"
    )

    note_on = [False] * 12
    note_events = []
    current_tick = 0

    chroma_values_file = open("chroma_values.txt", "w")

    chroma_values_file.write(
        "Time   C     C#    D     D#    E     F     F#    G     G#    A     A#    B\n"
    )
    for x in range(chroma_time_bins):
        bin_time = x * chroma_time_quantum

        if ticks_per_second is not None:
            current_tick = bin_time * ticks_per_second

        line = f"{bin_time:6.2f} "
        for c in range(12):
            bin_value = chroma[c][x]
            line += f"{bin_value:.2f}"
            if note_on[c] is False and bin_value > 0.7:
                note_on[c] = True
                note_events.append([c, current_tick, bin_time])
                line += "* "
            elif note_on[c] is True and bin_value < 0.5:
                note_on[c] = False
                line += "  "
            else:
                line += "  "

        chroma_values_file.write(line + "\n")

        if ticks_per_second is None:
            current_tick += 1

    # Sort note events by tick, then by note number, low to high
    note_events.sort(key=operator.itemgetter(1, 0))

    chroma_values_file.close()

    return note_events


def compute_acceleration_by_matches(
    matched_events_by_unaccel_ticks, per_foot=True
):

    # Calculate overall and recent velocities at roughly each foot of the
    # unaccelerated roll

    last_unaccel_time = 0.0
    last_unaccel_tick = 0
    last_accel_time = 0.0

    accel_v = []
    accel_t = []

    last_unaccel_tick = 0  # In unaccelerated ticks

    sample_interval = 1
    if per_foot == True:
        sample_interval = 3600  # In unaccelerated ticks

    last_foot = 0

    for unaccel_tick in sorted(matched_events_by_unaccel_ticks):
        if (unaccel_tick - last_unaccel_tick) < sample_interval:
            continue

        actual_feet_overall = float(unaccel_tick) / 3600.0
        actual_feet_delta = (
            float(unaccel_tick) - float(last_unaccel_tick)
        ) / 3600.0
        matched_event = matched_events_by_unaccel_ticks[unaccel_tick]

        unaccel_time = matched_event[0][0]
        accel_time = matched_event[0][1]

        if accel_time > last_accel_time and unaccel_time > last_unaccel_time:

            last_unaccel_fpm = (
                actual_feet_delta / (unaccel_time - last_unaccel_time) * 60
            )
            last_accel_fpm = (
                actual_feet_delta / (accel_time - last_accel_time) * 60
            )
            overall_unaccel_fpm = actual_feet_overall / unaccel_time * 60
            overall_accel_fpm = actual_feet_overall / accel_time * 60

            if int(last_foot) < int(actual_feet_overall):
                logging.info(
                    f"{actual_feet_overall:.4f}ft ({unaccel_tick} unaccel ticks), unaccel time is {unaccel_time:.4f}s, accel time is {accel_time:.4f}s"
                )
                logging.info(
                    f"Actual ft delta: {actual_feet_delta:.4f}ft, unaccel delta v: {last_unaccel_fpm:.4f}ft/m, overall: {overall_unaccel_fpm:.4f}ft/m, accel delta v: {last_accel_fpm:.4f}ft/m, overall: {overall_accel_fpm:.4f}ft/m"
                )

            # XXX Hack to remove problematic samples
            if accel_time < 13:
                continue
            accel_t.append(accel_time / 60.0)
            accel_v.append(last_accel_fpm)

        last_unaccel_time = unaccel_time
        last_unaccel_tick = unaccel_tick
        last_accel_time = accel_time
        last_foot = int(actual_feet_overall)

    # Derive average acceleration over the roll and plot it
    visualize_observed_velocities(accel_t, accel_v)


def visualize_observed_velocities(accel_t, accel_v):
    median_v = statistics.median(accel_v)
    mean_v = statistics.mean(accel_v)
    stdev_v = statistics.stdev(accel_v)
    logging.info(
        f"Median velocity: {median_v:.4f}, mean: {mean_v:.4f}, stdev: {stdev_v:.4f}"
    )

    acceleration = (accel_v[-1] - accel_v[1]) / ((accel_t[-1] - accel_t[1]))
    logging.info(f"Average acceleration since ft 1: {acceleration:.4f}ft/m^2")

    import numpy as np
    import matplotlib.pyplot as plt
    from scipy.stats import linregress

    regression = linregress(accel_t, accel_v)
    logging.info(f"Results of linear regression on velocity samples:")
    logging.info(f"Acceleration: {regression.slope:.4f} ft/min^2")
    logging.info(f"Initial velocity: {regression.intercept:.4f} ft/min")

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


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # accel_file_tpb, accel_file_tempo = get_midi_speed(accel)
    # unaccel_events = get_note_timings(unaccel, accel_file_tpb, accel_file_tempo)

    if Path(unaccel).suffix == ".mp3" and Path(accel).suffix == ".mp3":
        logging.info(f"Getting chroma features for {unaccel} and {accel}")
        if Path(roll_id + "_dtw.p").exists():
            (
                D,
                wp,
                unaccel_duration,
                accel_duration,
                unaccel_total_samples,
                accel_total_samples,
            ) = pickle.load(open(Path(roll_id + "_dtw.p"), "rb"))
        else:
            (
                unaccel_chroma,
                unaccel_fs,
                unaccel_duration,
                unaccel_total_samples,
            ) = get_chroma_features(unaccel)
            (
                accel_chroma,
                accel_fs,
                accel_duration,
                accel_total_samples,
            ) = get_chroma_features(accel)
            logging.info("Running dynamic time-warp matching")
            D, wp = librosa.sequence.dtw(
                X=unaccel_chroma, Y=accel_chroma, metric="euclidean"
            )
            pickle.dump(
                [
                    D,
                    wp,
                    unaccel_duration,
                    accel_duration,
                    unaccel_total_samples,
                    accel_total_samples,
                ],
                open(Path(roll_id + "_dtw.p"), "wb"),
            )
        # wp_s = np.asarray(wp) * hop_length / fs
        logging.info(f"Shape of warping path: {wp.shape}")

        unaccel_time_bins = unaccel_total_samples / hop_length
        unaccel_bin_duration = unaccel_duration / unaccel_time_bins

        accel_time_bins = accel_total_samples / hop_length
        accel_bin_duration = accel_duration / accel_time_bins

        matched_events_by_unaccel_ticks = {}

        last_unaccel_stride = 0
        last_accel_stride = 0

        wp_file = open(roll_id + "_warping.txt", "w")

        for x in range(wp.shape[0] - 1, 0, -1):
            unaccel_stride, accel_stride = wp[x]

            unaccel_time = unaccel_stride * unaccel_bin_duration
            accel_time = accel_stride * accel_bin_duration

            unaccel_tick = int(unaccel_time * unaccel_tps)

            wp_file.write(
                "\t".join(
                    [
                        str(unaccel_stride),
                        str(accel_stride),
                        str(unaccel_time),
                        str(accel_time),
                        str(unaccel_tick),
                    ]
                )
            )

            # XXX Is this the right thing to do?
            if (
                unaccel_stride != last_unaccel_stride
                and accel_stride != last_accel_stride
            ):

                if unaccel_tick not in matched_events_by_unaccel_ticks:
                    matched_events_by_unaccel_ticks[unaccel_tick] = [
                        [unaccel_time, accel_time]
                    ]
                else:
                    matched_events_by_unaccel_ticks[unaccel_tick].append(
                        [unaccel_time, accel_time]
                    )

                wp_file.write("*")

            wp_file.write("\n")

            last_unaccel_stride = unaccel_stride
            last_accel_stride = accel_stride

        compute_acceleration_by_matches(
            matched_events_by_unaccel_ticks, per_foot=True
        )

        return

    elif Path(unaccel).suffix == ".mid" and Path(accel).suffix == ".mp3":
        unaccel_events = get_midi_timings(unaccel, use_chroma_numbers=True)
        accel_events = get_chroma_timings(accel)
    elif Path(unaccel).suffix == ".mid" and Path(accel).suffix == ".mid":
        unaccel_events = get_midi_timings(unaccel)
        accel_events = get_midi_timings(accel)
    else:
        logging.error("Unable to process this combination of input file types")
        return

    logging.info(f"Number of unaccelerated note events: {len(unaccel_events)}")
    logging.info(f"Number of accelerated note events: {len(accel_events)}")

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

    alignment_fn = roll_id + "_alignment.p"

    # The pickled alignment data is just the two sequences
    if Path(f"{alignment_fn}").exists():
        logging.info("Loading pairwise alignment")
        unaccel_seq, accel_seq = pickle.load(open(alignment_fn, "rb"))
    else:
        logging.info("Computing pairwise alignment")
        alignments = pairwise2.align.globalxx(
            unaccel_chars,
            accel_chars,
            gap_char=[gap_char],
            one_alignment_only=True,
        )
        alignment = alignments[0]
        unaccel_seq = alignment.seqA
        accel_seq = alignment.seqB
        pickle.dump((unaccel_seq, accel_seq), open(alignment_fn, "wb"))

    unaccel_counter = 0
    accel_counter = 0

    logging.info(
        f"total unmatched notes in unaccelerated file: {unaccel_seq.count('-')}"
    )
    logging.info(
        f"total unmatched notes in accelerated file: {accel_seq.count('-')}"
    )

    # Accumulate data about matched MIDI messages between the sequences
    logging.info("ACCEL MATCH_INFO UNACCEL MATCH_INFO")

    matched_events_by_unaccel_ticks = {}

    for i, unaccel_item in enumerate(unaccel_seq):

        accel_item = accel_seq[i]

        if accel_item != "-" and unaccel_item != "-":
            unaccel_midi_number = ord(unaccel_item.replace("~", "-"))
            accel_midi_number = ord(accel_item.replace("~", "-"))
            unaccel_event = unaccel_events[unaccel_counter]
            accel_event = accel_events[accel_counter]

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

            unaccel_time = unaccel_event[2]
            accel_time = accel_event[2]

            unaccel_tick = unaccel_event[1]

            if unaccel_tick not in matched_events_by_unaccel_ticks:
                matched_events_by_unaccel_ticks[unaccel_tick] = [
                    [unaccel_time, accel_time]
                ]
            else:
                matched_events_by_unaccel_ticks[unaccel_tick].append(
                    [unaccel_time, accel_time]
                )

        if str(unaccel_item) != "-":
            unaccel_counter += 1

        if str(accel_item) != "-":
            accel_counter += 1

    if Path(accel).suffix == ".mp3":
        compute_acceleration_by_matches(
            matched_events_by_unaccel_ticks, per_foot=False
        )
    else:
        compute_acceleration_by_matches(
            matched_events_by_unaccel_ticks, per_foot=True
        )


if __name__ == "__main__":
    main()
