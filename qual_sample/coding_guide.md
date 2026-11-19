# Qualification outcome coding guide (both coders use this)

Labels: 1 matches_profile / 2 mismatch_call_continues / 3 call_terminates

One-line rule: if the caller reacts to the answer, code by the reaction;
if the transcript just ends on the answer, code by whether the answer fits.

- A. Transcript ends right after the callee's answer (no caller reaction):
     answer fits -> 1, answer doesn't fit -> 3.
     (About 86% of transcripts end on the callee's turn, so "the call ended" alone tells us nothing.)
- B. Several questions: look at the last question and what happens after it.
- C. Ignore what happens after qualification (e.g. a failed transfer).
- D. Criterion not stated, but the caller moves on -> 1.
- E. Criterion not stated and no caller reaction -> 3.
     (Code matches_profile only when there is evidence: the stated criterion is met, or the caller moves on.)
