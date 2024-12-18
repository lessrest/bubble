# Actor Identity in Node.Town

This document explores approaches to actor identity in [[Node.Town]], focusing
on how we might combine [[Decentralized Identity]],
[[Verifiable Credential]]s, and [[ActivityPub]].

## Core Concept

We're considering a hybrid identity system where:

1. Users can bring their own identifiers (sovereign identity)
2. System actors use predictable, host-controlled identifiers
3. Verifiable Credentials connect actors to servers

## Identity Types

### User Identities

Users could authenticate using their own DIDs:

- `did:dns:users-domain.com` (domain-based)
- `did:web:users-website.com` (website-based)
- `did:key:z6Mk...` (self-generated keypair)

This follows similar approaches to Bluesky, giving users sovereignty over
their identity while allowing proof through existing domain ownership.

### System Actors

System components (bots, services, etc.) would use path-based `did:web`
identifiers under the host's control:

- `did:web:node.town:system:moderation`
- `did:web:node.town:bot:welcome`

These resolve to predictable paths:

- `https://node.town/system/moderation/did.json`
- `https://node.town/bot/welcome/did.json`

## Server-Actor Relationships

Verifiable Credentials connect actors to their servers:

1. Actor maintains their base identity (e.g., `did:key` or `did:dns`)
2. Server (`did:web:node.town`) issues credentials that:
   - Confirm the actor's membership
   - Specify their server endpoints
   - Define their capabilities

This enables:

- Identity portability between servers
- Server-based trust networks
- Clear capability management
- Multiple server relationships

## ActivityPub Integration

The system needs to bridge DIDs with ActivityPub:

- Map DIDs to ActivityPub URLs
- Use DID public keys for ActivityPub signatures
- Handle credential verification during federation

## Open Questions

1. **Security**

   - Credential revocation process
   - Key rotation and recovery
   - Prevention of credential spoofing

2. **Federation**

   - Cross-server credential verification
   - Performance implications
   - Compatibility with existing AP servers

3. **User Experience**
   - Making sovereign identity accessible
   - Balancing security and usability
   - Recovery procedures

## Related

- [[ActivityPub]]
- [[Authentication]]
- [[User Identity]]
