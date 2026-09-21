"""The trailer's music: an original ambient/electronic piece, synthesised here
from sine waves and noise with numpy alone. No samples, no loops, nothing
downloaded: every sound is computed in this file, so the track is original
and free to use.

    .venv/bin/python tools/trailer/music.py [out/trailer/timeline.json] [out/trailer/music.wav]

It is written to the trailer's bars (shots.mjs: 90 BPM, 4/4). D minor,
i-VI-III-VII (Dm Bb F C) that resolves to F on the end card:
  bars  0-4   pads open out of silence; sparse "spikes" (soft bell plucks at
              random, like neurons firing) in a long reverb
  bars  4-16  a sub bass and a quiet eighth-note pulse join
  bars 16-24  a soft heartbeat kick, a sixteenth arpeggio, more spikes
  bars 24-26  the build: the filter opens, a noise swell, the kick on every beat
  end card    one low bloom and the F chord, left to ring out
Deterministic: a fixed seed, so the same timeline gives the same file.
"""
import json
import os
import sys
import wave

import numpy as np

SR = 48000
rng = np.random.default_rng(1914)

tl_path = sys.argv[1] if len(sys.argv) > 1 else "out/trailer/timeline.json"
out_path = sys.argv[2] if len(sys.argv) > 2 else "out/trailer/music.wav"
if os.path.exists(tl_path):
    TL = json.load(open(tl_path))
    BPM, SHOT_END, TOTAL = TL["bpm"], TL["endCard"]["start"], TL["total"]
else:
    BPM, SHOT_END, TOTAL = 90, 26 * 16 / 6, 26 * 16 / 6 + 6
BEAT = 60 / BPM
BAR = 4 * BEAT
END_BAR = SHOT_END / BAR                   # the bar the end card starts on (26)
LEN = TOTAL + 2.5                          # room for the tail
N = int(LEN * SR)
t_all = np.arange(N) / SR


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def at(sec):
    return int(round(sec * SR))


def env_adsr(n, a, r, sustain_len):
    """Attack a s, hold, release r s, as raised-cosine ramps (no clicks)."""
    e = np.ones(n)
    na, nr = min(n, at(a)), min(n, at(r))
    e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / max(1, na))
    s = at(sustain_len)
    if s < n:
        k = np.arange(n - s)
        e[s:] *= np.where(k < nr, 0.5 + 0.5 * np.cos(np.pi * k / max(1, nr)), 0.0)
    return e


def add(buf, start, sig, pan=0.0, gain=1.0):
    """Mix a mono signal into the stereo buffer, equal-power panned."""
    i = at(start)
    if i >= N:
        return
    sig = sig[: N - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i:i + len(sig)] += sig * l * gain
    buf[1, i:i + len(sig)] += sig * r * gain


