"use client";

import { useEffect, useRef, useState } from "react";
import { ImagePlus, Move, RotateCcw } from "lucide-react";

export type PreparedArtwork = { blob: Blob | null; logo?: Blob; url?: string };
type Transform = { scale: number; rotation: number; x: number; y: number };
const initialTransform: Transform = { scale: 100, rotation: 0, x: 50, y: 50 };
const clamp = (n: number) => Math.min(100, Math.max(0, n));

async function prepareLogo(bitmap: ImageBitmap): Promise<Blob> {
  const surface = document.createElement("canvas");
  const scale = Math.min(1, 512 / Math.max(bitmap.width, bitmap.height));
  surface.width = Math.max(1, Math.round(bitmap.width * scale));
  surface.height = Math.max(1, Math.round(bitmap.height * scale));
  surface
    .getContext("2d")!
    .drawImage(bitmap, 0, 0, surface.width, surface.height);
  return new Promise((resolve, reject) => {
    surface.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not prepare your logo."));
    }, "image/png");
  });
}

export default function ArtworkEditor({
  ratio,
  disabled,
  onChange,
  onError,
}: {
  ratio: number;
  disabled: boolean;
  onChange: (artwork: PreparedArtwork) => void;
  onError: (message: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [source, setSource] = useState<{
    bitmap: ImageBitmap;
    logo: Blob;
    name: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [transparent, setTransparent] = useState(true);
  const [background, setBackground] = useState("#ffffff");
  const [transform, setTransform] = useState<Transform>(initialTransform);
  const loadId = useRef(0);
  const url = useRef("");
  const callbacks = useRef({ onChange, onError });
  callbacks.current = { onChange, onError };
  const drag = useRef<{
    pointerId: number;
    clientX: number;
    clientY: number;
    x: number;
    y: number;
  } | null>(null);

  useEffect(
    () => () => {
      loadId.current++;
      if (url.current) URL.revokeObjectURL(url.current);
    },
    [],
  );
  useEffect(() => () => source?.bitmap.close(), [source]);

  useEffect(() => {
    if (!source || loading) return;
    let cancelled = false;
    callbacks.current.onChange({ blob: null });
    const frame = requestAnimationFrame(() => {
      const surface = canvas.current!;
      surface.width = ratio >= 1 ? 1024 : Math.max(1, Math.round(1024 * ratio));
      surface.height =
        ratio >= 1 ? Math.max(1, Math.round(1024 / ratio)) : 1024;
      const context = surface.getContext("2d")!;
      context.clearRect(0, 0, surface.width, surface.height);
      if (!transparent) {
        context.fillStyle = background;
        context.fillRect(0, 0, surface.width, surface.height);
      }
      const fit =
        Math.min(
          surface.width / source.bitmap.width,
          surface.height / source.bitmap.height,
        ) * 0.88;
      const scale = (fit * transform.scale) / 100;
      context.save();
      context.translate(
        (surface.width * transform.x) / 100,
        (surface.height * transform.y) / 100,
      );
      context.rotate((transform.rotation * Math.PI) / 180);
      context.scale(scale, scale);
      context.drawImage(
        source.bitmap,
        -source.bitmap.width / 2,
        -source.bitmap.height / 2,
      );
      context.restore();
      surface.toBlob((blob) => {
        if (cancelled) return;
        if (!blob || blob.size > 1_500_000) {
          callbacks.current.onError(
            "The prepared image is too large. Try a simpler logo.",
          );
          return;
        }
        const previous = url.current;
        url.current = URL.createObjectURL(blob);
        callbacks.current.onChange({
          blob,
          logo: source.logo,
          url: url.current,
        });
        if (previous) URL.revokeObjectURL(previous);
      }, "image/png");
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [source, loading, ratio, transparent, background, transform]);

  async function chooseFile(file: File) {
    if (
      !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
      file.size > 10_000_000
    ) {
      callbacks.current.onError("Choose a PNG, JPG, or WebP under 10 MB.");
      return;
    }
    const id = ++loadId.current;
    setLoading(true);
    callbacks.current.onChange({ blob: null });
    callbacks.current.onError("");
    try {
      const bitmap = await createImageBitmap(file);
      let logo: Blob;
      try {
        logo = await prepareLogo(bitmap);
      } catch (error) {
        bitmap.close();
        throw error;
      }
      if (id !== loadId.current) {
        bitmap.close();
        return;
      }
      setSource({ bitmap, logo, name: file.name });
      setTransform(initialTransform);
    } catch {
      if (id === loadId.current)
        callbacks.current.onError(
          "We couldn’t read that image. Choose another PNG, JPG, or WebP.",
        );
    } finally {
      if (id === loadId.current) setLoading(false);
    }
  }

  function adjust(key: keyof Transform, value: number) {
    if (disabled || loading) return;
    callbacks.current.onChange({ blob: null });
    setTransform((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="artwork-editor">
      <div className="field-heading artwork-heading">
        <label htmlFor="artwork-file">Your artwork</label>
        {source && (
          <label className="change-artwork" htmlFor="artwork-file">
            Change image
          </label>
        )}
      </div>
      <input
        id="artwork-file"
        className="file-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={disabled || loading}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void chooseFile(file);
          event.target.value = "";
        }}
      />
      {!source ? (
        <label className="upload-area" htmlFor="artwork-file">
          <ImagePlus size={25} strokeWidth={1.4} />
          <strong>
            {loading
              ? "Preparing your artwork…"
              : "Give your logo a place on the car"}
          </strong>
          <span>PNG, JPG, or WebP · Up to 10 MB</span>
        </label>
      ) : (
        <>
          <div className="artwork-stage" aria-busy={loading}>
            <canvas
              ref={canvas}
              className="logo-position-canvas"
              style={{
                width: `min(100%, ${Math.min(360, 180 * ratio)}px)`,
                aspectRatio: ratio,
              }}
              role="img"
              aria-label="Logo positioning canvas. Drag to move your logo, or use the arrow keys."
              tabIndex={disabled ? -1 : 0}
              onPointerDown={(event) => {
                if (disabled || loading || event.button !== 0) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                drag.current = {
                  pointerId: event.pointerId,
                  clientX: event.clientX,
                  clientY: event.clientY,
                  x: transform.x,
                  y: transform.y,
                };
              }}
              onPointerMove={(event) => {
                const start = drag.current;
                if (
                  disabled ||
                  loading ||
                  !start ||
                  start.pointerId !== event.pointerId
                )
                  return;
                const bounds = event.currentTarget.getBoundingClientRect();
                callbacks.current.onChange({ blob: null });
                setTransform((current) => ({
                  ...current,
                  x: clamp(
                    start.x +
                      ((event.clientX - start.clientX) / bounds.width) * 100,
                  ),
                  y: clamp(
                    start.y +
                      ((event.clientY - start.clientY) / bounds.height) * 100,
                  ),
                }));
              }}
              onPointerUp={(event) => {
                drag.current = null;
                event.currentTarget.releasePointerCapture(event.pointerId);
              }}
              onPointerCancel={() => {
                drag.current = null;
              }}
              onLostPointerCapture={() => {
                drag.current = null;
              }}
              onKeyDown={(event) => {
                if (
                  !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
                    event.key,
                  ) ||
                  disabled ||
                  loading
                )
                  return;
                event.preventDefault();
                const step = event.shiftKey ? 10 : 1;
                const axis = ["ArrowLeft", "ArrowRight"].includes(event.key)
                  ? "x"
                  : "y";
                adjust(
                  axis,
                  clamp(
                    transform[axis] +
                      (["ArrowLeft", "ArrowUp"].includes(event.key)
                        ? -step
                        : step),
                  ),
                );
              }}
            />
          </div>
          <div className="artwork-edit-hint">
            <span>
              <Move size={12} /> Drag to position
            </span>
            <button
              type="button"
              disabled={disabled || loading}
              onClick={() => {
                callbacks.current.onChange({ blob: null });
                setTransform({ ...initialTransform });
              }}
            >
              <RotateCcw size={12} /> Reset
            </button>
          </div>
          <div className="artwork-adjustments">
            {(
              [
                ["scale", "Size", 10, 400, "%"],
                ["rotation", "Rotation", -180, 180, "°"],
                ["x", "Horizontal position", 0, 100, "%"],
                ["y", "Vertical position", 0, 100, "%"],
              ] as const
            ).map(([key, label, min, max, suffix]) => (
              <label className="artwork-slider" key={key}>
                <span>
                  {label}
                  <output>
                    {Math.round(transform[key])}
                    {suffix}
                  </output>
                </span>
                <input
                  type="range"
                  aria-label={`Logo ${label.toLowerCase()}`}
                  min={min}
                  max={max}
                  step={1}
                  value={transform[key]}
                  disabled={disabled || loading}
                  onChange={(event) => adjust(key, Number(event.target.value))}
                />
              </label>
            ))}
          </div>
          <p className="artwork-crop-note">
            Anything outside the frame is cropped to your spot.
          </p>
        </>
      )}
      <div className="artwork-background">
        <span>Background</span>
        <div
          className="background-options"
          role="group"
          aria-label="Artwork background"
        >
          <button
            type="button"
            aria-pressed={transparent}
            disabled={disabled}
            onClick={() => {
              if (!transparent) {
                callbacks.current.onChange({ blob: null });
                setTransparent(true);
              }
            }}
          >
            <span className="checker-swatch" /> Transparent
          </button>
          <button
            type="button"
            aria-pressed={!transparent}
            disabled={disabled}
            onClick={() => {
              if (transparent) {
                callbacks.current.onChange({ blob: null });
                setTransparent(false);
              }
            }}
          >
            Solid color
          </button>
        </div>
        {!transparent && (
          <input
            type="color"
            aria-label="Artwork background color"
            value={background}
            disabled={disabled}
            onChange={(event) => {
              callbacks.current.onChange({ blob: null });
              setBackground(event.target.value);
            }}
          />
        )}
      </div>
      {transparent && (
        <p className="artwork-crop-note">
          Use a transparent PNG or WebP to let the car’s paint show through.
        </p>
      )}
    </div>
  );
}
