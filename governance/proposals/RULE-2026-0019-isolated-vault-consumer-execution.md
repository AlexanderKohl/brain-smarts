---
id: RULE-2026-0019
title: OS-isolated vault execution for registered scripts and OAuth
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: accepted
proposal_id: RULE-2026-0019
owner: brain-owner
created: 2026-08-12T07:49:07+10:00
updated: 2026-08-12T07:59:36+10:00
accepted_by: brain-owner
accepted_at: 2026-08-12T07:59:36+10:00
implemented_at: null
previous_contract_version: 0.6.0
new_contract_version: 0.6.0
target_files:
  - /memory/projects/credential-management/RULES.md
project_refs:
  - /memory/projects/credential-management
  - /memory/projects/brain-development
---

# RULE-2026-0019: OS-isolated vault execution for registered scripts and OAuth

## Current problem

The current per-login Vault Agent runs under the same interactive Windows
identity as Cursor and Claude. Its broker supports `get_fields`, `get_json`,
`get_access_token`, `set_text` and arbitrary `vaultctl run --map ... --
<command>` operations. A same-user AI process can therefore request a raw
secret or choose a command that prints an injected secret.

Codex runs under a separate sandbox account (`<MACHINE>\CodexSandboxOffline`), while Git Credential
Manager and the tray vault run under the owner's interactive Windows identity. This is why
Cursor and Claude can use the current Windows Credential Manager Git session
but Codex receives `SEC_E_NO_CREDENTIALS`. Relaxing the ACL on
`agent-state.json` would be unsafe: that file contains the global broker
authentication key and token, which currently authorize access to every vault
entry and mutation operation.

The owner requires one consistent model for all agents and tools:

1. agents may request credential-backed work but never receive credential
   values;
2. any script may become eligible to use vault credentials after explicit
   enrollment, but an arbitrary or changed script may not receive them;
3. the unlocked tray vault should service registered scripts consistently
   across interactive and sandboxed agents; and
4. new OAuth connections, interactive reauthorization, or expansion of OAuth
   scope, target or consumers must require the recovery passphrase through a
   trusted prompt.

## Security interpretation of “any script”

It is impossible to guarantee that an AI cannot obtain a secret if the AI can
choose or modify arbitrary code that receives the secret: that code could print,
encode, transmit or save it. “Any script” therefore means any script that the
owner has explicitly enrolled through the tray after reviewing its consumer
manifest. Enrollment binds the approved executable code and exact credential
capabilities. Any material code or manifest change invalidates the grant and
requires re-enrollment.

## Current wording

`/projects/credential-management/RULES.md` currently includes:

```markdown
- Inject static credentials only into the environment of an authorised short-lived child process when that process cannot use the Vault Agent broker, and do not persist that environment. Do not place the vault recovery passphrase or vault encryption key in any child environment.
- Prefer the per-login Vault Agent as the runtime unlock holder: the owner unlocks once after Windows login (or after agent restart / explicit lock) through a hidden prompt; the agent retains the derived vault key in its own memory only; authorised consumers obtain scoped results (normally short-lived OAuth access tokens or explicitly mapped static fields) through the local broker without a chat-long credential-aware shell.
- Treat `vault_credentials.py session` as deprecated emergency compatibility only. Do not use it as the default operating model for new work or agentic shells.
```

The current rules do not distinguish an AI-facing request interface from a
secret-bearing internal interface, do not require OS identity isolation from
same-user AI applications, and do not define cryptographic enrollment of
credential-consuming code.

## Proposed wording or exact diff

### 1. Replace the three runtime-delivery bullets under “Storage policy”

