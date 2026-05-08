# Preview Dataset Mode

Preview Mode allows users to browse remote data collections without immediately importing them into the platform. This provides a low-overhead way to inspect data before committing storage and compute resources.

## Overview

The feature enables a "browse first, import later" workflow:
- **Remote Exploration**: Connect to an upstream data source (e.g., S3, local directory, or mock provider) via a collection reference.
- **On-Demand Persistence**: Items are only imported into the platform's database and Label Studio when the user explicitly clicks "Persist Dataset".
- **Stateless Browsing**: Preview sessions are stored in an in-memory TTL store, keeping the main database clean of transient exploration data.

## User Flow

1. **Launch Preview**: Navigate to `/preview` and enter a `collection_ref` (e.g., a path or identifier recognized by the upstream adapter).
2. **Browse Collection**: View an infinite-scrolling grid of images fetched from the remote source.
3. **Inspect Items**: Click individual items to open the Preview Item Drawer for detailed metadata inspection.
4. **Persist Dataset**: 
   - Click "Persist Dataset" in the workspace header.
   - Select persistence scope: "Entire Collection" (import all remote items) or "Loaded Items Only" (import only what has been scrolled into view).
5. **Handoff**: Upon successful persistence, the platform creates a permanent Dataset and redirects the user to `/datasets/:id/classify` to begin work.

## Architecture

### Backend Components
- **`PreviewService`**: Orchestrates session lifecycle, pagination, and the handoff to persistence.
- **`PreviewStore`**: An in-memory, thread-safe store managing sessions with TTL-based eviction.
- **`UpstreamAdapter`**: An abstract base class defining the contract for remote data sources.
- **`MockUpstreamAdapter`**: A deterministic implementation for testing, serving 50 synthetic items.

### Frontend Components
- **`PreviewLaunchView`**: The entry form for starting new preview sessions.
- **`PreviewClassifyView`**: The main workspace providing the grid view and persistence controls.
- **`PreviewItemDrawer`**: A side panel for inspecting remote item metadata.
- **`usePreviewLoader`**: A Vue composable that handles cursor-based pagination logic.

## API Endpoints

| Method | Path | Request Shape | Response Shape |
|--------|------|---------------|----------------|
| `POST` | `/api/v1/preview-sessions` | `{ collection_ref: string }` | `PreviewSessionResponse` |
| `GET` | `/api/v1/preview-sessions/{id}` | - | `PreviewSessionResponse` |
| `GET` | `/api/v1/preview-sessions/{id}/items` | `?cursor=&limit=` | `PreviewItemsResponse` |
| `POST` | `/api/v1/preview-sessions/{id}/persist` | `{ scope: PreviewPersistScope }` | `PreviewPersistStatus` |
| `GET` | `/api/v1/preview-sessions/{id}/persist-status` | - | `PreviewPersistStatus` |

## Upstream Adapter Contract

To support new data sources, implement a class inheriting from `UpstreamAdapter`:

```python
class UpstreamAdapter(ABC):
    @abstractmethod
    async def resolve_collection(self, collection_ref: str) -> dict[str, Any]:
        """Verify the reference exists and return basic metadata."""
        ...

    @abstractmethod
    async def fetch_page(self, collection_ref: str, cursor: str | None, limit: int) -> PreviewPage:
        """Fetch a specific page of items from the remote source."""
        ...

    @abstractmethod
    async def estimate_total(self, collection_ref: str) -> int | None:
        """Provide an estimated count of total items in the collection."""
        ...
```

## Configuration

Preview behavior is governed by the following limits (configured in `PreviewStore`):
- **TTL**: 7200 seconds (2 hours) of inactivity before a session is evicted.
- **Max Sessions**: 200 concurrent sessions globally.
- **Session Cap**: 2000 items cached per session to prevent memory exhaustion.

## Limitations (v1)

- **Volatility**: Sessions are in-memory and do not survive backend restarts.
- **URL Expiry**: Does not currently support refreshing signed URLs for long-running sessions.
- **Synchronous Persist**: Persistence is handled as a single blocking operation; background task delegation is planned for v2.
