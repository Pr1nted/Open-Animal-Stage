#!/usr/bin/env python3
"""Export the MICrONS digital twin (Wang et al., Nature 2025) for the browser.

    data/raw/micro_venv/bin/python tools/export_microns_twin.py            # scan 6-4
    data/raw/micro_venv/bin/python tools/export_microns_twin.py --scan 8-5

WHAT THIS PRODUCES, under web/species/mouse_v1/

    model.onnx   ONE 1/30 s STEP of the twin for one imaging scan, with every
                 piece of recurrent state as an explicit input and output, so
                 the page can run a clip of any length by feeding the state
                 back. Inputs and outputs are listed in mouse.json.
    mouse.json   the units (neurons) the model predicts, in readout order:
                 their functional ids, cortical area, 2P soma position, and --
                 for the subset that were matched to the electron-microscopy
                 reconstruction -- the EM nucleus id, EM soma position and
                 cortical layer. Plus the input spec and provenance.

WHAT THE MODEL IS

The twin is a recurrent network trained on two-photon recordings of mouse
17797, the same animal whose cortex was reconstructed by electron microscopy
for MICrONS. A shared "foundation" core is frozen; each of the 13 imaging
scans has its own readout (one output per recorded unit), its own eye-to-
monitor geometry (perspective) and its own behaviour MLP (modulation). A scan
is therefore a separate model, and this exports one scan at a time.

WHY ONE STEP, NOT A CLIP

The network is stateful (temporal convolutions keep the last two frames of
their input; two LSTMs keep h and c). The fnn package holds that state in
Python dicts on the modules. Here it is lifted into graph inputs/outputs so
the page owns it. All temporal convolutions zero-pad in time and every LSTM
starts from zeros, so the initial state is all zeros -- this is checked
against the reference implementation below, not assumed.

WHERE THE DATA COMES FROM (all public, no login)

    s3://bossdb-open-data/iarpa_microns/minnie/functional_data/foundation_model/
        foundational_model_weights_and_metadata_v1.zip   (md5 checked by fnn)
    .../functional_data/digital_twin_properties/v2/{anatomy,performance,readout}/
    .../functional_data/functional_connectomics/node_and_edge_properties/v1/
        node_data_v1.pkl   Ding et al. 2025: functional unit <-> EM nucleus

Fetch them with the commands in docs/mouse.md into data/raw/microns/.
"""

import argparse
import hashlib
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from fnn import microns

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "microns"
OUT = ROOT / "web" / "species" / "mouse_v1"

H, W = 144, 256  # stimulus frame, pixels, fixed by the released model
FPS = 30


def discover_state(model):
    """Run two eager steps and return the stateful slots the fnn modules fill.

    Returns a list of (module_name, module, kind, shapes) where kind is
    "history" (a temporal conv's input history) or "lstm" (h and c).
    """
    model.eval()
    model.reset()
    s, p, m, _ = model.to_tensor(np.full([H, W], 128, np.uint8))
    with torch.no_grad():
        model(s, p, m)
        model(s, p, m)
    slots = []
    for name, mod in model.named_modules():
        past = getattr(mod, "past", None)
        if not isinstance(past, dict) or not past:
            continue
        if "h" in past and "c" in past:
            slots.append((name, mod, "lstm", [tuple(past["h"].shape), tuple(past["c"].shape)]))
        elif past.get("history") is not None:
            if getattr(mod, "pad", None) != "zeros":
                raise SystemExit(f"{name}: temporal conv pads with {mod.pad!r}; zero initial state would be wrong")
            hist = past["history"]
            slots.append((name, mod, "history", [tuple(hist[0].shape)] * (hist.maxlen - 1)))
    model.reset()
    return slots


class Step(torch.nn.Module):
    """One frame of the twin with the recurrent state passed explicitly."""

    def __init__(self, model, slots):
        super().__init__()
        self.model = model
        self.slots = slots

    def forward(self, stimulus, perspective, modulation, *state):
        self.model.reset()
        it = iter(state)
        for _, mod, kind, shapes in self.slots:
            if kind == "lstm":
                h, c = next(it), next(it)
                mod.past["h"], mod.past["c"] = h, c
            else:
                prev = [next(it) for _ in shapes]
                # A full deque: the leading placeholder is dropped by the append
                # inside Conv.forward, leaving [prev..., x].
                mod.past["stream"] = None
                mod.past["weight"] = mod.weight(None)
                mod.past["history"] = deque([prev[0], *prev], maxlen=len(prev) + 1)
        response = self.model(stimulus, perspective, modulation)
        out = [response]
        for _, mod, kind, _ in self.slots:
            if kind == "lstm":
                out += [mod.past["h"], mod.past["c"]]
            else:
                out += list(mod.past["history"])[1:]
        self.model.reset()
        return tuple(out)


