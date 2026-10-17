# TossIQ — Project Context

## Overview
TossIQ is an AI-powered smart waste sorting and intelligence platform for organizations, including universities, warehouses, offices, and commercial facilities.

Our goal is not just to sort trash, but to turn waste disposal into actionable data that helps organizations reduce waste, optimize purchasing, recover valuable materials, and improve safety.

## Core Features

### 1. Smart Waste Sorting
- A Raspberry Pi-connected camera captures discarded items.
- A lightweight local vision model identifies items and controls the physical sorting mechanism.
- Sorting must be fast and independent of cloud connectivity.
- Support recycling, landfill, and potentially compost, with safe handling of uncertain items.

### 2. Advanced AI Image Analysis
- A more powerful vision model analyzes captured images asynchronously, initially running on a laptop.
- Identify specific objects, materials, visible contamination, and potential improper disposal.
- Detect potentially hazardous, restricted, reusable, or valuable discarded items.
- Advanced analysis must never delay physical sorting.

### 3. Custom Organization Recognition
- Organizations can upload their own products, supplies, menu items, reference images, and catalogs.
- Match discarded items against organization-specific products without requiring retraining for every addition.
- Support custom disposal policies, restricted items, and product costs.

### 4. Waste Intelligence Dashboard
- Track discarded item counts, categories, timestamps, and locations.
- Show waste composition, trends, frequently discarded products, and comparisons across bins or buildings.
- Display item-level history, AI analysis, and safety alerts.
- Estimate financial waste using product catalog costs.
- Provide AI-driven recommendations for purchasing, waste reduction, and operational improvements.

## High-Level Architecture
- **Raspberry Pi:** Camera capture, fast inference, physical sorting.
- **Laptop:** Advanced vision analysis and custom catalog matching.
- **Oracle Cloud Infrastructure:** Persistent data and image storage, centralized analytics, and dashboard support.
- **Web Dashboard:** Organization-facing waste intelligence and management.

Keep these components modular and independently operable.

## Hardware Constraints
- We have a Raspberry Pi-compatible camera and plan to integrate a physical sorting mechanism.
- **No weight sensors are available.** Focus on item identification, counts, and trends rather than measured weight.
- Weight tracking, inventory integrations, and advanced purchasing forecasts are future features.

## Hackathon MVP Goals
Demonstrate an end-to-end system where:
1. An item is captured, recognized, and physically sorted.
2. Advanced AI produces detailed item analysis.
3. An administrator can register a custom product that TossIQ subsequently recognizes.
4. Disposal events update a cloud-backed analytics dashboard.
5. The system generates meaningful waste insights or safety alerts from collected data.

## Development Priorities
- Prioritize working end-to-end functionality over unnecessary complexity.
- Keep physical sorting low-latency and independent of advanced AI.
- Build for general-purpose organizational use, not just food waste.
- Distinguish observed data from AI estimates and predictions.
- Use OCI meaningfully to support the hackathon's technical judging criteria.
- Keep implementation flexible and extensible without overengineering.
