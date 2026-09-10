"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { Maximize2, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { artworkBounds } from "@/lib/artwork-bounds.mjs";
import styles from "./car-ad-preview.module.css";
import {
  slots,
  activeSlots,
  modelUrl,
  artworkCrops,
  money,
  minimumBid,
  type Placement,
} from "@/lib/auction";

export type View = "perspective" | "left" | "right" | "top" | "front" | "back";
type Props = {
  placements: Record<string, Placement>;
  selected: string | null;
  view: View;
  onSelect: (id: string) => void;
  resetView?: View;
  onInteract?: () => void;
  onResetView?: () => void;
  focusOnSelected?: boolean;
  previewing?: boolean;
};
type Runtime = {
  scene: THREE.Scene;
  model?: THREE.Group;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  renderer: THREE.WebGLRenderer;
  materials: Map<THREE.Mesh, THREE.Material | THREE.Material[]>;
  textures: Map<string, THREE.Texture>;
  loaded: Map<string, string>;
  pending: Map<string, string>;
  destination: THREE.Vector3 | null;
  targetDestination: THREE.Vector3 | null;
  disposed: boolean;
};
const angles: Record<View, [number, number, number]> = {
  perspective: [3.3, 2.65, -4.4],
  left: [0, 1.8, -5.5],
  right: [0, 1.8, 5.5],
  top: [0, 7, -0.01],
  front: [5.5, 1.7, 0],
  back: [-5.5, 1.7, 0],
};
const faceDirections: Record<string, [number, number, number]> = {
  left: [0.12, 0.18, -1],
  right: [-0.12, 0.18, 1],
  top: [0.12, 1, -0.08],
  front: [1, 0.18, 0.05],
  back: [-1, 0.18, -0.05],
};

function panelOutline(geometry: THREE.BufferGeometry) {
  const positions = geometry.getAttribute("position");
  const uv = geometry.getAttribute("uv");
  const index = geometry.getIndex();
  const count = index?.count ?? positions.count;
  const edges: number[] = [];
  // Outline the artwork's UV boundary, excluding seams where the car body curves.
  for (let i = 0; i < count; i += 3) {
    const triangle = [0, 1, 2].map((offset) =>
      index ? index.getX(i + offset) : i + offset,
    );
    for (let edge = 0; edge < 3; edge++) {
      const a = triangle[edge],
        b = triangle[(edge + 1) % 3];
      const boundary = [0, 1].some(
        (end) =>
          (Math.abs(uv.getX(a) - end) < 0.001 &&
            Math.abs(uv.getX(b) - end) < 0.001) ||
          (Math.abs(uv.getY(a) - end) < 0.001 &&
            Math.abs(uv.getY(b) - end) < 0.001),
      );
      if (boundary)
        for (const vertex of [a, b])
          edges.push(
            positions.getX(vertex),
            positions.getY(vertex),
            positions.getZ(vertex),
          );
    }
  }
  return new THREE.BufferGeometry().setAttribute(
    "position",
    new THREE.Float32BufferAttribute(edges, 3),
  );
}

function frameCamera(state: Runtime, view: View, focus: string | null) {
  const slot = focus ? slots.find((slot) => slot.id === focus) : undefined;
  const panel = slot && state.model?.getObjectByName(slot.panel);
  const target = panel
    ? new THREE.Box3().setFromObject(panel).getCenter(new THREE.Vector3())
    : new THREE.Vector3(0, 0.82, 0);
  if (slot && panel) {
    const tangent = Math.tan(THREE.MathUtils.degToRad(state.camera.fov / 2));
    const distance = Math.max(
      1.05,
      (slot.height_m * 1.9) / (2 * tangent),
      (slot.width_m * 1.65) / (2 * tangent * state.camera.aspect),
    );
    state.destination = new THREE.Vector3(...faceDirections[slot.face])
      .normalize()
      .multiplyScalar(distance)
      .add(target);
  } else {
    // Keep the full car in frame on narrow screens without reducing its desktop presence.
    const position = new THREE.Vector3(...angles[view]);
    const narrow = Math.max(1, 1.05 / state.camera.aspect);
    state.destination = position.sub(target).multiplyScalar(narrow).add(target);
  }
  state.targetDestination = target;
  state.controls.minDistance = slot ? 0.5 : 3.2;
  state.renderer.domElement.dataset.focusedSlot = slot?.id ?? "";
  state.renderer.domElement.dataset.cameraView = view;
}

