# LINE With Pictures Portable Kit

This kit contains Git-tracked source, the external `Material/行動力` image
library, the material catalog, and SHA-256 checksums. It deliberately excludes
credentials, `.env`, Edge profiles, browser state, logs, response evidence,
snapshots, and customer exports.

On the second Windows PC:

1. Copy the complete kit from USB to a local directory.
2. Open PowerShell in the kit directory.
3. Run `.\setup_second_pc.ps1`.
4. Supply Google credentials separately and share the workbook with that
   service account when Sheets access is required.
5. Install and sign in to the LINE Edge extension through the normal project
   login workflow.
6. Run `source\.venv\Scripts\python.exe doctor_second_pc.py` from the kit root
   whenever the material library or setup needs verification.

Dependency installation can require internet access. The response watcher
remains disabled until `LINE_RESPONSE_WATCHER_ENABLED=true` is set explicitly.
