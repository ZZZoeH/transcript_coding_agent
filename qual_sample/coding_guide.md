# Qualification outcome coding guide (both coders use this)

Labels: 1 matches_profile / 2 mismatch_call_continues / 3 call_terminates

Principle: code 1 only when there is evidence of a fit
(the stated criterion is met, or the caller moves on). No evidence -> 3.

## What counts as the qualification exchange
- C. Only the part before the first transfer. Ignore everything after it
     (new agent's questions, failed transfer, odd remarks).
- B. Several questions: look at the last question before the transfer and what happens after it.

## How to decide
1. Caller reacts to the answer -> code by the reaction.
   - moves on (next question, pitch, transfer, "you qualify") and the answer fits -> 1
   - moves on although the answer does not fit -> 2
   - says the callee doesn't qualify and ends the call -> 3
2. No caller reaction (transcript ends on the callee's answer):
   - A. answer fits the stated criterion -> 1, doesn't fit -> 3
     (About 86% of transcripts end on the callee's turn, so "the call ended" alone tells us nothing.)
   - E. criterion not stated -> 3

## Edge cases
- D. Criterion not stated, but the caller moves on -> 1.
- E+. A criterion counts as stated if it follows directly from the offer or the question in the transcript
      (auto insurance -> owns a car; "want to learn more?" -> interested).
      Facts from outside the transcript (e.g. marketplace age limits) don't count.
- F. Caller asks "is this correct?" about several criteria at once and the callee says yes -> fits.
- I. Callee never answers: caller moves on anyway -> 1 (D); otherwise -> 3.
- G. Read obvious speech-to-text errors by context ("part a and vivo" = "part A and B").
- H. If a caller turn looks split (the callee answers before the question appears),
     read the two caller turns as one. Never edit the transcript.