_conv3d = torch.nn.functional.conv3d


def _conv3d_as_conv2d(input, weight, bias=None, stride=1, padding=0, dilation=1, groups=1):
    """fnn's Conv always calls conv3d with the whole time window as the kernel
    depth (output depth 1) and does its own spatial padding. That is exactly a
    grouped conv2d over channels (c, t) flattened c-major, which every
    onnxruntime-web backend supports; grouped Conv3D is refused by WebGPU."""
    N, C, T, H, W = input.shape
    O, Cg, Tk, kh, kw = weight.shape
    if Tk != T or padding not in (0, (0, 0, 0)) or dilation not in (1, (1, 1, 1)):
        return _conv3d(input, weight, bias, stride, padding, dilation, groups)
    s = stride if isinstance(stride, int) else tuple(stride)[1:]
    y = torch.nn.functional.conv2d(input.reshape(N, C * T, H, W), weight.reshape(O, Cg * Tk, kh, kw),
                                   bias, s, 0, 1, groups)
    return y.unsqueeze(2)


def state_names(slots):
    names = []
    for name, _, kind, shapes in slots:
        key = name.replace(".", "_")
        if kind == "lstm":
            names += [f"{key}__h", f"{key}__c"]
        else:
            names += [f"{key}__t{i}" for i in range(len(shapes))]
    return names


