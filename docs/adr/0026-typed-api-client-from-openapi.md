# ADR-0026: The TypeScript API client is generated from FastAPI's OpenAPI spec

- Status: Accepted
- Date: 2026-10-06
- Deciders: Fares

## Context

The dashboard and the widget chat app are TypeScript; the API is FastAPI in Python ([ADR-0014](0014-v1-tech-stack.md)). The vendor asked whether oRPC would help.

- oRPC builds end-to-end typesafe APIs whose server is written with oRPC in TypeScript, and generates OpenAPI from that code ([orpc.dev](https://orpc.dev/)). FastAPI already generates the OpenAPI spec.
- oRPC's client can call any OpenAPI-compliant server through OpenAPILink. That route needs a TypeScript contract, a "Jsonified" client, and custom error decoding when the server's errors do not match oRPC's format ([OpenAPILink](https://orpc.dev/docs/openapi/client/openapi-link)).
- The documented route from an existing spec goes through a Hey API client and an experimental converter, `experimental_toORPCClient` ([oRPC + Hey API](https://orpc.unnoq.com/docs/hey-api)).
- oRPC's streaming and WebSocket transports need an oRPC server; live chat runs on FastAPI WebSockets.

## Decision

- FastAPI's OpenAPI spec is the API contract. Hey API's openapi-ts (MIT) generates the TypeScript client for the dashboard and the widget chat app, including TanStack Query options and keys ([Hey API](https://heyapi.dev/openapi-ts/plugins/tanstack-query)).
- WebSocket events are defined as Pydantic models. Their TypeScript types are generated from the models' JSON Schema.
- CI regenerates the client and the event types, and fails if either differs from what is committed.
- oRPC is not used.

## Consequences

- A change to the API or to an event shows up as a TypeScript compile error in the dashboard or widget, not as a runtime bug.
- Revisit if a TypeScript backend is ever added; oRPC would fit that case.
