import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  forgetCheckout,
  rememberCheckout,
  savedCheckouts,
} from "../src/lib/checkout-recovery";

const firstSession = "cs_test_First123";
const secondSession = "cs_live_Second456";
let values: Map<string, string>;
let storage: Storage;
let beforeNextWrite: (() => void) | undefined;

beforeEach(() => {
  values = new Map();
  beforeNextWrite = undefined;
  const interleaveWrite = () => {
    const write = beforeNextWrite;
    beforeNextWrite = undefined;
    write?.();
  };
  storage = {
    get length() {
      return values.size;
    },
    key: (index) => [...values.keys()][index] ?? null,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      interleaveWrite();
      values.set(key, value);
    },
    removeItem: (key) => {
      interleaveWrite();
      values.delete(key);
    },
    clear: () => values.clear(),
  };
  vi.stubGlobal("localStorage", storage);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("checkout recovery", () => {
  it("remembers each checkout once and forgets only the requested session", () => {
    storage.setItem("another-feature", "keep me");
    rememberCheckout(firstSession);
    rememberCheckout(secondSession);
    rememberCheckout(firstSession);

    expect(new Set(savedCheckouts())).toEqual(
      new Set([firstSession, secondSession]),
    );
    forgetCheckout(firstSession);
    expect(savedCheckouts()).toEqual([secondSession]);
    expect(storage.getItem("another-feature")).toBe("keep me");
  });

  it("preserves another tab's checkout when its write interleaves with remembering", () => {
    beforeNextWrite = () => rememberCheckout(secondSession);
    rememberCheckout(firstSession);

    expect(new Set(savedCheckouts())).toEqual(
      new Set([firstSession, secondSession]),
    );
  });

  it("preserves another tab's checkout when its write interleaves with forgetting", () => {
    rememberCheckout(firstSession);
    beforeNextWrite = () => rememberCheckout(secondSession);
    forgetCheckout(firstSession);

    expect(savedCheckouts()).toEqual([secondSession]);
  });

  it("does not restore a checkout that another tab forgets during a write", () => {
    rememberCheckout(firstSession);
    beforeNextWrite = () => forgetCheckout(firstSession);
    rememberCheckout(secondSession);

    expect(savedCheckouts()).toEqual([secondSession]);
  });

  it("ignores unrelated or malformed storage keys", () => {
    storage.setItem("another-feature", firstSession);
    storage.setItem(`other-prefix:${firstSession}`, "1");
    storage.setItem("driving-fly-checkout:", "1");
    storage.setItem("driving-fly-checkout:cs_test_not-valid", "1");
    storage.setItem(`driving-fly-checkout:cs_test_${"a".repeat(250)}`, "1");
    rememberCheckout(firstSession);

    expect(savedCheckouts()).toEqual([firstSession]);
  });

  it("does not write malformed checkout IDs", () => {
    for (const sessionId of [
      "",
      "invalid",
      "cs_test_not-valid",
      "a".repeat(251),
    ]) {
      rememberCheckout(sessionId);
      forgetCheckout(sessionId);
    }

    expect(storage.length).toBe(0);
  });

  it("keeps existing sessions when a new storage write fails", () => {
    rememberCheckout(firstSession);
    vi.spyOn(storage, "setItem").mockImplementation(() => {
      throw new Error("Storage quota exceeded");
    });

    expect(() => rememberCheckout(secondSession)).not.toThrow();
    expect(savedCheckouts()).toEqual([firstSession]);
  });

  it("tolerates blocked storage reads and removals", () => {
    rememberCheckout(firstSession);
    vi.spyOn(storage, "key").mockImplementation(() => {
      throw new Error("Storage is blocked");
    });
    vi.spyOn(storage, "removeItem").mockImplementation(() => {
      throw new Error("Storage is blocked");
    });

    expect(savedCheckouts()).toEqual([]);
    expect(() => forgetCheckout(firstSession)).not.toThrow();
  });

  it("tolerates browsers without available local storage", () => {
    vi.stubGlobal("localStorage", undefined);

    expect(savedCheckouts()).toEqual([]);
    expect(() => rememberCheckout(firstSession)).not.toThrow();
    expect(() => forgetCheckout(firstSession)).not.toThrow();
  });
});
