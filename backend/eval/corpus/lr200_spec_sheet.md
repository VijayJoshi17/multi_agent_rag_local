# LR-200 "Sparrow" — Autonomous Mobile Robot: Technical Specification

The LR-200 is Larkspur's compact autonomous mobile robot (AMR) for tote and bin transport in e-commerce fulfilment centres. It navigates without floor markers using 2D lidar SLAM and is designed to work in mixed traffic alongside people.

## Physical

- Dimensions (L × W × H): 820 × 560 × 310 mm
- Weight (without payload): 96 kg
- Maximum payload: 180 kg
- Top speed: 1.8 m/s (limited to 1.2 m/s in zones marked as pedestrian areas)
- Turning: zero-radius turn on the spot
- Ingress protection: IP54

## Power

- Battery: 48 V lithium iron phosphate (LiFePO4), 2.1 kWh
- Runtime: up to 10 hours at a typical 60% duty cycle
- Charging: automatic docking; 0–80% in 45 minutes, full charge in 70 minutes
- Battery service life: rated for 4,000 full charge cycles

## Sensors and safety

- Two 270° safety lidars (front and rear), PL d / SIL 2 certified
- 3D depth camera for overhanging obstacles
- Emergency stop buttons on all four sides
- Audible and light signalling for turns and reversing

## Connectivity

The LR-200 connects over Wi-Fi 6 (802.11ax) and is managed through the Larkspur Fleet API. Firmware updates are delivered over the air and installed only while the robot is docked.

## Environment

Operating temperature is +5 °C to +40 °C. The LR-200 is not rated for cold-storage or freezer environments; for those, see the LR-400.

## Warranty

Standard warranty is 24 months, extendable to 60 months with a Larkspur Care service contract.