export default function CarViewer({
  placements,
  selected,
  view,
  onSelect,
  resetView = "perspective",
  onInteract,
  onResetView,
  focusOnSelected = false,
  previewing = false,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<Runtime | null>(null);
  const select = useRef(onSelect);
  const interact = useRef(onInteract);
  interact.current = onInteract;
  const currentPlacements = useRef(placements);
  const framing = useRef({ view, focus: focusOnSelected ? selected : null });
  framing.current = { view, focus: focusOnSelected ? selected : null };
  select.current = onSelect;
  currentPlacements.current = placements;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewFocused = useRef(false);
  const previewPointer = useRef(false);
  function keepPreview() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  }
  function dismissPreview() {
    keepPreview();
    previewFocused.current = false;
    previewPointer.current = false;
    setHovered(null);
  }
  function leavePreview() {
    if (hoverTimer.current || previewFocused.current || previewPointer.current)
      return;
    hoverTimer.current = setTimeout(() => {
      hoverTimer.current = null;
      if (!previewFocused.current && !previewPointer.current) setHovered(null);
    }, 350);
  }
  useEffect(() => {
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismissPreview();
    };
    document.addEventListener("keydown", onEscape);
    return () => {
      keepPreview();
      document.removeEventListener("keydown", onEscape);
    };
  }, []);
  const [progress, setProgress] = useState(0);
  const [textureError, setTextureError] = useState(false);

  useEffect(() => {
    const element = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      setError(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive Mini Cooper. Drag to rotate, scroll to zoom, or select a spot from the list below.",
    );
    renderer.domElement.setAttribute("role", "img");
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(...angles[framing.current.view]);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.82, 0);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 3.2;
    controls.maxDistance = 11;
    controls.maxPolarAngle = Math.PI / 2 - 0.035;
    controls.autoRotate = false;
    const onControlsStart = () => {
      const state = runtime.current;
      if (state) {
        state.destination = null;
        state.targetDestination = null;
      }
      interact.current?.();
    };
    controls.addEventListener("start", onControlsStart);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const environment = pmrem.fromScene(room, 0.04);
    scene.environment = environment.texture;
    room.dispose();
    pmrem.dispose();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x969e94, 2));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(3, 7, -4);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -5;
    key.shadow.camera.right = 5;
    key.shadow.camera.top = 5;
    key.shadow.camera.bottom = -5;
    key.shadow.normalBias = 0.035;
    scene.add(key);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 200),
      new THREE.ShadowMaterial({ opacity: 0.15 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.015;
    floor.receiveShadow = true;
    scene.add(floor);
    const state: Runtime = {
      scene,
      camera,
      controls,
      renderer,
      materials: new Map(),
      textures: new Map(),
      loaded: new Map(),
      pending: new Map(),
      destination: null,
      targetDestination: null,
      disposed: false,
    };
    runtime.current = state;
    const draco = new DRACOLoader().setDecoderPath("/draco/");
    const loader = new GLTFLoader().setDRACOLoader(draco);
    loader.load(
      modelUrl,
      (gltf) => {
        if (state.disposed) return;
        state.model = gltf.scene;
        gltf.scene.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            object.castShadow = !object.userData.slot_id || object.userData.role === "billboard_structure";
            object.receiveShadow = !object.userData.slot_id || object.userData.role === "billboard_structure";
            state.materials.set(object, object.material);
          }
        });
        scene.add(gltf.scene);
        setReady(true);
        renderer.domElement.dataset.modelReady = "true";
      },
      (event) =>
        setProgress(
          event.total ? Math.round((event.loaded / event.total) * 100) : 0,
        ),
      () => setError(true),
    );
    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.fov = width < 600 ? 45 : 34;
      camera.updateProjectionMatrix();
      frameCamera(state, framing.current.view, framing.current.focus);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const find = (event: PointerEvent) => {
      if (!state.model) return null;
      const bounds = element.getBoundingClientRect();
      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        (-(event.clientY - bounds.top) / bounds.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObject(state.model, true).find((hit) => {
        let object: THREE.Object3D | null = hit.object;
        while (object) {
          if (!object.visible) return false;
          object = object.parent;
        }
        return true;
      });
      let object: THREE.Object3D | null = hit?.object || null;
      while (object) {
        if (object.userData.slot_id) return object.userData.slot_id as string;
        object = object.parent;
      }
      return null;
    };
    let down = { x: 0, y: 0 };
    const onDown = (event: PointerEvent) => {
      dismissPreview();
      down = { x: event.clientX, y: event.clientY };
      state.destination = null;
      state.targetDestination = null;
    };
    const onMove = (event: PointerEvent) => {
      if (event.buttons) {
        dismissPreview();
        return;
      }
      const id = find(event);
      if (id) {
        keepPreview();
        setHovered(id);
      } else leavePreview();
      renderer.domElement.style.cursor = id ? "pointer" : "grab";
    };
    const onUp = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - down.x, event.clientY - down.y) < 6) {
        const id = find(event);
        if (id) select.current(id);
      }
    };
    const onLeave = leavePreview;
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let animation = 0;
    const render = () => {
      if (state.destination) {
        camera.position.lerp(state.destination, motion.matches ? 1 : 0.09);
        if (camera.position.distanceTo(state.destination) < 0.01)
          state.destination = null;
      }
      if (state.targetDestination) {
        controls.target.lerp(
          state.targetDestination,
          motion.matches ? 1 : 0.09,
        );
        if (controls.target.distanceTo(state.targetDestination) < 0.001)
          state.targetDestination = null;
      }
      controls.update();
      renderer.render(scene, camera);
      animation = requestAnimationFrame(render);
    };
    render();
    return () => {
      state.disposed = true;
      cancelAnimationFrame(animation);
      observer.disconnect();
      controls.removeEventListener("start", onControlsStart);
      controls.dispose();
      draco.dispose();
      const materials = new Set<THREE.Material>();
      const textures = new Set<THREE.Texture>(state.textures.values());
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const originals = state.materials.get(object);
          [
            ...(Array.isArray(object.material)
              ? object.material
              : [object.material]),
            ...(Array.isArray(originals)
              ? originals
              : originals
                ? [originals]
                : []),
          ].forEach((m) => materials.add(m));
        }
      });
      materials.forEach((material) => {
        for (const value of Object.values(material))
          if (value instanceof THREE.Texture) textures.add(value);
        material.dispose();
      });
      textures.forEach((texture) => texture.dispose());
      environment.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      runtime.current = null;
    };
  }, []);

  useEffect(() => {
    if (runtime.current)
      frameCamera(runtime.current, view, focusOnSelected ? selected : null);
  }, [view, ready, focusOnSelected, selected]);

  useEffect(() => {
    const state = runtime.current;
    const slot = slots.find((slot) => slot.id === selected);
    const panel = slot && state?.model?.getObjectByName(slot.panel);
    if (!slot || !(panel instanceof THREE.Mesh) || !focusOnSelected) return;
    const outline = new THREE.LineSegments(
      panelOutline(panel.geometry),
      new THREE.LineBasicMaterial({ color: "#b7e25e", depthWrite: false }),
    );
    const normal = new THREE.Vector3(...faceDirections[slot.face]).normalize();
    normal.applyQuaternion(
      panel.getWorldQuaternion(new THREE.Quaternion()).invert(),
    );
    outline.position.copy(normal.multiplyScalar(0.008));
    outline.renderOrder = 2;
    panel.add(outline);
    return () => {
      panel.remove(outline);
      outline.geometry.dispose();
      outline.material.dispose();
    };
  }, [selected, ready, focusOnSelected]);

  useEffect(() => {
    const state = runtime.current;
    if (!state?.model) return;
    const loader = new THREE.TextureLoader();
    setTextureError(false);
    for (const slot of slots) {
      const group = state.model.getObjectByName(slot.node);
      const panel = state.model.getObjectByName(slot.panel) as
        THREE.Mesh | undefined;
      if (!panel || !group) continue;
      group.visible = activeSlots(placements).some(
        (active) => active.id === slot.id,
      );
      if (!group.visible) continue;
      const placement = placements[slot.id];
      if (!placement) {
        if (state.loaded.has(slot.id)) {
          (panel.material as THREE.Material).dispose();
          panel.material = (
            state.materials.get(panel) as THREE.Material
          ).clone();
          state.textures.get(slot.id)?.dispose();
          state.textures.delete(slot.id);
          state.loaded.delete(slot.id);
          group.traverse((object) => {
            if (object.userData.role === "availability_marker")
              object.visible = true;
          });
        }
        state.pending.delete(slot.id);
        continue;
      }
      if (
        state.loaded.get(slot.id) === placement.textureUrl ||
        state.pending.get(slot.id) === placement.textureUrl
      )
        continue;
      state.pending.set(slot.id, placement.textureUrl);
      loader.load(
        placement.textureUrl,
        (texture: THREE.Texture) => {
          if (
            state.disposed ||
            currentPlacements.current[slot.id]?.textureUrl !==
              placement.textureUrl
          ) {
            texture.dispose();
            return;
          }
          state.pending.delete(slot.id);
          // A sponsor may move to a differently shaped panel. Fit the published
          // artwork without stretching it; the surrounding area stays transparent.
          const image = texture.image as HTMLImageElement;
          const aspect = slot.width_m / slot.height_m;
          if (Math.abs(image.width / image.height / aspect - 1) > 0.01) {
            const canvas = document.createElement("canvas");
            canvas.width = 1024;
            canvas.height = Math.round(canvas.width / aspect);
            const context = canvas.getContext("2d");
            if (!context) {
              texture.dispose();
              setTextureError(true);
              return;
            }
            const source = document.createElement("canvas");
            source.width = image.width;
            source.height = image.height;
            const sourceContext = source.getContext("2d")!;
            sourceContext.drawImage(image, 0, 0);
            const crop = artworkBounds(
              sourceContext.getImageData(0, 0, image.width, image.height).data,
              image.width,
              image.height,
              artworkCrops[placement.textureUrl],
            );
            const inset = artworkCrops[placement.textureUrl] ? 1 : 0.9;
            const scale = Math.min(
              (canvas.width * inset) / crop.width,
              (canvas.height * inset) / crop.height,
            );
            const width = crop.width * scale;
            const height = crop.height * scale;
            context.drawImage(
              image,
              crop.left,
              crop.top,
              crop.width,
              crop.height,
              (canvas.width - width) / 2,
              (canvas.height - height) / 2,
              width,
              height,
            );
            texture.dispose();
            texture = new THREE.CanvasTexture(canvas);
          }
          texture.colorSpace = THREE.SRGBColorSpace;
          texture.flipY = false;
          texture.anisotropy = Math.min(
            8,
            state.renderer.capabilities.getMaxAnisotropy(),
          );
          const old = panel.material;
          panel.material = new THREE.MeshStandardMaterial({
            map: texture,
            transparent: true,
            depthWrite: false,
            alphaTest: 0.001,
            roughness: 0.55,
            metalness: 0.05,
            side: THREE.DoubleSide,
            polygonOffset: true,
            polygonOffsetFactor: -4,
            polygonOffsetUnits: -4,
          });
          panel.renderOrder = 2;
          if (old !== state.materials.get(panel))
            (old as THREE.Material).dispose();
          state.textures.get(slot.id)?.dispose();
          state.textures.set(slot.id, texture);
          state.loaded.set(slot.id, placement.textureUrl);
          panel.userData.liveTexture = placement.textureUrl;
          group.traverse((object) => {
            if (object.userData.role === "availability_marker")
              object.visible = false;
          });
          state.renderer.domElement.dataset.textureRevision = JSON.stringify(
            Object.fromEntries(state.loaded),
          );
        },
        undefined,
        () => {
          if (
            !state.disposed &&
            state.pending.get(slot.id) === placement.textureUrl
          ) {
            state.pending.delete(slot.id);
            setTextureError(true);
          }
        },
      );
    }
  }, [placements, ready]);

  useEffect(() => {
    const state = runtime.current;
    if (!state?.model) return;
    for (const slot of slots) {
      const panel = state.model.getObjectByName(slot.panel) as
        THREE.Mesh | undefined;
      if (!panel) continue;
      const material = panel.material as THREE.MeshStandardMaterial;
      // Original materials may be shared across spots. Clone before highlighting.
      if (material === state.materials.get(panel))
        panel.material = material.clone();
      const current = panel.material as THREE.MeshStandardMaterial;
      if (current.emissive) {
        current.emissive.set(
          !focusOnSelected && (slot.id === selected || slot.id === hovered)
            ? "#40883c"
            : "#000000",
        );
        current.emissiveIntensity = 0.25;
      }
    }
  }, [selected, hovered, ready, placements, focusOnSelected]);

  function zoom(factor: number) {
    const state = runtime.current;
    if (!state) return;
    interact.current?.();
    const offset = state.camera.position
      .clone()
      .sub(state.controls.target)
      .multiplyScalar(factor);
    offset.clampLength(state.controls.minDistance, state.controls.maxDistance);
    state.destination = offset.add(state.controls.target);
  }
  const hoveredSlot = slots.find((s) => s.id === hovered);
  const hoveredAd = hoveredSlot && placements[hoveredSlot.id];
  return (
    <div className={`viewer-shell${focusOnSelected ? " focused-viewer" : ""}`}>
      <div className="viewer-corner">
        <span className="tiny-dot" />{" "}
        {previewing
          ? "YOUR ARTWORK PREVIEW"
          : focusOnSelected
            ? `SPOT ${selected?.slice(3)} · SELECTED`
            : "LIVE LIVERY"}{" "}
        {!focusOnSelected && (
          <>
            <span className="viewer-divider">/</span> MINI COOPER S
          </>
        )}
      </div>
      <div ref={host} className="canvas-host" />
      {!ready && !error && (
        <div className="model-loading">
          <div className="loading-track">
            <span style={{ width: `${Math.max(progress, 8)}%` }} />
          </div>
          <span>Rolling out the Mini… {progress > 0 && `${progress}%`}</span>
        </div>
      )}
      {error && (
        <div className="model-loading">
          <strong>The 3D view couldn’t start.</strong>
          <span>You can still browse and buy every spot below.</span>
        </div>
      )}
      {textureError && (
        <div className="texture-error" role="status">
          A logo couldn’t load. Refresh to retry.
        </div>
      )}
      {hoveredSlot && !focusOnSelected && (
        <aside
          className={styles.preview}
          aria-label="Advertiser preview"
          data-slot-id={hoveredSlot.id}
          onPointerEnter={() => {
            previewPointer.current = true;
            keepPreview();
          }}
          onPointerLeave={() => {
            previewPointer.current = false;
            leavePreview();
          }}
          onFocus={() => {
            previewFocused.current = true;
            keepPreview();
          }}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              previewFocused.current = false;
              leavePreview();
            }
          }}
        >
          <div className={styles.position}>
            <span className="slot-number">{hoveredSlot.id.slice(3)}</span>
            <span>{hoveredSlot.name}</span>
          </div>
          {hoveredAd ? (
            <>
              <div className={styles.artwork}>
                <img
                  src={hoveredAd.textureUrl}
                  alt={`${hoveredAd.brand} artwork`}
                />
              </div>
              <strong className={styles.brand}>{hoveredAd.brand}</strong>
              {hoveredAd.message && (
                <p className={styles.message}>{hoveredAd.message}</p>
              )}
              <a
                className={styles.website}
                href={hoveredAd.url}
                target="_blank"
                rel="noopener noreferrer sponsored"
              >
                {hoveredAd.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                <span aria-hidden="true">↗</span>
              </a>
              <div className={styles.bid}>
                Current bid <strong>{money(hoveredAd.amount)}</strong>
              </div>
            </>
          ) : (
            <p className={styles.message}>Your ad could be here.</p>
          )}
          <button
            className={styles.claim}
            onClick={() => select.current(hoveredSlot.id)}
          >
            Claim this spot for {money(minimumBid(hoveredAd?.amount))} or more{" "}
            <span aria-hidden="true">↗</span>
          </button>
        </aside>
      )}
      <div className="viewer-bottom">
        <span className="drag-hint">
          <RotateCcw size={14} /> Drag to spin <span>·</span> Scroll to zoom{" "}
          {!focusOnSelected && (
            <>
              <span>·</span> Hover to see ads <span>·</span> Click a spot
            </>
          )}
        </span>
        <div className="viewer-tools">
          <button aria-label="Zoom in" onClick={() => zoom(0.8)}>
            <ZoomIn size={17} />
          </button>
          <button aria-label="Zoom out" onClick={() => zoom(1.25)}>
            <ZoomOut size={17} />
          </button>
          <button
            aria-label="Reset view"
            title={
              onResetView ? "Return to the highest bidder’s side" : "Reset view"
            }
            onClick={() => {
              onResetView?.();
              if (runtime.current)
                frameCamera(
                  runtime.current,
                  resetView,
                  focusOnSelected ? selected : null,
                );
            }}
          >
            <RotateCcw size={16} />
          </button>
          <button
            aria-label="Fullscreen car view"
            onClick={() => {
              void host.current?.parentElement
                ?.requestFullscreen?.()
                .catch(() => {});
            }}
          >
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
