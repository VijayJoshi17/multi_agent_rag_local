# Post-Incident Review: INC-2291 — Lidar dropouts after firmware 4.2.1

**Severity:** SEV-2  **Status:** Resolved  **Author:** Fleet Reliability team

## Summary

On 11 March 2025, LR-200 robots at the Rotterdam fulfilment site began stopping unexpectedly in aisles. The cause was a race condition in lidar driver initialisation introduced in firmware 4.2.1, which caused the front safety lidar to intermittently report no data. The robots behaved safely — a missing lidar signal triggers a protective stop — but throughput at the site dropped by 31% for two days.

## Impact

- 37 LR-200 units at the Rotterdam site were affected.
- No LR-400 units were affected, because the LR-400 uses a different lidar driver.
- No injuries or property damage occurred.
- The customer received a service credit equal to two days of fleet subscription fees.

## Timeline (all times CET)

- 11 March 08:40 — Site operators report robots halting in aisles.
- 11 March 10:15 — On-call engineer correlates stops with the firmware 4.2.1 rollout completed the previous night.
- 11 March 12:30 — Rollout of 4.2.1 paused for all other sites.
- 12 March 16:00 — Affected units rolled back to firmware 4.1.8 as a temporary mitigation.
- 13 March 09:00 — Firmware 4.2.3, containing the fix, released and deployed to Rotterdam.

## Root cause

Firmware 4.2.1 parallelised sensor start-up to shorten boot time. When the depth camera and front lidar initialised at the same time, a shared USB controller could drop the lidar's enumeration, leaving the lidar driver waiting for data that never arrived.

## Corrective actions

1. Sensor initialisation is serialised again (fixed in 4.2.3).
2. Firmware rollouts now use a staged canary: 5% of a site's fleet for 24 hours before full rollout.
3. A new fleet alert fires when more than three robots at one site enter protective stop within ten minutes.
