
"""
Compact wfview waterfall recorder.

This single-file variant keeps the project easy to read: capture mono audio,
perform a sliding STFT, and dump the result to a CSV file. No packaging,
metadata sidecars, or background threads beyond the audio callback.
"""

from __future__ import annotations

import argparse
import csv
import queue
import sys
import time
from typing import List, Optional
from pathlib import Path

import numpy as np
import sounddevice as sd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wfview-waterfall-compact",
        description="Record wfview audio into a CSV STFT waterfall (compact version).",
    )
    parser.add_argument("--device", default=None, help="Audio device name or index.")
    parser.add_argument("--samplerate", type=int, default=48_000, help="Sample rate in Hz.")
    parser.add_argument("--nfft", type=int, default=2048, help="FFT size.")
    parser.add_argument("--hop", type=int, default=512, help="Hop size between frames.")
    parser.add_argument(
        "--window",
        default="hann",
        choices=["hann", "hanning", "hamming", "rect"],
        help="Window function applied before each FFT.",
    )
    parser.add_argument(
        "--blocksize",
        type=int,
        default=512,
        help="Audio block size passed to sounddevice (set 0 to let the driver decide).",
    )
    parser.add_argument("--outfile", default=None, help="Destination CSV path.")
    parser.add_argument(
        "--save-dir",
        default="csv",
        help="Directory used for auto-saved CSV files when running in live mode.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Recording duration in seconds (<= 0 means run until Ctrl+C).",
    )
    parser.add_argument(
        "--amplitude-floor",
        type=float,
        default=1e-8,
        help="Minimum magnitude before converting to dB to avoid log(0).",
    )
    parser.add_argument(
        "--live-plot",
        action="store_true",
        help="Display a real-time spectrogram (requires matplotlib).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Shortcut enabling --live-plot and auto-saving the capture to --save-dir when stopping.",
    )
    parser.add_argument(
        "--plot-frames",
        type=int,
        default=200,
        help="Number of recent frames kept in the live plot.",
    )
    parser.add_argument(
        "--center-freq",
        type=float,
        default=None,
        help="Fréquence centrale (en Hz) pour la visualisation live; si fournie, l'axe des fréquences sera recentré autour de cette valeur.",
    )
    parser.add_argument(
        "--span-hz",
        type=float,
        default=None,
        help="Largeur de bande à afficher (en Hz) autour de --center-freq pour la visualisation live. Par défaut: pleine bande (0..Fs/2).",
    )
    return parser.parse_args()


def build_window(name: str, size: int) -> np.ndarray:
    lowered = name.lower()
    if lowered in {"hann", "hanning"}:
        return np.hanning(size)
    if lowered == "hamming":
        return np.hamming(size)
    if lowered == "rect":
        return np.ones(size, dtype=np.float32)
    raise ValueError(f"Unsupported window: {name}")


