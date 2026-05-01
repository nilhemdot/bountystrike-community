"""sandbox-mcp — sandboxed PoC execution for the exploit + validator agents.

Driver hierarchy:

  Driver protocol (drivers/protocol.py)
    │
    ├── LocalSubprocessDriver   — DEV-ONLY. No isolation; refuses to run
    │                             unless BS_SANDBOX_DEV_MODE=1 AND the
    │                             scope JWT carries dev_mode_sandbox=true.
    │                             Used for unit tests and local replay
    │                             of validated PoCs only.
    │
    ├── DockerDriver            — Container isolation + iptables egress
    │                             filter. GAP-deploy: requires host
    │                             iptables wrapper service to install
    │                             egress rules tagged by container ID.
    │
    └── FirecrackerDriver       — Production target. Microvm boot in
                                  ~150ms, fresh kernel per run, no shared
                                  filesystem. Build deferred to a separate
                                  hardening task (build-plan §6.5).
"""
