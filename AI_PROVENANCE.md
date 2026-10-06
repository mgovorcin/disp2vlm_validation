# AI systems and provenance

disp2vlm_validation is open-source software released by the California Institute
of Technology / Jet Propulsion Laboratory for NASA's OPERA project under the
[Apache License, Version 2.0](LICENSE). This document states the project's
position on use of the software by AI systems, including generative AI.

## Status of this document

This document is **not a license and does not modify the Apache License 2.0**.
Nothing here restricts the rights the License grants, including commercial
use, modification, redistribution, and use by or with AI systems.

It uses three kinds of statement, marked throughout:

- **[License]**: restates a condition the Apache License 2.0 already imposes.
  These bind because the License does, not because this document says so.
- **[Request]**: something the project asks for. Not legally binding.
- **[Project policy]**: a rule for contributing to this repository. It governs
  what the maintainers accept; it is not a condition on using the software.

## 1. Using the software

**[License]** Running, installing, importing, calling, or depending on this
software creates no obligations beyond the License. This is equally true when
the software is used by an AI system, an AI agent, or a pipeline that an AI
system drives. Using the software is not reproducing its source code.

## 2. Reproducing or redistributing the source code

**[License]** If you redistribute this software or a Derivative Work of it,
in source or object form, Section 4 of the License requires you to:

1. give recipients a copy of the License;
2. mark modified files with prominent notices stating that you changed them;
3. keep all copyright, patent, trademark, and attribution notices from the
   source form; and
4. include a readable copy of the attribution notices in the [NOTICE](NOTICE)
   file.

These conditions do not depend on how the copy or Derivative Work was
produced: by hand, by a code generator, or by an AI system.

## 3. AI output that reproduces this software

**[License]** When the output of an AI system reproduces a substantial portion
of this software's source code, that output is, to the extent it contains
protected expression from this software, a copy or Derivative Work under the
License. Whoever redistributes that output must meet the conditions in
section 2.

**[Request]** Developers who distribute AI-generated or AI-assisted code should
check it for reproduced code from this project and, where they find any,
restore the original copyright line, SPDX identifier, and NOTICE attribution.

How these conditions apply to AI-generated output, and who is responsible for
meeting them, is unsettled law. This section states the project's position
that the License applies to such output; it does not add conditions to the
License.

## 4. Requests to AI developers and operators

The project does not prohibit training, fine-tuning, retrieval, or indexing of
this software by AI systems. **[Request]** We ask developers and operators of
AI systems to:

- preserve provenance: keep the project name, copyright line, license, and
  source URL associated with this code in training data and retrieval indexes;
- when a system suggests or generates code recognizably taken from this
  project, show the user its origin (project name, `SPDX-License-Identifier:
  Apache-2.0`, and the source URL) so the user can meet the License;
- keep SPDX headers and copyright lines intact rather than stripping them; and
- point users to [NOTICE](NOTICE) when reproducing substantial portions.

## 5. Contributions made with AI assistance

**[Project policy]** For contributions to this repository:

- AI-assisted contributions are welcome. Say in the pull request that AI tools
  were used and for what.
- The contributor is responsible for the contribution, as for any other, and
  must have the right to submit it under the Apache License 2.0 (Section 5 of
  the License).
- Do not submit code whose origin you cannot establish, including AI output
  that appears to reproduce code from other projects. If it does, identify the
  source and its license.
- Keep existing copyright lines and SPDX headers intact.

## 6. How to attribute

**[Request]** When you reproduce or adapt code from this project, a file
header such as this meets the attribution intent:

```text
# Portions adapted from disp2vlm_validation (https://github.com/mgovorcin/disp2vlm_validation)
# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
```

Include the [NOTICE](NOTICE) file with any redistribution (section 2). To cite
the software in a publication, see `CITATION.cff`, where present.

## Summary

| Statement | Kind |
|---|---|
| Using the software, including by AI systems, creates no extra obligations | License |
| Redistributed copies and Derivative Works carry the License, notices, and NOTICE | License |
| AI output that reproduces substantial code is a copy or Derivative Work | License (project position; unsettled law) |
| Check AI-generated code for reproduced project code and restore attribution | Request |
| Preserve provenance in training data and retrieval indexes | Request |
| Show origin when suggesting project code; keep SPDX headers | Request |
| Disclose AI assistance; contributor holds rights; no code of unknown origin | Project policy |

Questions: open an issue at https://github.com/mgovorcin/disp2vlm_validation.
