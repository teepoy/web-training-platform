# Nav Reorganization: Preserved Routes

## Overview

As part of the navigation reorganization, several top-level routes have been removed from the main sidebar to reduce clutter and focus on the dataset-centric workflow. These routes remain registered in the Vue Router to support deep-linking, SDK notifications, and administrative access, but they are no longer visible as primary navigation items.

## Preserved Routes Table

| Route | Prior Nav Location | Current Entry Point | Rationale |
| :--- | :--- | :--- | :--- |
| `/jobs` | Training Jobs | Dataset Detail "Train" tab or direct URL | Training jobs are now managed within the context of their source datasets. |
| `/jobs/:id` | Job Detail | Direct URL / SDK notifications | Deep-links to specific jobs from external notifications must remain functional. |
| `/models` | Models | Dataset Detail "Predict" tab or direct URL | Models are now grouped with the datasets used for training and prediction. |
| `/schedules` | Schedules | Direct URL only | Background schedules are considered an advanced feature, removed from the main sidebar. |
| `/schedules/:id` | Schedule Detail | Direct URL | Preservation of deep-links for automated management and alerts. |
| `/dashboard` | Dashboard | `/admin/dashboard` or direct URL | General platform metrics have been moved to an administrative scope. |
| `/presets` | Preset Catalog | `/admin/presets` or direct URL | Trainer and predictor preset management has been moved to administrative settings. |

## Future Cleanup Plan

These routes should be reviewed for removal or permanent relocation once the following dependencies are addressed:
- Update SDK notification templates to use new contextual URLs where applicable.
- Finalize the `/admin` workspace layout to host the relocated dashboard and preset catalog.
- Verify no critical user flows depend on sidebar access for these items.

## Owner/Last Updated

- **Owner**: Platform Team
- **Last Updated**: 2026-05-20