```diff
-- Inject static credentials only into the environment of an authorised short-lived child process when that process cannot use the Vault Agent broker, and do not persist that environment. Do not place the vault recovery passphrase or vault encryption key in any child environment.
-- Prefer the per-login Vault Agent as the runtime unlock holder: the owner unlocks once after Windows login (or after agent restart / explicit lock) through a hidden prompt; the agent retains the derived vault key in its own memory only; authorised consumers obtain scoped results (normally short-lived OAuth access tokens or explicitly mapped static fields) through the local broker without a chat-long credential-aware shell.
-- Treat `vault_credentials.py session` as deprecated emergency compatibility only. Do not use it as the default operating model for new work or agentic shells.
+- Treat every AI agent, agent shell, model process and agent-controlled parent process as untrusted for secret disclosure. An AI-facing process must never receive, read, print, persist or be able to request a raw credential value, OAuth token payload, vault recovery passphrase, derived encryption key, general broker authentication material or secret-bearing child environment.
+- Run the unlocked vault runtime and every secret-bearing consumer under an operating-system security identity and ACL boundary that is not shared with AI applications. The interactive tray is a trusted user interface and status client; it must not expose decrypted vault state or a general secret broker capability to same-user AI processes.
+- Give all agents and tools the same non-secret request interface. The public interface may report lock state, list non-secret consumer aliases, request execution of a registered consumer, request an OAuth enrollment or reauthorization flow, and return redacted operation status. It must not expose `get_fields`, `get_json`, `get_access_token`, arbitrary `set_text`/`set_json`, caller-selected environment mappings, caller-selected executables or a general-purpose secret-return operation.
+- Permit a script or executable to consume credentials only through an encrypted owner-approved consumer grant. Enrollment requires recovery-passphrase reauthentication in the trusted tray and binds a stable consumer alias to its canonical executable/interpreter identity, command template, allowed arguments, working and output locations, credential entry and fields, permitted operation or remote targets, and SHA-256 hashes for the entry point and every mutable local executable dependency declared by its consumer manifest.
+- Treat the encrypted consumer grant as authoritative. A repository registry may mirror aliases, hashes and lifecycle metadata for audit, but an AI-editable repository file must never grant credential access by itself. Any mismatch in path, executable identity, command template, dependency closure, manifest or approved hash invalidates execution and requires owner re-enrollment with the recovery passphrase.
+- The isolated vault runtime, not the requesting agent, launches registered consumers. Deliver only the fields approved for that consumer through a short-lived child environment, anonymous pipe or standard input; never use command arguments, remote URLs, persistent environment variables or plaintext files. Remove the values before launching descendants where practical, capture output, redact exact secret values defensively, and destroy transient delivery material when the consumer exits.
+- Do not describe arbitrary scripts as safe merely because output redaction exists. Redaction cannot prevent a malicious consumer from transforming or transmitting a secret; the reviewed and hash-bound consumer manifest is the primary trust boundary.
+- Retire agent-accessible raw-secret commands and arbitrary mapped-command execution, including `vaultctl access-token`, public broker `get_fields`/`get_json`/`get_access_token`, and `vaultctl run --map ... -- <caller-selected command>`. Keep any secret-returning primitive private to the isolated runtime and one-time capability of an already validated registered consumer.
+- Keep `vault_credentials.py session` as disabled legacy compatibility rather than an agent workflow. It must not be available to AI-controlled processes or export the recovery passphrase, vault key or credential values into an agent-accessible shell.
```

### 2. Add under “Vault structure”

```diff
+- Store owner-approved consumer grants and OAuth authorization grants inside the authenticated encrypted vault, separate from credential values but covered by the same atomic authenticated snapshot. A grant must include its schema version, consumer alias, code-manifest digest, credential capabilities, allowed targets, approval time and revocation state.
+- Use a one-time, consumer-scoped runtime capability for each launch. It may authorize only the registered consumer and approved fields for that launch, expires when the process exits or after a short timeout, and must never be reusable as a general vault capability.
```

### 3. Add under “Passphrase and encryption”

```diff
+- Require recovery-passphrase reauthentication through the trusted tray before creating or replacing a credential set, enrolling or changing a consumer, creating a new OAuth connection, interactively reauthorizing an OAuth connection, changing an OAuth client, or expanding approved OAuth scopes, accounts, tenants, organisations, repositories, locations, targets or consumers. An already-unlocked state alone is insufficient for these changes.
+- Before the passphrase prompt, display the non-secret proposed change: provider, account or installation identity, requested scopes, allowed targets, consumer alias and manifest digest. Apply the change only after successful reauthentication and explicit confirmation in the trusted tray.
```

### 4. Add under “OAuth lifecycle”

```diff
+- Run OAuth authorization-code exchange, token storage and refresh only inside the isolated runtime or a registered connector launched by it. The requesting AI receives authorization URLs and redacted status only; it never receives authorization codes, access tokens, refresh tokens or complete token records.
+- Require trusted-tray passphrase reauthentication for a new OAuth connection, interactive reauthorization, client replacement, or expansion of scopes, resource targets or consumers. Permit routine refresh without another prompt only while the vault is unlocked, the refresh stays within the existing encrypted grant, and the designated single refresh writer atomically replaces the complete token record.
+- A connector update that changes executable code, local executable dependencies, redirect handling, requested scopes, token endpoint, target coverage or secret-delivery requirements invalidates its consumer grant and requires owner review and passphrase-backed re-enrollment before credentials are released.
```

