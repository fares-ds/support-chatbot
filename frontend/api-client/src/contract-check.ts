// Checked by `pnpm typecheck`, never run: if the API's health response or the WebSocket events
// change shape, this stops compiling, and so would the dashboard and the widget.
import type { FullHealthReport, HealthResponse, ServerEvent } from "./index";
import { client, healthOptions } from "./index";

type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Expect<T extends true> = T;

// The health query's data is the API's FullHealthReport.
type HealthQueryData = Awaited<ReturnType<NonNullable<ReturnType<typeof healthOptions>["queryFn"]>>>;
export type HealthQueryIsTheReport = Expect<Equal<HealthQueryData, FullHealthReport>>;
export type HealthResponseIsTheReport = Expect<Equal<HealthResponse, FullHealthReport>>;

export const report: FullHealthReport = {
  status: "ok",
  checks: { postgres: "ok", worker: "down" },
  schema_revision: "0002",
  worker_heartbeat: null,
};

// Events are told apart by their literal type.
export const ready: ServerEvent = { type: "connection.ready", connected_at: "2026-10-09T10:00:00Z" };
// @ts-expect-error: an event type the API never sends
export const unknown: ServerEvent = { type: "connection.lost", connected_at: "2026-10-09T10:00:00Z" };

// The dashboard and the widget configure the shared client once.
client.setConfig({ baseUrl: "https://chat.example.com", auth: () => "a bearer token" });
