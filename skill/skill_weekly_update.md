# Skill: Weekly Update

## When to trigger
When the user says any of:
- "update weekly update"
- "push weekly update"
- "sync weekly update"
- "weekly update ล่าสุด"

## What this skill does

Updates `weekly update/budget management web.xlsx` with the latest task status and syncs it to SharePoint — merging with any tasks colleagues may have added directly on SharePoint.

## Algorithm (must follow in order)

### 1. Determine what changed this session
Read the conversation and identify any tasks that:
- Were completed (mark **Done**)
- Were started (mark **In Progress**)
- Are newly added (append as new row)
- Have updated remark/cutoff/PIC

Update the `ROWS` list in `setup/create_weekly_update.py` accordingly before running.

### 2. Run the script
```
python setup/create_weekly_update.py
```

The script will:
1. **Download** the current SharePoint file
2. **Read** all rows (including tasks added by Chatdanai, Ratima, or other colleagues)
3. **Merge** — upsert local ROWS by "Action" name; preserve unmatched colleague rows
4. **Save** merged file to `weekly update/budget management web.xlsx`
5. **Upload** merged file back to SharePoint (overwrite)

### 3. Report to user
After running, summarize:
- How many rows total
- Which colleague tasks were preserved
- Whether SharePoint upload succeeded or needs manual upload

## Key: Upsert rules
| Case | Result |
|------|--------|
| Action exists in both local ROWS and SharePoint | Local ROWS wins (overwrite) |
| Action only on SharePoint (colleague task) | Preserved as-is |
| Action only in local ROWS (new task) | Appended after SharePoint rows |

## Column order (A–G)
`Action type` | `Action` | `Remark` | `PIC` | `Cut-off` | `Status` | `Data source`

## Status values
- `Done` — green fill
- `In Progress` — orange fill

## Action types
- `Project Settings`
- `Data Pipeline`
- `Development`
- `Project Action`
