# CompactVault: Technical Architecture

## 1. Core Philosophy: The WORM Archive

CompactVault is architected as a **local-first, permanent asset archive**. Its design is fundamentally based on the **WORM (Write Once, Read Many)** principle. Every technical decision is made to support the goal of creating a secure, immutable, and reliable long-term storage system for digital assets.

-   **Portability & Simplicity:** It runs as a single-file Python server with an embedded vanilla JavaScript frontend, requiring no external dependencies. This ensures maximum portability and ease of use.
-   **Data Integrity:** The primary goal is to ensure that once an asset is stored, it cannot be accidentally altered or corrupted.
-   **Local-First:** All data is stored and managed on the user's local machine, guaranteeing privacy and control.

## 2. Backend Architecture (server.py)

The backend is a multi-threaded HTTP server built using Python's standard `http.server` and `socketserver` libraries.

-   **`ThreadedHTTPServer`**: Handles each incoming request in a separate thread to manage concurrent connections.
-   **`RequestHandler`**: The core of the web server, responsible for:
    -   **Routing**: A regex-based router maps API endpoints (e.g., `/api/projects`) to handler methods.
    -   **Authentication**: Implements Basic Authentication via the `COMPACTVAULT_PASSWORD` environment variable.
    -   **Rate Limiting**: A per-IP rate limiter prevents abuse while allowing legitimate bursts of requests during uploads.
-   **`CompactVaultManager`**: The data and logic layer that abstracts all database operations. It is the sole component responsible for enforcing the WORM model.

## 3. Storage Layer: The Immutable Vault

CompactVault uses a single SQLite file (`.vault`) as its database. The storage architecture is the heart of the WORM implementation.

### WORM (Write Once, Read Many) Model

The `CompactVaultManager` provides methods for adding and reading data, but **intentionally lacks methods for editing or deleting assets**. The API exposed by the `RequestHandler` reflects this; there are no `PUT`, `PATCH`, or `DELETE` endpoints for assets. This architectural constraint is the primary mechanism for ensuring the permanence of the archive.

### Chunk-Based Storage & Data Integrity

To guarantee integrity and save space, all assets are chunked and hashed:

1.  When a file is uploaded, it is broken into chunks.
2.  A `SHA-256` hash of each chunk's data is calculated.
3.  The chunk is compressed and stored in the `chunks` table, indexed by its hash.

This system provides two key benefits for a permanent archive:
-   **Data Deduplication:** If multiple files contain the same chunk, it is only stored once.
-   **Verifiability:** The asset's `manifest` (a list of chunk hashes) acts as a checksum for the entire file. This allows for future integrity checks to verify that the asset data has not degraded or been tampered with at the storage level.

### Database & WAL Mode

The database runs in **Write-Ahead Logging (WAL) mode** (`PRAGMA journal_mode = WAL;`), which provides high-performance reads and writes. A graceful shutdown mechanism (`signal_handler` for Ctrl+C) is implemented to run a database checkpoint, which commits all changes from the `.wal` log file into the main database and ensures the temporary files are cleanly removed.

## 4. Frontend Architecture

The frontend is a dependency-free, single-page application (SPA) written in vanilla JavaScript (ES6+). The HTML, CSS, and JavaScript are embedded as strings within `server.py`.

-   **Virtual Rendering:** The asset list uses virtual scrolling, rendering only the visible items in the DOM. This ensures the UI remains fast and responsive even with thousands of assets.
-   **Backend-Driven Logic:** The frontend is designed to be a "dumb" client. It is primarily responsible for rendering the data provided by the backend. Crucial logic, such as sorting, is handled entirely by the backend to ensure consistency.

## 5. Key Data Flows

### Asset Ingestion (Write Once)

1.  A file is dropped onto the UI.
2.  The frontend JavaScript reads the file and sends it in small chunks to the `/api/upload/chunk` endpoint.
3.  Once all chunks are sent, the frontend calls `/api/upload/complete`.
4.  The backend places a task in a queue to process the asset in a background thread.
5.  The `CompactVaultManager` worker processes the chunks, creates a `manifest` (the ordered list of hashes), and inserts the final, immutable asset record into the database.

### Asset Retrieval (Read Many)

1.  The user navigates to a collection.
2.  The frontend requests assets from `/api/collections/{id}/assets`.
3.  The backend fetches all asset records for that collection, sorts them using a **natural sort algorithm** in memory, and returns only the paginated slice requested by the client.
4.  For previews or downloads, the backend reads the asset's manifest and streams the constituent data chunks from the database in the correct order.
