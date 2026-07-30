---
name: comprehension-check
description: Test understanding of the current phase by asking targeted questions from the django-learning-roadmap
---

## Purpose
Test understanding of the current phase by asking targeted questions from the django-learning-roadmap.md. This is the actual measure of progress in this learning project — not the number of checklist items ticked, but the ability to explain what you built and why.

## When to use
After completing a phase in the Django learning roadmap. Run this skill to answer the comprehension questions for that phase without looking them up. If you cannot answer one, stop and ask Claude Code to explain that specific piece before moving on.

## How it works

1. **Identify the phase.** Ask the user which phase they've just completed or are working on (e.g., "Phase 4: Schema design", "Phase 8: First vertical slice").

2. **Extract and present the questions.** Find the comprehension-check section in `django-learning-roadmap.md` for that phase. Present each question clearly, one at a time if the user prefers, or all at once if they want to batch them.

3. **Read their answers.** For each question, read their response carefully. The point is not to grade correctness harshly — the point is to catch gaps in understanding *now*, before those gaps compound into confused code later.

4. **Flag gaps gently.** If an answer is incomplete, vague, or shows misunderstanding, ask a follow-up question to probe deeper. Examples:
   - If they describe the *what* but not the *why*, ask "why does Django do it that way?"
   - If they conflate two concepts, ask them to draw the distinction.
   - If they gesture at something they clearly know but can't articulate, ask them to explain it to someone unfamiliar with Django.

5. **Point to resources if needed.** If a gap is real, ask them whether they want to re-read the relevant section from the roadmap's "Read first" list, or have Claude Code explain that specific topic. The roadmap always names the page and section to read.

6. **Do not continue if understanding is shaky.** The roadmap's own guidance: "If you cannot answer one, you accepted code you do not understand. Go back and ask Claude Code to explain that specific piece before moving on."

## Questions belong in the roadmap
If a question feels unanswered or if you think a comprehension check is missing for a phase, that's feedback for the roadmap author. Record it as a note but do not add questions to the skill itself — they live in `django-learning-roadmap.md`.

## Tone
Encouraging and direct. The user is learning intentionally. A gap now is a gift; it means they can fix it before it matters. Treat answers seriously and probe real gaps, but do not be pedantic about phrasing or completeness of explanation.
