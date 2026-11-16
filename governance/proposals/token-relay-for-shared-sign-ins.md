---
id: PROPOSAL-token-relay-for-shared-sign-ins
title: A token relay lets several brains share one rotating sign-in
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
rule_id: null
accepted_by: brain-owner
accepted_at: 2026-11-17T05:01:44+10:00
implemented_at: 2026-11-17T05:01:44+10:00
created: 2026-11-16T19:59:48+10:00
updated: 2026-11-17T05:01:44+10:00
target_files:
  - /shared/skills/manage-credentials/SKILL.md
---

# A token relay lets several brains share one rotating sign-in

Read `/CONTRACT.md` first. This proposal changes three bullets of the *Credential policy* in
`/shared/skills/manage-credentials/SKILL.md` and adds one. The policy came into the skill through
an accepted proposal, so its wording is changed only through another.

## Summary in plain language

Some providers hand out a new refresh token every time one is used, and the old one stops working.
The policy therefore allows one computer only to refresh such a sign-in. That makes one person's
computer the bottleneck as soon as colleagues' brains need the same company system.

Under this proposal several brains may refresh the same sign-in, provided they do it through the
**token relay**: an encrypted record of the current token in a private store all of them can
reach, with a short lease so that only one of them refreshes at a time. The store never holds the
key, the client secret or anything else that would let it act on its own. Without a relay, the
one-writer rule stands exactly as today.

A consequence the owner should see plainly: the encrypted token record is committed to a private
Git repository made only for it. The vault itself is still never committed.

## Current wording

*OAuth lifecycle*:

> - Allow only one active refresh writer for a credential set across all devices.

*Portability and concurrency*:

> - Do not commit the vault, merge divergent copies, or assume file synchronisation provides locking.
> - Use one active writer for each rotating OAuth credential set across devices.

## Proposed wording

*OAuth lifecycle*, the bullet replaced:

> - Allow only one active refresh writer for a credential set across all devices, unless the
>   entry is listed in the token relay's configuration. Brains that share a relayed entry refresh
>   only while holding the relay's lease, take the newest token from the relay before refreshing,
>   and write the new token back at once.

*Portability and concurrency*, the two bullets replaced and one added after them:

> - Do not commit the vault, merge divergent copies, or assume file synchronisation provides
>   locking. The token relay's record is not the vault: it is one rotating token bundle, encrypted
>   with the relay key, and may be committed only to the private store named in the relay's
>   configuration.
> - Use one active writer for each rotating OAuth credential set across devices, or the token
>   relay for an entry several brains share.
> - The relay store holds ciphertext only. The relay key and the provider's client secret live in
>   each brain's vault and reach another person only through a password manager, never through
>   chat, e-mail or a repository. When the relay cannot be reached and the local token is about
>   to expire, a brain refuses to refresh.

## Reason

An owner whose colleagues' brains need the same Xero and HighLevel sign-ins did not want his own
computer to be the place every refresh goes through. The alternatives were a server that holds
every working key, or copies of the token on several computers that lock each other out at the
first refresh. The relay avoids both: no computer is the bottleneck, and the shared store is
useless to anyone who takes it.

## Scope and consequences

- Only entries an owner lists in the relay's configuration. Every other entry, and every brain
  without a relay, behaves as before.
- Everyone who shares a relayed entry holds the client secret and a working token, so each has
  full access to that system. The relay suits trusted partners; it does not limit what a person
  may do.
- Removing a person: take away their access to the store, then refresh once. Their copy of the
  refresh token stops working; an access token they still hold runs until it expires.

## Risks and migration

- **A brain crashes between the provider's answer and the write-back.** The new token is written
  to the local vault first and pushed at the next use; until then other brains wait for the lease
  to run out and may have to re-authorise if the provider no longer accepts the old token.
- **A person who leaves in bad faith** can refresh before being removed and lock the others out.
  The remedy is then a new client secret and a new authorisation.
- **Ciphertext history stays in the store.** Old refresh tokens in it are already spent; old
  access tokens have expired. The relay key is replaced when someone who held it leaves.
- No migration: the relay is off until an owner creates the store, the key and the configuration.

## Rollback

Remove the configuration file: every entry returns to one writer. Revert the commit that applies
this wording.

## Validation

- The repository preflight passes on the mechanics.
- The relay's tests pass, including the test that an entry not listed behaves exactly as before.

## Acceptance

The owner accepts or declines `PROPOSAL-token-relay-for-shared-sign-ins` as one answer. On
acceptance the exact wording above is applied, and the acceptance is recorded in the memory's
governance proposals.

## Implementation

Accepted by the owner on 17 November 2026 ("Accept", answering the one acceptance question that
named this proposal, asked after its full wording was shown) and applied the same morning, exactly
as worded above, to the *Credential policy* of `/shared/skills/manage-credentials/SKILL.md`. The
policy carries no rule number, so `rule_id` stays empty. The relay stays off until an owner creates
the store, the key and the configuration.
