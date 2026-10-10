# Caddy with the dashboard's and the widget's files. Placeholders until M1 builds them from
# frontend/ (ADR-0027). The Caddyfile comes from the install bundle.

# Caddy 2.11.7, built with the builder image's Go (1.27.2): the official 2.11.7-alpine image's
# binary was built with Go 1.26.8, which has two high net/http vulnerabilities (CVE-2026-78667,
# CVE-2026-97031). Caddy 2.11.7 also requires golang.org/x/net v0.59.0, whose HTTP/2 has a high
# denial of service (CVE-2026-78669), so the build replaces it with v0.60.0. Go back to the plain
# image once a Caddy release ships with both fixed.
FROM caddy:2.11.7-builder-alpine AS build
RUN xcaddy build v2.11.7 --replace golang.org/x/net=golang.org/x/net@v0.60.0 --output /usr/bin/caddy

FROM caddy:2.11.7-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
COPY site /srv
