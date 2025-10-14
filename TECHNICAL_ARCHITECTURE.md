# Technical Architecture

This document outlines the core technical decisions and architecture of the CompactVault system.

## Hashing Algorithm

The system utilizes the **BLAKE2b** hashing algorithm for all data chunk and manifest integrity checks.

BLAKE2b was chosen over the previous SHA256 implementation for its significant performance advantages (it is generally faster than SHA256 on modern 64-bit platforms) while providing an equivalent, high level of security.

This change was implemented as a **breaking change**. Any database created with a previous version of the software is incompatible and must be recreated.

## Password Hashing

Each `.vault` file is protected by a password. The password is not stored directly. Instead, it is hashed using **PBKDF2-HMAC-SHA256** with a unique salt for each vault. The salt is stored in the `vault_properties` table along with the hash. This makes the password storage secure against rainbow table and pre-computation attacks.

## Database Schema & Performance

The database schema is designed for efficient storage and retrieval of chunked assets. To enhance performance, the following optimizations have been made:

*   **`vault_properties` Table:** A dedicated table for storing vault-specific metadata, such as the password hash and salt.
*   **Write-Ahead Logging (WAL):** The database operates in WAL mode to improve concurrency and write performance.
*   **Filename Sort Index:** A dedicated database index has been created on the `value` column of the `metadata` table. This index specifically accelerates the natural sorting of assets by their filename, which is the default view in the application.
*   **Manual `VACUUM`:** The application provides a UI button to trigger the `VACUUM` command. This allows the user to manually reclaim unused space and optimize the database file.