def one_pole_lp(x, cutoff):
    """One-pole low-pass; cutoff in Hz, scalar or per-sample array."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


# --------------------------------------------------------------- harmony
DM = [50, 57, 60, 64, 65]          # Dm9:  D A C E F
BB = [46, 53, 57, 62, 65]          # Bbmaj7(add?): Bb F A D F
FM = [41, 53, 57, 60, 64]          # Fmaj7: F F A C E
CM = [48, 55, 62, 64, 67]          # C(add9): C G D E G
FIN = [41, 48, 57, 60, 64, 67, 72]  # Fmaj9 on the end card

# (start bar, length in bars, chord)
chords = []
b = 0
while b < 16:
    for ch in (DM, BB, FM, CM):
        if b < 16:
            chords.append((b, 2, ch)); b += 2
while b < 24:
    for ch in (DM, BB, FM, CM):
        if b < 24:
            chords.append((b, 1, ch)); b += 1
chords += [(24, 1, BB), (25, 1, CM)]
while b < END_BAR - 2:                 # a longer cut: keep cycling
    chords.append((b, 1, (DM, BB, FM, CM)[int(b) % 4])); b += 1


def brightness(bar):
    """How many harmonics the pads let through: opens up towards the end card."""
    if bar < 4:
        return 1.6
    if bar < 16:
        return 2.2
    if bar < 24:
        return 2.8
    return 2.8 + (bar - 24) / 2 * 2.5


# --------------------------------------------------------------- voices
def pad_note(f, dur, bright_from, bright_to, rel=2.2):
    """A warm pad: three slightly detuned voices of a softened saw, whose
    upper harmonics are faded by `brightness`, with slow vibrato."""
    n = at(dur + rel)
    t = np.arange(n) / SR
    bright = np.linspace(bright_from, bright_to, n)
    out = np.zeros(n)
    for cents in (-6, 0, 6.5):
        fd = f * 2 ** (cents / 1200)
        vib = 1 + 0.0018 * np.sin(2 * np.pi * (0.21 + 0.05 * rng.random()) * t + rng.random() * 6.28)
        phase = 2 * np.pi * fd * np.cumsum(vib) / SR + rng.random() * 6.28
        for k in range(1, 9):
            if fd * k > 9000:
                break
            out += np.sin(k * phase) * (1 / k) * np.exp(-(k - 1) / bright)
    return out * env_adsr(n, min(1.4, dur * 0.45), rel, dur) / 3


def bell(f, decay=0.6, bright=1.0):
    """A soft FM bell/marimba: the 'spike'. Quick attack, exponential tail."""
    n = at(decay * 5)
    t = np.arange(n) / SR
    idx = 1.6 * bright * np.exp(-t / (decay * 0.25))
    s = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 2.0 * t))
    s += 0.25 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t / (decay * 0.3))
    e = np.exp(-t / decay) * (1 - np.exp(-t / 0.003))
    return s * e


def kick(soft=1.0):
    n = at(0.7)
    t = np.arange(n) / SR
    f = 44 + 62 * np.exp(-t / 0.045)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.32) * (1 - np.exp(-t / 0.002))
    return s * soft


def tick():
    n = at(0.05)
    x = rng.standard_normal(n)
    x = x - one_pole_lp(x, 5000)                  # keep the top: a soft hat
    return x * np.exp(-np.arange(n) / SR / 0.012)


PENTA = [62, 65, 67, 69, 72, 74, 77, 79, 81, 84]   # D minor pentatonic, D4-C6

dry = np.zeros((2, N))
padbus = np.zeros((2, N))

# Pads, one chord at a time, overlapping by their release.
for (b0, bl, ch) in chords:
    start, dur = b0 * BAR, bl * BAR
    for j, m in enumerate(ch):
        s = pad_note(midi(m), dur, brightness(b0), brightness(b0 + bl))
        add(padbus, start, s, pan=(j / (len(ch) - 1) - 0.5) * 0.7, gain=0.075 if m >= 50 else 0.06)
# Fade the pads in out of silence over the first two bars.
padbus[:, : at(2 * BAR)] *= (np.linspace(0, 1, at(2 * BAR)) ** 1.6)

# The end card: a bloom and the resolving chord, long release.
end = SHOT_END
for j, m in enumerate(FIN):
    s = pad_note(midi(m), TOTAL - end - 1.0, 3.5, 1.8, rel=3.0)
    add(padbus, end, s, pan=(j / (len(FIN) - 1) - 0.5) * 0.8, gain=0.075)
for j, m in enumerate([65, 69, 72, 77]):
    add(dry, end + j * 0.09, bell(midi(m), decay=1.8, bright=0.8), pan=(j - 1.5) * 0.3, gain=0.10)
add(dry, end, kick(1.0) * 0.9 + 0.0, gain=0.55)

# Sub bass under every chord, ducked by the kick later.
bass = np.zeros(N)
for (b0, bl, ch) in chords:
    r = {50: 38, 46: 34, 41: 29, 48: 36}[ch[0]]
    n = at(bl * BAR + 0.4)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * midi(r) * t) + 0.18 * np.sin(4 * np.pi * midi(r) * t)
    e = env_adsr(n, 0.25, 0.4, bl * BAR)
    i = at(b0 * BAR)
    if b0 >= 4:
        swell = min(1.0, 0.35 + (b0 - 4) / 4 * 0.65)     # comes in over two chords, not at once
        bass[i:i + n] += (s * e)[: N - i] * 0.11 * swell
n = at(TOTAL - end + 1)
t = np.arange(n) / SR
bass[at(end):at(end) + n] += (np.sin(2 * np.pi * midi(29) * t) * np.exp(-t / 2.5) * 0.2)[: N - at(end)]

# Kicks: none in the intro, a heartbeat on 1 and 3 from bar 16, every beat in the build.
kicks = []
for bar in range(16, int(END_BAR)):
    beats = (0, 2) if bar < 24 else (0, 1, 2, 3)
    for bt in beats:
        kicks.append(bar * BAR + bt * BEAT)
for k in kicks:
    add(dry, k, kick(0.8), gain=0.42)
# Sidechain: the pads and bass breathe with the kick.
duck = np.ones(N)
for k in kicks + [end]:
    i = at(k); n = at(0.45)
    d = 1 - 0.35 * np.exp(-np.arange(n) / SR / 0.12)
    duck[i:i + n] = np.minimum(duck[i:i + n], d[: N - i])
padbus *= duck
add(dry, 0, bass * duck, gain=1.0)

# The pulse: quiet eighth notes on chord tones from bar 4, sixteenths from bar 16.
for (b0, bl, ch) in chords:
    if b0 < 4:
        continue
    step = BEAT / 2 if b0 < 16 else BEAT / 4
    tones = sorted(set(m + 12 for m in ch[1:]))
    nsteps = int(round(bl * BAR / step))
    for s_ in range(nsteps):
        tt = b0 * BAR + s_ * step
        m = tones[(s_ * 2 + (s_ // 4)) % len(tones)]
        bright = 0.35 + (0.9 if b0 >= 24 else 0.3 if b0 >= 16 else 0.0) * ((tt / BAR - 16) / 10 if b0 >= 16 else 0)
        accent = 1.0 if s_ % 4 == 0 else 0.6
        g = (0.030 if b0 < 16 else 0.034) * accent
        add(dry, tt, bell(midi(m), decay=0.18 if b0 < 16 else 0.12, bright=bright), pan=0.35 * np.sin(s_ * 0.7), gain=g)

# Hats: very soft, off-beats, from bar 16.
for bar in range(16, int(END_BAR)):
    for bt in range(4):
        add(dry, bar * BAR + bt * BEAT + BEAT / 2, tick(), pan=0.25, gain=0.035 if bar < 24 else 0.05)

# Spikes: bells at random (Poisson) times, denser as the piece goes on, each on
# a pentatonic note, placed across the stereo field. Neurons, not a melody.
def rate(sec):
    bar = sec / BAR
    if bar < 4:
        return 0.9
    if bar < 16:
        return 1.6
    if bar < END_BAR:
        return 2.4 + max(0, bar - 22) * 0.9
    return 0.8 * np.exp(-(sec - SHOT_END) / 2)


tt = 0.6
while tt < TOTAL - 1:
    tt += rng.exponential(1 / rate(tt))
    m = PENTA[rng.integers(len(PENTA))] + (12 if rng.random() < 0.2 else 0)
    add(dry, tt, bell(midi(m), decay=0.35 + 0.5 * rng.random(), bright=0.6 + 0.6 * rng.random()),
        pan=rng.uniform(-0.85, 0.85), gain=0.03 + 0.03 * rng.random())

# The build: a noise swell whose filter opens over bars 24-26 and stops dead
# at the end card, where the reverb catches it.
b_start, b_end = 23.5 * BAR, SHOT_END
n = at(b_end - b_start)
u = np.linspace(0, 1, n)
noise = rng.standard_normal(n)
cut = 180 + 3800 * u ** 2.5                       # two poles: a soft whoosh, not a hiss
sw = one_pole_lp(one_pole_lp(noise, cut), cut) * (u ** 2.6) * 0.3
add(dry, b_start, sw, pan=-0.3, gain=1.0)
sw2 = one_pole_lp(one_pole_lp(rng.standard_normal(n), cut), cut) * (u ** 2.6) * 0.3
add(dry, b_start, sw2, pan=0.3, gain=1.0)

# --------------------------------------------------------------- space
# A synthetic hall: decorrelated noise per channel, decaying (RT60 ~3.6 s),
# darker as it decays, after a short pre-delay.
def impulse(seed):
    r = np.random.default_rng(seed)
    n = at(4.2)
    t = np.arange(n) / SR
    x = r.standard_normal(n) * np.exp(-6.9 * t / 3.6)
    x = one_pole_lp(x, 6500) * 0.6 + one_pole_lp(x, 1800) * 0.4
    x[: at(0.018)] = 0
    return x / np.sqrt(np.sum(x ** 2))


def convolve(x, h):
    L = len(x) + len(h) - 1
    nfft = 1 << (L - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[:L]
    return y[: len(x)]


send = padbus * 0.55 + dry * 0.45
wet = np.stack([convolve(send[0], impulse(11)), convolve(send[1], impulse(12))])
mix = padbus + dry + wet * 0.55
# The arc: level rises gently through the heartbeat section and the build.
bars_t = t_all / BAR
arc = np.interp(bars_t, [0, 16, 24, 26, END_BAR + 0.5, 100], [0.9, 0.95, 1.08, 1.22, 1.15, 1.15])
mix *= arc

# Gentle master: a touch of tanh glue, then peak to -1 dBFS, fade the tail.
mix = np.tanh(mix * 1.4) / 1.4
mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))
fade = at(2.0)
mix[:, -fade:] *= np.linspace(1, 0, fade) ** 2
mix[:, : at(0.05)] *= np.linspace(0, 1, at(0.05))

os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
pcm = (np.clip(mix.T, -1, 1) * 32767).astype("<i2")
with wave.open(out_path, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print(f"{out_path}: {LEN:.1f} s, {BPM} BPM, end card at {SHOT_END:.2f} s")
