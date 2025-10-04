# CompactVault: Technical Architecture

## 1. Core Philosophy

CompactVault is built on the principle of **simplicity and portability**. It operates as a single-file Python web server with a vanilla JavaScript frontend, requiring no external dependencies beyond a standard Python installation. This ensures it is lightweight, easy to run, and easy to understand.

## 2. Backend Architecture (server.py)

The backend is a multi-threaded HTTP server built using Python's standard `http.server` and `socketserver` libraries.

### Key Components:

-   **`ThreadedHTTPServer`**: A simple extension of `http.server.HTTPServer` that uses `ThreadingMixIn` to handle each incoming request in a separate thread, allowing the server to manage multiple concurrent connections.

-   **`RequestHandler`**: This is the core of the web server. It inherits from `BaseHTTPRequestHandler` and is responsible for:
    -   **Routing**: A simple regex-based router maps API endpoints (e.g., `/api/projects`, `/api/assets/{id}`) to their corresponding handler methods within the class.
    -   **Authentication**: Implements Basic Authentication to protect the vault. The password is read from the `COMPACTVAULT_PASSWORD` environment variable.
    -   **Request Handling**: Contains methods for handling GET, POST, and DELETE requests for all API endpoints.
    -   **Response Compression**: Compresses responses with Gzip where appropriate to reduce bandwidth.

-   **`CompactVaultManager`**: This class acts as the data and logic layer, abstracting all database operations away from the `RequestHandler`. It manages the SQLite connection, schema creation, and all business logic for creating, retrieving, and managing projects, collections, and assets.

## 3. Database Design (SQLite)

CompactVault uses a single SQLite file (`.vault`) as its database. It operates in **Write-Ahead Logging (WAL) mode** (`PRAGMA journal_mode = WAL;`), which provides higher concurrency by allowing readers to operate while data is being written.

### Schema:

-   `projects`: Stores project metadata.
-   `collections`: Stores collection metadata, with a `parent_id` to enable a nested, folder-like hierarchy.
-   `assets`: Contains metadata for each asset, including its type, format, and a JSON `manifest`.
-   `chunks`: This is the heart of the storage system. It stores unique, compressed data chunks.
-   `metadata`: A key-value table for storing additional asset information, such as the original filename.

### Chunk-Based Storage & Deduplication:

To save space and improve I/O, all assets are split into fixed-size chunks. 

1.  When a file is uploaded, it is broken into chunks.
2.  Each chunk is compressed using `zlib`.
3.  A `SHA-256` hash of the uncompressed chunk data is calculated.
4.  The compressed data is stored in the `chunks` table, indexed by its hash.

If a new file contains a chunk with a hash that already exists in the database, that chunk is not stored again. This provides **data deduplication** at the chunk level.

The `assets` table does not store the file itself, but rather a JSON `manifest` that contains an ordered list of the hashes of the chunks that constitute the file.

## 4. Frontend Architecture

The frontend is a single-page application (SPA) written entirely in **vanilla JavaScript (ES6+)**, with no frameworks or external libraries. The HTML, CSS, and JavaScript are all embedded as strings within the main `server.py` file and served as a single HTML document.

### Startup & Vault Selection

Upon starting, the server checks for the existence of `.vault` files:
-   **No Vaults Found:** If no vault files exist, the server automatically creates a `default.vault` and initializes a `CompactVaultManager` to use it. The main application UI is served immediately.
-   **Vaults Found:** If one or more `.vault` files are present, the `CompactVaultManager` is **not** immediately initialized. Instead, the server serves a special HTML page that acts as a vault selector. This page allows the user to either choose an existing vault or create a new one.

Only after a vault is selected (via the `/api/select_db` endpoint) is the `CompactVaultManager` instance created and associated with the server process. All subsequent API requests are then handled by this manager instance.

### Key Components:

-   **State Management:** A global `state` object holds the application's entire state.
-   **API Client:** A simple `api` helper function standardizes `fetch` requests to the backend.
-   **Virtual Rendering:** The asset list uses a virtual scrolling mechanism. Only the visible items in the list are rendered in the DOM, allowing the UI to remain fast and responsive even with thousands of assets.
-   **UI Logic:** The UI is dynamically rendered and updated by manipulating the DOM directly. The code is organized by feature (e.g., `loadProjects`, `renderVisibleAssets`).

## 5. Key Feature Implementations

-   **Chunked Uploads:** Large files are uploaded in chunks via separate POST requests. The server reassembles these chunks and processes them in a background thread, preventing the UI from freezing.

-   **Optimized Video Streaming:** The backend supports HTTP Range Requests. When a video is played, the browser can request specific byte ranges of the file. The server reads the asset's manifest, identifies which chunks contain the requested bytes, and streams only those chunks back to the client. This enables instant seeking without downloading the entire file.

-   **Graceful Shutdown:** The server listens for `SIGINT` (Ctrl+C) and `SIGTERM` signals. The `signal_handler` ensures that the database connection is properly checkpointed and closed before the process exits, which is crucial for cleaning up the SQLite WAL files.