// The API client (ADR-0026): generated from the backend by `pnpm generate`, never by hand.
export * from "./generated";
export * from "./generated/@tanstack/react-query.gen";
// The shared client, which the dashboard and the widget configure once with their base URL and
// bearer token (client.setConfig), and what they need to build another.
export { client } from "./generated/client.gen";
export { createClient, createConfig } from "./generated/client";
export type { Auth, Client, Config } from "./generated/client";
export type * from "./events.gen";
