"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { applyMeetingState, invalidateResource, keys, type LiveResource } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";

type RawMeetingState = components["schemas"]["MeetingStateOut"];

/** Server → client messages. Protocol: apps/api/src/altri_api/live/router.py */
type LiveMessage =
  | { type: "hello"; user_id: string; server_now: string; meeting: RawMeetingState | null }
  | { type: "meeting"; meeting: RawMeetingState }
  | { type: "changed"; resources: LiveResource[] }
  | { type: "pong"; server_now: string };

export type LiveStatus = "connecting" | "live" | "reconnecting";

const PING_MS = 25_000;
const MAX_BACKOFF_MS = 5_000;

/**
 * The socket connects to the API directly (Next.js rewrites don't carry WebSocket upgrades). The session cookie
 * is host-scoped, not port-scoped, so the browser sends it to the API on the same host name.
 */
function liveUrl(teamId: string): string {
  const base =
    process.env.NEXT_PUBLIC_API_WS_URL ??
    `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
  return `${base}/api/v1/teams/${encodeURIComponent(teamId)}/live`;
}

/**
 * Keeps one live connection per team and feeds it into the query cache:
 * - `hello` / `meeting`: the authoritative meeting snapshot goes straight into the cache.
 * - `changed`: the named resources are refetched over REST.
 * - reconnect: the `hello` snapshot restores the meeting, and every team query is refetched, so nothing
 *   missed while offline survives. Mutations never go through the socket.
 */
export function useTeamLive(teamId: string, enabled = true): LiveStatus {
  const qc = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("connecting");

  useEffect(() => {
    // Only once the team is known to be readable; the server would refuse the socket anyway.
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let hadSession = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pingTimer: ReturnType<typeof setInterval> | undefined;

    const handle = (message: LiveMessage) => {
      switch (message.type) {
        case "hello":
          if (message.meeting) applyMeetingState(qc, message.meeting);
          else qc.setQueryData(keys.activeMeeting(teamId), null);
          if (hadSession) void qc.invalidateQueries({ queryKey: keys.team(teamId) });
          hadSession = true;
          break;
        case "meeting":
          applyMeetingState(qc, message.meeting);
          break;
        case "changed":
          for (const resource of message.resources) void invalidateResource(qc, teamId, resource);
          break;
      }
    };

    const connect = () => {
      const ws = new WebSocket(liveUrl(teamId));
      socket = ws;
      ws.addEventListener("open", () => {
        attempt = 0;
        setStatus("live");
        pingTimer = setInterval(() => ws.send(JSON.stringify({ type: "ping" })), PING_MS);
      });
      ws.addEventListener("message", (event) => {
        try {
          handle(JSON.parse(event.data as string) as LiveMessage);
        } catch {
          // A malformed frame is dropped; the next snapshot or refetch corrects the view.
        }
      });
      ws.addEventListener("close", () => {
        clearInterval(pingTimer);
        if (disposed) return;
        setStatus("reconnecting");
        retryTimer = setTimeout(connect, Math.min(MAX_BACKOFF_MS, 500 * 2 ** attempt++));
      });
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      clearInterval(pingTimer);
      socket?.close();
    };
  }, [teamId, enabled, qc]);

  return status;
}
