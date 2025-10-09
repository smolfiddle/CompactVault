# CompactVault

CompactVault is a lightweight and efficient local asset manager that runs as a self-contained web server. It is designed for developers, designers, and hobbyists who need a simple tool to organize, view, and manage digital assets like images, videos, and documents.

![CompactVault Screenshot](https://imgur.com/a/o4ZnKXK) <!-- Replace with a real screenshot URL later -->

## Features

- **Zero Dependencies:** Runs anywhere Python is installed.
- **Web Interface:** Modern, responsive UI with drag-and-drop uploading and readable, wrapping filenames.
- **Intelligent Sorting:** Assets are automatically sorted using a natural sort order (e.g., "Episode 2" comes after "Episode 1").
- **Expanded Previews:** Preview common text files (including code), images, audio, and video directly in the browser.
- **Chunk-Based Storage:** Saves space with file deduplication and allows for efficient streaming.
- **Video Streaming:** Optimized for streaming video content with HTTP Range Requests.
- **Multi-Vault Support:** Manage multiple, separate asset databases.
- **Secure:** Protect your vault with a password.

## Getting Started

1.  **Run the Server:**
    ```bash
    python3 server.py
    ```
    The application will open automatically in your web browser.

2.  **Select or Create a Vault:**
    - If no `.vault` files are found in the directory, a new one named `default.vault` will be created for you.
    - If one or more `.vault` files exist, you will be prompted to select one or create a new one.

3.  **Set a Password (Recommended):**
    Run the server with the `COMPACTVAULT_PASSWORD` environment variable.
    ```bash
    COMPACTVAULT_PASSWORD="your-secret-password" python3 server.py
    ```
    If no password is set, it defaults to `password`.

## How to Use

- **Projects & Collections:** Organize your files into a nested structure of projects and collections.
- **Upload Assets:** Drag and drop files and folders directly into the "Assets" panel or use the "Upload" button.
- **Preview:** Select an asset to see a preview. Text, images, audio, and video are supported.
- **Download:** Download individual assets, or entire collections and projects as `.zip` files.
