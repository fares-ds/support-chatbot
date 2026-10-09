// Hey API's openapi-ts: the client, the types, the SDK and TanStack Query's options and keys, from
// the spec the backend exports (ADR-0026).
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: "./src/generated",
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "@hey-api/sdk", "@tanstack/react-query"],
});
