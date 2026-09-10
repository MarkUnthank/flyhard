#!/usr/bin/env python3
"""Minimal synchronized 16:9 roundabout video with supplied sponsor artwork."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw, ImageFont

from flyhard.cockpit import WheelRig
from flyhard.live_livery import verify_live_livery, verify_layer_livery
from flyhard.steering_hud import draw_steering_readout
from flyhard.video_branding import draw_site_brand
from train_roundabout import sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--sponsors", required=True)
    p.add_argument("--asset", required=True, help="Fresh live sponsor export")
    p.add_argument("--preview-only", action="store_true")
    args = p.parse_args()
    root, sponsor_root = Path(args.run), Path(args.sponsors)
    manifest = verify_live_livery(args.asset, root)
    verify_layer_livery(args.asset, sponsor_root)
    config = json.loads((root / "config.json").read_text())
    frames = json.loads((root / "frames.json").read_text())
    assert json.loads((root / "metrics.json").read_text())["status"] == "capture_complete"
    layers = np.asarray(Image.open(sponsor_root / "sponsor-layer.png").convert("RGBA"), dtype=np.float32) / 255
    layer_depth = np.load(sponsor_root / "sponsor-depth.npy")
    assert layers.shape == (960, 1248, 4)
    sponsor_metrics = json.loads((sponsor_root / "metrics.json").read_text())
    assert (sponsor_metrics["revision"], sponsor_metrics["layout"]) == (manifest["revision"], manifest["layoutVersion"])
    assert np.allclose(sponsor_metrics["camera_relative_matrix"], config["camera_relative_matrix"])
    assert sponsor_metrics["fov_degrees"] == config["fov_degrees"]
    cns_command = [sys.executable, "scripts/render_cns.py", "--run", str(root), "--geometry", "data/cns-geometry-v1/geometry.npz"]
    if args.preview_only:
        cns_command.append("--preview-only")
    cns_metrics_file = root / ("cns-preview-metrics.json" if args.preview_only else "cns-render-metrics.json")
    if not cns_metrics_file.exists():
        subprocess.run(cns_command, check=True)
    cns_metrics = json.loads(cns_metrics_file.read_text())
    assert cns_metrics["frames_sha256"] == sha(root / "frames.json")
    assert cns_metrics["neural_trace_sha256"] == sha(root / "neural-trace.npz")
    with np.load(root / "body-trace.npz") as archive:
        body = {k: archive[k] for k in archive.files}
    rig = WheelRig(indicator_stalk=True)
    replay = mj.MjData(rig.model)
    renderer = mj.Renderer(rig.model, height=440, width=600)
    gpu = GL.glGetString(GL.GL_RENDERER).decode()
    assert "NVIDIA" in gpu
    rig.model.geom_rgba[rig.model.geom_bodyid == 0, :3] = .025
    # Display-only contrast: distinguish the grey wheel from the amber stalk.
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body("wheel").id, :3] = [.30, .30, .30]
    rig.model.geom_rgba[rig.model.geom_bodyid == rig.model.body("indicator_stalk").id, :3] = [.95, .48, .08]
    camera = mj.MjvCamera(); camera.lookat[:] = [.2, 0, 1.1]
    camera.distance = 5.0; camera.azimuth = 125; camera.elevation = -24
    fonts = {s: ImageFont.truetype("assets/fonts/Geist.ttf", s) for s in [20, 24, 28, 32]}
    reader = imageio.get_reader(root / "carla-camera.mp4")
    cns_reader = None if args.preview_only else imageio.get_reader(root / "cns-layer.mp4")
    writer = None if args.preview_only else imageio.get_writer(root / "flyhard-16x9.mp4", fps=config["fps"],
        codec="libx264", macro_block_size=1, ffmpeg_params=["-crf", "17", "-preset", "slow", "-movflags", "+faststart",
        "-metadata", f"comment=Sponsor livery revision {manifest['revision']}, layout {manifest['layoutVersion']}. Vehicle: CARLA 0.9.16, CVC, Universitat Autonoma de Barcelona."])
    wanted = {0, min(100, len(frames) - 1), min(200, len(frames) - 1), min(400, len(frames) - 1), len(frames) - 1}
    occlusion, depth_deltas = [], []
    started = time.perf_counter()
    try:
        for i, raw in enumerate(reader):
            if args.preview_only and i not in wanted:
                continue
            record = frames[i]
            assert record["body_index"] == record["neural_index"] == body["decision_index"][i] == i
            assert abs(body["time"][i] - record["camera_time"]) < 1e-4
            encoded = np.asarray(Image.open(root / "depth" / f"{i:05}.png"), dtype=np.float32)
            native_depth = (encoded[:, :, 0] + 256 * encoded[:, :, 1] + 65536 * encoded[:, :, 2]) * (1000 / 16777215)
            visible = native_depth + .03 >= layer_depth
            alpha = layers[:, :, 3] * visible
            car_image = (raw * (1 - alpha[:, :, None]) + layers[:, :, :3] * 255 * alpha[:, :, None]).clip(0, 255).astype(np.uint8)
            mask = (layers[:, :, 3] > .5) & np.isfinite(layer_depth)
            if mask.any():
                occlusion.append(float(np.mean(~visible[mask])))
                if i in wanted:
                    depth_deltas.append({"frame": i, "quantiles_m": np.quantile((native_depth - layer_depth)[mask], [.1, .5, .9]).tolist()})
            neural_image = (np.asarray(Image.open(root / f"cns-preview-{i:04}.png")) if args.preview_only else cns_reader.get_next_data())
            replay.qpos[:] = body["qpos"][i]; replay.qvel[:] = body["qvel"][i]; replay.ctrl[:] = body["ctrl"][i]
            replay.time = body["time"][i]
            mj.mj_forward(rig.model, replay)
            assert float(np.max(np.abs(replay.qpos - body["qpos"][i]))) == 0
            renderer.update_scene(replay, camera=camera)
            renderer.scene.flags[mj.mjtRndFlag.mjRND_SKYBOX] = False
            canvas = Image.new("RGB", (1920, 1080), "black")
            canvas.paste(Image.fromarray(car_image), (24, 64))
            canvas.paste(Image.fromarray(neural_image), (1296, 64))
            canvas.paste(Image.fromarray(renderer.render()), (1296, 584))
            draw = ImageDraw.Draw(canvas)
            title = "Roundabout" if config["mode"] == "indicators" else "Steering + indicators"
            draw.text((24, 23), title + f"  /  Exit {config['route']['exit_number']}", font=fonts[24], fill="#eee")
            draw.text((1272, 23), f"{record['speed_m_s'] * 3.6:.0f} km/h", anchor="ra", font=fonts[28], fill="white")
            draw.text((1296, 23), "Neural activity", font=fonts[24], fill="#eee")
            draw.text((1296, 540), "Fly", font=fonts[24], fill="#eee")
            signal = record["applied_signal"].upper()
            draw.text((1896, 540), "SIGNAL " + signal, anchor="ra", font=fonts[24], fill="#ffbd59" if signal != "OFF" else "#999")
            draw_steering_readout(canvas, requested_angle=record["requested_angle"], wheel_angle=record["wheel_angle"],
                                  applied_steer=record["applied_steer"])
            draw.text((970, 1052), f"Stalk {np.degrees(record['stalk_angle']):+.1f}°", anchor="mm", font=fonts[24], fill="#ddd")
            draw_site_brand(canvas)
            if record["index"] in wanted:
                canvas.save(root / f"preview-{i:04}.png")
                Image.fromarray(car_image).save(root / f"sponsored-car-{i:04}.png")
            if writer:
                writer.append_data(np.asarray(canvas))
            if i % 100 == 0:
                print(json.dumps({"frame": i, "wall_seconds": time.perf_counter() - started}), flush=True)
        if writer:
            credit = Image.new("RGB", (1920, 1080), "black")
            draw = ImageDraw.Draw(credit)
            lines = ["Vehicle: CARLA 0.9.16", "Computer Vision Center (CVC), Universitat Autònoma de Barcelona",
                     "Connectome: MaleCNS / Janelia · Fly body: NeuroMechFly / FlyGym, EPFL",
                     f"Sponsor livery: revision {manifest['revision']} · layout {manifest['layoutVersion']}"]
            for j, line in enumerate(lines):
                draw.text((960, 448 + j * 50), line, anchor="mm", font=fonts[28] if j == 0 else fonts[24], fill="#ddd")
            draw_site_brand(credit)
            for _ in range(config["fps"] * 2):
                writer.append_data(np.asarray(credit))
    finally:
        reader.close(); renderer.close()
        if writer:
            writer.close()
        if cns_reader:
            cns_reader.close()
    metrics = {"status": "previewed" if args.preview_only else "rendered", "width": 1920, "height": 1080,
               "fps": config["fps"], "source_frames": len(frames), "frames": len(frames) + config["fps"] * 2,
               "duration_seconds": len(frames) / config["fps"] + 2, "credit_seconds": 2,
               "playback_speed": 1., "same_episode": True, "mujoco_gpu": gpu,
               "sponsor_revision": manifest["revision"], "sponsor_layout": manifest["layoutVersion"], "sponsor_layer_sha256": sha(sponsor_root / "sponsor-layer.png"),
               "native_depth_occlusion": True, "mean_occluded_sponsor_fraction": float(np.mean(occlusion)),
               "native_depth_margin_metres": .03, "renderer_sha256": sha(__file__),
               "depth_alignment_quantiles": depth_deltas,
               "presentation_note": "Sponsor surfaces composited from the supplied Blender model in the recorded camera frame; CARLA footage, depth, body and neural states share one episode.",
               "body_trace_sha256": sha(root / "body-trace.npz"), "neural_trace_sha256": sha(root / "neural-trace.npz"),
               "frames_sha256": sha(root / "frames.json"), "wall_seconds": time.perf_counter() - started}
    if writer:
        metrics["video_sha256"] = sha(root / "flyhard-16x9.mp4")
    (root / ("preview-metrics.json" if args.preview_only else "render-metrics.json")).write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
