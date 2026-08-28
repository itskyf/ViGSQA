# Kế hoạch cập nhật Repository

Đúng hướng nhất là **tách “luật làm việc” khỏi “trạng thái công việc”**.

Hiện repo `itskyf/ViGSQA` **chưa có `AGENTS.md`**. `AGENTS.md` nên là instruction ổn định cho mọi coding session, không chứa progress cụ thể. Đây cũng đúng với cách AGENTS.md được thiết kế: standing instructions về build/test/conventions/workflow; GitHub cũng coi nó là always-on agent instruction. ([Agents][1])

Mình khuyên cấu trúc:

```text
AGENTS.md
docs/
  PLAN.md                  # source of truth: kế hoạch tổng
  plans/
    T01-dataset-quality.md # working record của task đang/đã làm
    T02-notebook.md
    ...
```

Trong `AGENTS.md`, thêm **Planning protocol** kiểu này:

```md
## Planning workflow

- `docs/PLAN.md` is the authoritative project plan.
- Before starting work, read `docs/PLAN.md` and the active task's file under
  `docs/plans/`.
- Future tasks in `PLAN.md` describe goals and motivation only. Do not
  prematurely prescribe exact implementations, artifacts, metrics, or outputs
  unless they are already required by an external specification.
- Treat plans as living documents. Update them when experiments, tests, data,
  or investigation produce new evidence.

### During a task

- Work toward the task goal, not a preconceived implementation.
- Prefer root-cause investigation over workarounds.
- When unexpected behavior, suspicious results, or bugs appear:
  - record the finding;
  - investigate it when relevant to the goal;
  - revise the task's next steps based on evidence;
  - add follow-up tasks when the issue deserves separate work.
- Do not continue blindly just because an earlier plan expected a different
  result.

### Progress tracking

For every coding session:
1. Read the current plan, task notes, repository state, and relevant results.
2. Continue one selected task from `docs/PLAN.md`.
3. Record meaningful findings, decisions, validation performed, and unresolved
   questions in its task file.
4. Update `docs/PLAN.md` before ending the session:
   - current status;
   - concise progress;
   - important discoveries that affect later tasks;
   - next logical action.
5. Mark a task complete only when its goal is satisfied and relevant validation
   passes.

Valid statuses: `planned`, `in_progress`, `blocked`, `done`.

Do not erase useful history when plans change. Record why the direction changed.
Keep `PLAN.md` concise; detailed investigation belongs in the task file.
```

`docs/PLAN.md` thì **không nên là checklist implementation dài**. Chỉ cần dạng:

```md
# ViGSQA Project Plan

## Project goal
Build and evaluate a reproducible Vietnamese adaptation of GS-QA that satisfies
the course requirements and supports defensible experimental conclusions.

## Tasks

| ID | Goal | Status | Current state |
|---|---|---|---|
| T01 | Establish a trustworthy Vietnamese benchmark | in_progress | ... |
| T02 | Establish a reproducible end-to-end notebook workflow | planned | ... |
| T03 | Establish sound evaluation and baselines | planned | ... |
| T04 | Investigate improvements motivated by observed failures | planned | ... |
| T05 | Analyze Vietnamese-specific behavior and errors | planned | ... |
| T06 | Produce the final scientific report and reproducibility package | planned | ... |

## Cross-task discoveries
- ...
```

Còn mỗi `docs/plans/Txx-*.md` là **lab notebook của agent**:

```md
# T01 — Establish a trustworthy Vietnamese benchmark

## Goal
...

## Current understanding
...

## Findings
...

## Decisions
...

## Validation
...

## Open questions / anomalies
...

## Next
...
```

Điểm quan trọng nhất: **`Next` chỉ là bước hợp lý hiện tại, không phải contract**. Sau lần chạy sau, nếu phát hiện SQL sai, metric lạ, data leakage... agent được phép tiếp tục investigate và sửa plan thay vì cố hoàn thành output đã tưởng tượng từ trước.

Mỗi session bạn chỉ cần nói:

> `Continue T01 from docs/PLAN.md. Follow AGENTS.md and update the planning documents based on what you actually discover.`

Cách này tốt hơn một `TODO.md` cố định vì nó tạo vòng lặp **plan → execute → observe → revise plan → validate**, đồng thời session mới có đủ context để tiếp tục mà không phải bạn kể lại lịch sử. GitHub cũng khuyến nghị repository instructions phải nói rõ cách build/test/validate để agent có thể tự kiểm chứng thay đổi. ([GitHub Docs][2])

[1]: https://agents.md/index?utm_source=chatgpt.com "AGENTS.md"
[2]: https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results?utm_source=chatgpt.com "Best practices for using GitHub Copilot to work on tasks - GitHub Docs"
