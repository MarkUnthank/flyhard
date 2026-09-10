"use client";
import { useEffect, useRef, useState } from "react";
import { emptySnapshot, type AuctionSnapshot } from "@/lib/auction";

export function useAuction() {
  const [snapshot, setSnapshot] = useState<AuctionSnapshot>(emptySnapshot);
  const [connected, setConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const revision = useRef(-1);
  function accept(next: AuctionSnapshot) {
    if (next.revision >= revision.current) {
      revision.current = next.revision;
      setSnapshot(next);
      setLoaded(true);
    }
  }
  useEffect(() => {
    let stopped = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let attempt = 0;
    async function refresh() {
      try {
        const response = await fetch("/api/auction", { cache: "no-store" });
        if (response.ok && !stopped) accept(await response.json());
      } catch {
        /* Keep the last confirmed state while reconnecting. */
      }
    }
    function connect() {
      if (stopped) return;
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/live`,
      );
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        socket.send("snapshot");
      };
      socket.onmessage = (event) => {
        if (event.data === "pong") return;
        try {
          accept(JSON.parse(event.data));
        } catch {
          /* Ignore malformed messages. */
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped)
          retry = setTimeout(connect, Math.min(30_000, 1000 * 2 ** attempt++));
      };
      socket.onerror = () => socket.close();
    }
    void refresh();
    connect();
    const poll = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 15_000);
    const heartbeat = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, 25_000);
    const focus = () => {
      if (!document.hidden) {
        void refresh();
        if (socket?.readyState === WebSocket.OPEN) socket.send("snapshot");
      }
    };
    document.addEventListener("visibilitychange", focus);
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearInterval(poll);
      clearInterval(heartbeat);
      socket?.close();
      document.removeEventListener("visibilitychange", focus);
    };
  }, []);
  return { snapshot, connected, loaded, accept };
}
