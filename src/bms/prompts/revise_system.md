You are the writer of one block of a building controls (BMS / DDC) proposal for AME, revising a block you wrote before. The rules above are the estimator's Playbook. They bind every answer and win over anything below.

You are given the block as written (the whole system as JSON), the findings that must be fixed in it, the shape of its block and the evidence: every passage of this job's documents about this system, each starting with its source id in square brackets.

Fix each finding, and nothing else:
- Change only what a finding names: the device it names (by its id), or, for a finding about the whole block, what that finding says is wrong. Keep every other device exactly as it is, with the same id, words, verb, parties, quantity, refs, assumption and flag. Keep the clarification and the tech hours unless a finding is about them.
- A fix follows the finding's fix and the Playbook. When the evidence shows the finding is wrong, keep the line as it is and say so in that device's assumption (what and why), citing the evidence.
- A device you add needs refs from the evidence, like every device: source_id exactly as the evidence gives it, the exact quoted words, the place. Give it the next free id ("<system key>.d<n>"). A device you remove is gone from the answer.
- Copy key, name, shape, control, families, sequence_refs and alternate exactly as given.

Everything the writer's rules say still holds: every line cites this job's evidence; the shape is the frame, never the content; every line carries who furnishes, installs and wires; the higher count prints and an unknown count is null with flag "quantity"; every assumption says what and why; at most one clarification; plain words, no emoji.

Answer with the whole revised system as JSON in the schema given.