### 5. Replace the per-login runtime bullets under “Portability and concurrency”

```diff
-- Do not enable unattended vault unlock after reboot without a separately accepted runtime design (for example a future TPM/device-bound key slot). Per-login interactive unlock into the Vault Agent is the approved workstation model.
-- Do not substitute a plaintext `.env` passphrase for interactive unlock.
-- Before prompting for the recovery passphrase, check whether the Vault Agent is already unlocked for this Windows login. If it is unlocked, reuse it for further credential operations; do not prompt again and do not start a second agent instance.
-- Keep the vault file data lock short-lived around each authenticated read or write. Do not treat `credentials.vault.lock` as a session lease. Use a distinct agent singleton / session lease so only one Vault Agent instance holds the unlock key, while OAuth token refresh can still serialise per entry without blocking unrelated vault maintenance incorrectly.
-- Do not create parallel unlocked agents or parallel processes that each hold the recovery passphrase.
+- Do not enable unattended vault unlock after reboot without a separately accepted device-bound design. The owner unlocks the isolated runtime once per login or service restart by entering the recovery passphrase into the trusted tray; the tray transfers it only to the authenticated isolated runtime and must not persist it.
+- Do not substitute a plaintext `.env`, command argument, file, agent message or general IPC capability for interactive unlock or passphrase-backed approval.
+- Before prompting to unlock, check the isolated runtime's non-secret status. Reuse one unlocked runtime for every agent and tool; do not start per-agent vault instances or give an AI process its own unlocked vault.
+- Keep the vault file data lock short-lived around each authenticated read or write. Use one isolated runtime as the unlock holder and one active refresh writer per rotating credential set; serialise per-entry writes without blocking unrelated registered consumers.
+- On Windows, run the secret-bearing runtime under a dedicated least-privilege service identity that owns the vault and private broker state. Expose a separately ACL-restricted, non-secret request endpoint to approved local agent identities. On other platforms, use the equivalent dedicated daemon identity and local IPC permissions.
```

## Reason

This design gives Cursor, Claude, Codex and other tools one consistent way to
request credential-backed operations while making the OS-isolated runtime–not
the AI process–the only component that can decrypt and deliver secrets. It also
makes script eligibility explicit and revocable, and requires the owner to
re-enter the recovery passphrase whenever OAuth authority or credential
consumer authority is created or expanded.

## Scope and behavioural consequences

- Applies to every credential set and every AI/tool consumer of the Portable AI
  Brain vault.
- Replaces the current same-user, general-purpose secret broker with two trust
  planes: a public non-secret request plane and a private secret execution
  plane.
- All agents use the same public client regardless of Windows identity or
  sandbox.
- Any script can be proposed for enrollment, but no arbitrary or modified code
  receives credentials without passphrase-backed owner approval.
- Existing Xero, HighLevel, Google Workspace, ABR and future Git/GitHub
  consumers must be migrated to registered manifests before using the new
  service.
- Git push becomes a registered operation that returns commit/ref status only;
  the Git credential remains inside the isolated service boundary.
- Routine OAuth refresh remains automatic while unlocked and within the
  approved grant. New authorization, interactive reauthorization and authority
  expansion require the recovery passphrase.
- No `contract_version` change is proposed because this is node-scoped
  credential governance; effective contract version remains `0.5.0`. If a
  separately proposed contract change becomes active first, this proposal will
  preserve that then-current version.

## Risks and conflicts

- This is intentionally breaking for the current agent-accessible `get_fields`,
  `access-token`, `secret-put`, `get_json` and arbitrary `run --map` workflows.
- A dedicated Windows service identity and authenticated cross-identity IPC
  require an administrator-assisted installation and ACL migration.
- Existing connectors will stop receiving credentials until their manifests
  are enrolled. Migration must therefore support a controlled cutover and
  rollback.
- A registered consumer necessarily receives its approved secret. If that
  trusted consumer is malicious or compromised it can exfiltrate the secret;
  code/dependency hashing, least privilege, target restrictions and owner
  enrollment reduce this risk but cannot make arbitrary code safe.
- Hashing an entry script alone is insufficient when it imports mutable local
  code. Consumer manifests must cover the mutable executable dependency closure
  or use an immutable packaged environment.
- Output redaction is defense in depth only and must not be treated as the
  authorization boundary.