def main() -> int:
    args = parse_args()

    if args.live:
        args.live_plot = True

    default_filename = "waterfall_compact.csv"
    if args.outfile:
        outfile_path = Path(args.outfile)
    else:
        if args.live_plot:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            outfile_path = Path(args.save_dir) / f"waterfall_{timestamp}.csv"
        else:
            outfile_path = Path(default_filename)
    if not outfile_path.parent.exists():
        outfile_path.parent.mkdir(parents=True, exist_ok=True)
    args.outfile = str(outfile_path)

    if args.hop <= 0 or args.hop > args.nfft:
        print("--hop must be between 1 and nfft", file=sys.stderr)
        return 2

    # These arrays hold the sliding window; keeping them outside the loop avoids reallocations.
    buffer = np.zeros(args.nfft, dtype=np.float32)
    window = build_window(args.window, args.nfft).astype(np.float32)
    hop = args.hop
    amplitude_floor = max(args.amplitude_floor, 1e-12)
    frame_duration = hop / float(args.samplerate)

    # Precompute FFT bin labels so the CSV header and visualisation stay in sync.
    use_shifted_fft = args.center_freq is not None
    if use_shifted_fft:
        base_freqs = np.fft.fftfreq(args.nfft, d=1.0 / args.samplerate)
        freq_bins = np.fft.fftshift(base_freqs) + float(args.center_freq)
    else:
        freq_bins = np.fft.rfftfreq(args.nfft, d=1.0 / args.samplerate)
    fmin_plot = float(freq_bins[0])
    fmax_plot = float(freq_bins[-1])
    headers = ["timestamp_epoch_s"] + [f"bin_{int(round(freq))}Hz" for freq in freq_bins]

    plot_frames: List[np.ndarray] = []
    plot_times: List[float] = []
    plot_image = None
    plot_axes = None
    plt = None  # type: ignore[assignment]
    center_line = None  # Matplotlib line artist for the center frequency marker

    if args.live_plot:
        try:
            import matplotlib.pyplot as plt  # type: ignore[no-redef]
        except ImportError as exc:  # pragma: no cover - optional feature
            print("matplotlib est requis pour --live-plot (pip install matplotlib).", file=sys.stderr)
            return 2
        plt.ion()
        fig, plot_axes = plt.subplots()
        plot_axes.set_title("wfview waterfall (live)")
        plot_axes.set_xlabel("Fréquence (Hz)")
        plot_axes.set_ylabel("Temps écoulé (s)")
        try:
            from matplotlib.ticker import ScalarFormatter  # type: ignore
        except Exception:  # pragma: no cover - dépend de matplotlib
            pass
        else:
            freq_formatter = ScalarFormatter(useOffset=False)
            freq_formatter.set_scientific(False)
            plot_axes.xaxis.set_major_formatter(freq_formatter)
        plot_axes.ticklabel_format(style="plain", axis="y")

    # Audio samples arrive via callback into this queue; the main loop stays simple.
    sample_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=16)

    def audio_callback(indata, frames, time_info, status):  # type: ignore[no-untyped-def]
        del frames, time_info  # Not used here, we only need the raw samples.
        if status:
            # Keep callback light: report once and drop the status flag.
            print(f"[audio] status={status}", file=sys.stderr)
        try:
            sample_queue.put_nowait(np.copy(indata[:, 0]).astype(np.float32))
        except queue.Full:
            pass  # Drop the block to avoid blocking the audio thread.

    blocksize = None if args.blocksize <= 0 else args.blocksize
    stream = sd.InputStream(
        samplerate=args.samplerate,
        blocksize=blocksize,
        device=args.device,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    )

    frames_emitted = 0
    filled = 0
    start_time = time.time()
    deadline: Optional[float] = None if args.duration <= 0 else start_time + args.duration

    with open(args.outfile, "w", newline="", encoding="utf-8") as handle, stream:
        writer = csv.writer(handle)
        writer.writerow(headers)

        # Affiche le périphérique réellement ouvert par PortAudio pour confirmer la configuration.
        try:
            device_indices = stream.device
            input_index = device_indices[0] if hasattr(device_indices, "__getitem__") else device_indices
            device_info = sd.query_devices(input_index)
            print(
                f"Input device: {device_info['name']} (index={input_index}, max_channels={device_info['max_input_channels']}, default_rate={device_info['default_samplerate']})"
            )
        except Exception as exc:  # pragma: no cover - diagnostic seulement
            print(f"Input device index: {stream.device} (info lookup failed: {exc})")

        try:
            while True:
                if deadline is not None and time.time() >= deadline and sample_queue.empty():
                    break
                try:
                    block = sample_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                idx = 0
                total = block.shape[0]
                while idx < total:
                    space = args.nfft - filled
                    take = min(space, total - idx)
                    buffer[filled : filled + take] = block[idx : idx + take]
                    filled += take
                    idx += take
                    if filled == args.nfft:
                        windowed = buffer * window
                        if use_shifted_fft:
                            spectrum = np.fft.fft(windowed, n=args.nfft)
                            spectrum = np.fft.fftshift(spectrum)
                        else:
                            spectrum = np.fft.rfft(windowed, n=args.nfft)
                        magnitude = np.maximum(np.abs(spectrum), amplitude_floor)
                        magnitudes_db = 20.0 * np.log10(magnitude)
                        frame_offset_s = (frames_emitted * hop) / args.samplerate
                        timestamp = start_time + frame_offset_s
                        row = [f"{timestamp:.6f}"] + [f"{value:.2f}" for value in magnitudes_db]
                        writer.writerow(row)
                        frames_emitted += 1
                        if hop < args.nfft:
                            buffer[: args.nfft - hop] = buffer[hop:]
                        filled = args.nfft - hop

                        if args.live_plot and plot_axes is not None:
                            # Empile les frames : les plus anciennes en haut, les nouvelles en bas
                            plot_frames.append(magnitudes_db)
                            plot_times.append(frame_offset_s)
                            if len(plot_frames) > max(args.plot_frames, 1):
                                plot_frames.pop(0)
                                plot_times.pop(0)

                            # Données image : (n_times, n_freqs) avec les frames empilées dans l'ordre chronologique
                            plot_data = np.vstack(plot_frames)

                            # Échelle de temps : timestamps absolus depuis le début de l'enregistrement.
                            time_start = plot_times[0]
                            time_end = plot_times[-1] + frame_duration

                            # Première création de l'image
                            if plot_image is None:
                                plot_image = plot_axes.imshow(
                                    plot_data,
                                    aspect="auto",
                                    origin="upper",  # 0 en haut, temps croît vers le bas
                                    extent=[fmin_plot, fmax_plot, time_end, time_start],  # inversion visuelle uniquement
                                    interpolation="nearest",
                                    vmin=-120,
                                    vmax=0,
                                )
                                plt.colorbar(plot_image, ax=plot_axes, label="dBFS")

                                # Crée la ligne verticale de fréquence centrale si demandée
                                if args.center_freq is not None and (fmin_plot <= args.center_freq <= fmax_plot):
                                    center_line = plot_axes.axvline(args.center_freq, linestyle="--", linewidth=1)
                            else:
                                plot_image.set_data(plot_data)
                                plot_image.set_extent([fmin_plot, fmax_plot, time_end, time_start])  # inversion visuelle uniquement

                                # Assure la présence/mise à jour de la ligne centrale
                                if args.center_freq is not None:
                                    if center_line is None and (fmin_plot <= args.center_freq <= fmax_plot):
                                        center_line = plot_axes.axvline(args.center_freq, linestyle="--", linewidth=1)
                                    elif center_line is not None:
                                        center_line.set_xdata([args.center_freq, args.center_freq])

                            # Gestion du centrage/zoom fréquentiel
                            if args.center_freq is not None:
                                cf = float(args.center_freq)
                                if args.span_hz is not None and args.span_hz > 0:
                                    half = float(args.span_hz) / 2.0
                                    left = cf - half
                                    right = cf + half
                                else:
                                    left = fmin_plot
                                    right = fmax_plot
                                left = max(fmin_plot, left)
                                right = min(fmax_plot, right)
                                if right - left <= 0:
                                    left, right = fmin_plot, fmax_plot
                                plot_axes.set_xlim(left, right)
                            else:
                                plot_axes.set_xlim(fmin_plot, fmax_plot)

                            # On conserve l'axe de temps inchangé (absolu, qui augmente), seule la texture est inversée
                            plot_axes.set_ylim(time_start, time_end)

                            plt.pause(0.01)
        except KeyboardInterrupt:
            print("\nInterrupted, stopping...", file=sys.stderr)

    print(f"Wrote {frames_emitted} frames to {args.outfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