def test_image(seed=0):
    """A fixed, map-like test frame: smooth blobs with hard borders."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.zeros([H, W])
    for _ in range(12):
        cx, cy, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(10, 50)
        img[(xx - cx) ** 2 + (yy - cy) ** 2 < r * r] = rng.uniform(0, 1)
    return (img * 255).astype(np.uint8)


def unit_table(session, scan_idx, ids):
    """Per-unit metadata in readout order."""
    ids = ids.reset_index().sort_values("readout_id")
    assert (ids.readout_id.values == np.arange(len(ids))).all()
    key = ["session", "scan_idx", "unit_id"]

    anat = pd.read_csv(RAW / "properties/anatomy/units.csv")
    perf = pd.read_csv(RAW / "properties/performance/units.csv")
    ro_units = pd.read_csv(RAW / "properties/readout/units.csv")
    ro_loc = np.load(RAW / "properties/readout/readout_locations.npy")
    ro_units["rf_x"], ro_units["rf_y"] = ro_loc[:, 0], ro_loc[:, 1]

    t = ids[key + ["readout_id"]]
    t = t.merge(anat, on=key, how="left").merge(perf, on=key, how="left").merge(ro_units, on=key, how="left")

    node = pd.read_pickle(RAW / "coreg/node_data_v1.pkl")
    node = node[(node.scan_session == session) & (node.scan_idx == scan_idx)]
    node = node.assign(unit_id=node.unit_id.astype(int))[
        ["unit_id", "nucleus_id", "nucleus_x", "nucleus_y", "nucleus_z", "layer", "brain_area", "proofread_status"]
    ].rename(columns={"brain_area": "em_area"})
    missing = set(node.unit_id) - set(t.unit_id)
    assert not missing, f"{len(missing)} coregistered units are not in the model's readout"
    t = t.merge(node, on="unit_id", how="left").sort_values("readout_id")
    assert len(t) == len(ids)
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scan", default="6-4", help="session-scan_idx (default 6-4: the most EM-matched units)")
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--frames", type=int, default=30, help="frames to check ONNX against fnn")
    args = ap.parse_args()
    session, scan_idx = map(int, args.scan.split("-"))

    torch.manual_seed(0)
    model, ids = microns.scan(session, scan_idx, cuda=False, directory=str(RAW))
    model.eval()
    n_units = len(ids)
    slots = discover_state(model)
    names = state_names(slots)
    shapes = [s for *_, sh in slots for s in sh]
    print(f"scan {session}-{scan_idx}: {n_units} units, {sum(p.numel() for p in model.parameters()):,} params, "
          f"{len(names)} state tensors ({sum(int(np.prod(s)) for s in shapes) * 4 / 2**20:.1f} MiB)")

    step = Step(model, slots).eval()
    zeros = [torch.zeros(s) for s in shapes]
    stim0 = torch.zeros(1, 1, H, W)
    persp0 = torch.zeros(1, 2)
    mod0 = torch.zeros(1, 2)

    OUT.mkdir(parents=True, exist_ok=True)
    onnx_path = OUT / "model.onnx"
    torch.nn.functional.conv3d = _conv3d_as_conv2d  # export only; the check below uses fnn unpatched
    try:
        with torch.no_grad():
            torch.onnx.export(
                step,
                (stim0, persp0, mod0, *zeros),
                str(onnx_path),
                input_names=["stimulus", "perspective", "modulation", *[f"in__{n}" for n in names]],
                output_names=["response", *[f"out__{n}" for n in names]],
                opset_version=args.opset,
                dynamo=False,
                do_constant_folding=True,
            )
    finally:
        torch.nn.functional.conv3d = _conv3d
    size = onnx_path.stat().st_size
    print(f"wrote {onnx_path.relative_to(ROOT)} ({size / 2**20:.1f} MiB)")

    # --- check: ONNX stepped with its own state == fnn's own predict() ------
    import onnxruntime as ort

    img = test_image()
    frames = np.repeat(img[None], args.frames, axis=0)
    with torch.no_grad():
        ref = model.predict(stimuli=frames)  # [T, U], zero perspective/modulation
    model.reset()

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1  # closest to a single-threaded WASM page
    sess = ort.InferenceSession(str(onnx_path), so, providers=["CPUExecutionProvider"])
    state = [z.numpy() for z in zeros]
    x = (img.astype(np.float32) / 255)[None, None]
    got, times = [], []
    for _ in range(args.frames):
        t0 = time.perf_counter()
        outs = sess.run(None, {"stimulus": x, "perspective": np.zeros([1, 2], np.float32),
                               "modulation": np.zeros([1, 2], np.float32),
                               **{f"in__{n}": s for n, s in zip(names, state)}})
        times.append(time.perf_counter() - t0)
        got.append(outs[0][0])
        state = outs[1:]
    got = np.array(got)
    err = np.abs(got - ref).max()
    rel = err / np.abs(ref).max()
    print(f"ONNX vs fnn over {args.frames} frames: max abs err {err:.2e} (relative {rel:.2e})")
    if rel > 1e-3:
        raise SystemExit("ONNX export does not reproduce fnn; not writing mouse.json")
    ms = 1000 * np.median(times)
    print(f"onnxruntime CPU, 1 thread: {ms:.0f} ms/frame median -> {ms * FPS / 1000:.1f} s per 1 s clip")

    # --- mouse.json -----------------------------------------------------------
    t = unit_table(session, scan_idx, ids)
    em = t.nucleus_id.notna()

    def col(series, kind=float, nd=None):
        out = []
        for v in series:
            if pd.isna(v):
                out.append(None)
            elif kind is float:
                out.append(round(float(v), nd) if nd is not None else float(v))
            else:
                out.append(kind(v))
        return out

    doc = {
        "species": "mouse_v1",
        "role": "station",
        "dataset": "MICrONS digital twin (Wang et al., Nature 640:470, 2025), mouse 17797",
        "scan": {"session": session, "scan_idx": scan_idx},
        "n": n_units,
        "n_em_matched": int(em.sum()),
        "input": {
            "stimulus": {"shape": [1, 1, H, W], "dtype": "float32", "range": [0, 1],
                         "meaning": "one grayscale frame, pixel/255, shown on the monitor at 30 Hz. "
                                    "The released twin was trained on 144x256 frames; render the map to "
                                    "exactly that and convert to luminance."},
            "perspective": {"shape": [1, 2], "dtype": "float32",
                            "meaning": "[pupil_x, pupil_y], each z-scored over the scan's training set. "
                                       "0,0 = the mouse's average eye position (fnn's own default)."},
            "modulation": {"shape": [1, 2], "dtype": "float32",
                           "meaning": "[pupil_radius, treadmill_velocity], z-scored over the scan's training set. "
                                      "0,0 = average pupil and average running (fnn's own default). "
                                      "The station feeds 0,0: there is no mouse, so no behaviour to report."},
            "frame_rate_hz": FPS,
            "burnin_frames": 10,
        },
        "output": {"response": {"shape": [1, n_units],
                                "meaning": "predicted activity of each unit for this frame: exp of the readout (fnn's "
                                           "Poisson unit), in the units of the training targets -- recorded "
                                           "activity scaled by the unit's training-set mean (fnn demo 4). "
                                           "So ~1 is roughly that neuron's typical level; this reading is inferred "
                                           "from the training spec, not stated for the released weights. The first "
                                           "`burnin_frames` are the model settling, not a response."}},
        "state": [{"input": f"in__{n}", "output": f"out__{n}", "shape": list(s), "init": 0}
                  for n, s in zip(names, shapes)],
        "units": {
            "readout_id": t.readout_id.astype(int).tolist(),
            "unit_id": t.unit_id.astype(int).tolist(),
            "area": col(t.brain_area, str),
            "field": col(t.field, int),
            "soma_2p_um": [[round(float(a), 2), round(float(b), 2), round(float(c), 2)]
                           for a, b, c in zip(t.unit_x, t.unit_y, t.unit_z)],
            "rf_xy": [[round(float(a), 4), round(float(b), 4)] for a, b in zip(t.rf_x, t.rf_y)],
            "cc_norm": col(t.cc_norm, float, 4),
            "nucleus_id": col(t.nucleus_id, int),
            "layer": col(t.layer, str),
            "soma_em_nm": [None if pd.isna(a) else [int(a), int(b), int(c)]
                           for a, b, c in zip(t.nucleus_x, t.nucleus_y, t.nucleus_z)],
            "proofread_status": col(t.proofread_status, str),
        },
        "units_doc": {
            "soma_2p_um": "unit_x (posterior->anterior), unit_y (lateral->medial), unit_z (superficial->deep), "
                          "microns, two-photon stack space (digital_twin_properties/v2/anatomy)",
            "rf_xy": "readout location, approx. receptive-field centre in stimulus space, (-1,-1) top-left, "
                     "(1,1) bottom-right (digital_twin_properties/v2/readout)",
            "cc_norm": "how well the twin predicts this unit on held-out data, normalised by the neuron's own "
                       "trial-to-trial repeatability (digital_twin_properties/v2/performance)",
            "nucleus_id": "EM nucleus id in the MICrONS minnie65 volume, for units coregistered to the "
                          "reconstruction (Ding et al. 2025 node_data_v1). A nucleus id is stable; a segment "
                          "root id is not, and is deliberately not stored here.",
            "soma_em_nm": "EM nucleus centre, nanometres, minnie65 space (node_data_v1)",
            "layer": "cortical layer, EM-matched units only (node_data_v1); null means not matched, not 'no layer'",
        },
        "provenance": {
            "weights": "s3://bossdb-open-data/iarpa_microns/minnie/functional_data/foundation_model/"
                       "foundational_model_weights_and_metadata_v1.zip (md5 58fcac4b31ad2902c81e339432cec787): "
                       f"params_core.pt + params_{session}_{scan_idx}.pt",
            "code": "https://github.com/cajal/fnn (MIT), fnn.microns.scan; exported by tools/export_microns_twin.py",
            "anatomy": "s3://bossdb-open-data/iarpa_microns/minnie/functional_data/digital_twin_properties/v2/",
            "coregistration": "s3://bossdb-open-data/iarpa_microns/minnie/functional_data/functional_connectomics/"
                              "node_and_edge_properties/v1/node_data_v1.pkl",
            "onnx_sha256": hashlib.sha256(onnx_path.read_bytes()).hexdigest(),
            "onnx_check": {"frames": args.frames, "max_abs_err": float(err), "max_rel_err": float(rel)},
            "ort_cpu_1thread_ms_per_frame": round(float(ms), 1),
            "licence": "fnn code: MIT. Weights and MICrONS data: see docs/mouse.md",
            "cite": ["Wang et al. 2025, doi:10.1038/s41586-025-08829-y",
                     "Ding, Fahey, Papadopoulos et al. 2025, doi:10.1038/s41586-025-08840-3",
                     "MICrONS Consortium 2025, doi:10.1038/s41586-025-08790-w"],
        },
    }
    (OUT / "mouse.json").write_text(json.dumps(doc, separators=(",", ":")))
    print(f"wrote {(OUT / 'mouse.json').relative_to(ROOT)}: {n_units} units, {int(em.sum())} EM-matched")


if __name__ == "__main__":
    main()
