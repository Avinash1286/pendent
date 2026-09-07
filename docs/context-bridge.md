# AURA Context Pack and live context bridge

The device captures a thought; the companion turns it into a note; the portal lets its owner decide what becomes context for an AI conversation. The user's profile and instructions are distinct from captured notes. Captured speech is treated as source data, not as commands to an assistant.

## Portable context

A Context Pack contains a purpose, optional user profile/current goals, selected notes with capture dates, source references, and explicit uncertainty. Markdown is the universal interchange format. A user can copy the pack into any AI chat or attach the exported file. Opening an AI application's website does not itself inject or submit text there.

This works with interfaces such as ChatGPT, Claude, Gemini and Grok because the user supplies ordinary text or an attachment. Context windows, attachment support, account entitlements and provider retention policies vary. The portal must preview exactly what will be copied or shared. It must not silently send recordings or an entire note library to another provider.

## Live access

The portal backend is Convex; the frontend is Next.js. Device ingestion uses a separately revocable, owner-bound token. A live context endpoint returns only the scope the owner has enabled. MCP-capable clients can request fresh context while a conversation is in progress; provider-specific setup and support must be documented from the actual implemented endpoint. Standard web chat interfaces without a connector can use the portable pack instead.

Sync and transcription latency are real: saved audio must transfer and be processed before a new note can appear. “Live” means newly synced notes are queryable without rebuilding an exported file; it does not mean instantaneous transcription or access to an actively recording microphone.

## Required access boundaries

- Every database query and mutation derives its owner from authenticated identity.
- Device tokens are shown once, stored as hashes, scoped to ingestion, and revocable.
- Context access credentials are separate from ingestion credentials and read only.
- A Context Pack previews selected sources and includes no unselected private notes.
- Notes can be edited and deleted; exports already copied to another provider remain under that provider's controls.
- No share URL should place a long-lived secret in a public repository, analytics event or page referrer.

See the portal README and validation report for implemented routes and tested behavior. This document defines the intended contract while the Convex account provisioning step is pending.
