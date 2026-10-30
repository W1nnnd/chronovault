# Privacy and approval

Linked from [SKILL.md](../SKILL.md).

## Read-only source folders

- Scan only `authorized_folders` named by the user for this run.
- Original files are never moved, renamed, edited or deleted.
- After the run, the Skill reports that source files were left unchanged.

## No external calls

- Use only registered UGOS experts and on-device models.
- No cloud API, no API key and no telemetry.

## Masking

- Mask account numbers and long policy numbers to the last four characters in the digest (for example `****0452`).
- Serial numbers that identify a product may be shown in full when they appear on a warranty or receipt.

## Approval gates

| Action | Gate |
| :--- | :--- |
| Show digest in chat | None (read-only result) |
| Save digest via `ug-knowledge save-text` | `waiting_approval` |
| Add tags via `ug-filemgr tag-add-file` | User opted in (`apply_tags`) and `waiting_approval` |

If approval is denied, keep the chat digest and do not retry the write or the tagging.