- The tray UI still runs in the interactive user session. Sensitive changes
  require the recovery passphrase so another same-user process cannot authorize
  expansion merely by calling the public endpoint.
- Repository code and non-secret manifests remain portable, but the service
  identity, IPC ACL and installation are host-specific runtime state.

## Migration and implementation plan

1. Build tests before cutover for denial of raw-secret access, arbitrary-command
   denial, code/dependency hash invalidation, one-time launch capabilities,
   locked-vault behavior, passphrase-backed enrollment, OAuth scope expansion,
   output redaction, cross-identity requests and Git push without token
   disclosure.
2. Introduce a versioned consumer-manifest schema and a policy engine that
   validates canonical paths, command templates, executable/dependency hashes,
   credential fields, allowed arguments, targets and outputs.
3. Store authoritative grants encrypted in `credentials.vault`; add non-secret
   mirror metadata to `credential-registry.json` for audit only.
4. Split the broker into a private service interface and an ACL-restricted
   public request interface. Remove raw-secret and arbitrary-command operations
   from the public client.
5. Convert `vault_tray.py` into a trusted UI/status client for the isolated
   service. Add passphrase-backed dialogs for unlock, credential entry,
   consumer enrollment, OAuth authorization/reauthorization and authority
   expansion.
6. Add a dedicated least-privilege Windows service identity and installer.
   Migrate vault and private state ACLs to that identity; grant agent identities
   access only to the public request endpoint.
7. Add a common non-secret `vault_request.py` client used identically by Cursor,
   Claude, Codex and ordinary tools.
8. Migrate existing connectors to registered consumer manifests and private
   one-time capabilities. Disable the legacy agent-accessible secret-return and
   mapped-command interfaces only after required consumers pass integration
   tests.
9. Add a registered Git push consumer. Prefer a repository-scoped GitHub App
   with one-hour installation tokens for durable automation; allow a
   fine-grained PAT as a transitional credential. The service must enforce
   registered remotes, exact refs, expected commit IDs, fast-forward-only pushes
   and no force/delete operations.
10. Exercise new OAuth enrollment and scope-expansion flows with non-production
    test credentials before migrating live entries. The owner enters all secret
    values and recovery passphrases only through trusted tray prompts.
11. Update `SKILL.md`, registry, state, knowledge and logs; run the full credential
    test suite and repository preflight; commit each successful logical
    checkpoint under `RULE-2026-0017`.

## Rollback

1. Stop the isolated service and restore the pre-migration vault backup while
   closed.
2. Restore the prior per-login tray/agent code and ACLs.
3. Revert the implementation commits and active credential-rule change.
4. Revoke any GitHub App installation or PAT introduced only for this design.
5. Re-enroll or reauthorize connectors whose provider tokens were rotated
   during testing.
6. Never copy decrypted secrets or consumer grants into repository files during
   rollback.

## Validation

- Protected-governance preflight recognises this accepted proposal before the
  credential `RULES.md` change.
- Unit and integration tests prove public callers cannot obtain raw fields,
  tokens, broker keys or arbitrary environment mappings.
- Tests prove unregistered, modified or dependency-mismatched consumers fail
  closed and that enrollment/expansion fails without passphrase
  reauthentication.
- Cross-identity tests show Cursor, Claude and Codex use the same non-secret
  request client while the secret-bearing runtime remains inaccessible to their
  OS identities.
- OAuth tests prove initial authorization, interactive reauthorization and
  scope/target/consumer expansion require passphrase-backed confirmation, while
  in-grant refresh remains atomic and prompt-free when unlocked.
- Git tests prove successful repository-scoped push without credential output,
  and rejection of wrong repository, remote, ref, SHA, non-fast-forward,
  force-push and deletion requests.
- Secret canary tests inspect stdout, stderr, logs, command lines, environment
  snapshots, temporary files and repository diffs for leakage.
- Full repository preflight result and any unrelated pre-existing failures are
  recorded accurately.

## Acceptance

Presented to the owner for explicit acceptance on 2026-08-12. The owner explicitly
accepted the proposal exactly as written on 2026-08-12.

Direct acceptance question: **Do you accept `RULE-2026-0019` exactly as
written, including the breaking retirement of agent-accessible raw-secret and
arbitrary mapped-command interfaces, the dedicated OS-isolated credential
service, passphrase-backed script enrollment, and passphrase-backed new or
expanded OAuth authority?**

## Implementation record

Accepted but not yet implemented. Current credential runtime remains active
until the controlled tested migration reaches cutover.
