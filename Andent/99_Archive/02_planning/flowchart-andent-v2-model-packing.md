# Andent V2 Model Packing Flowchart

This flowchart shows how the system currently decides:
- which models can go into the same build
- when a case must be sent to manual review
- when a case joins an existing build or starts a new one

Primary source:
- `andent_planning.py` (`plan_andent_builds`)

```mermaid
flowchart TD
    A["Start with the classified STL files"] --> B["Group files by case ID"]
    B --> C{"Is the file unclear or missing a case ID?"}
    C -- Yes --> MR1["Send file to manual review"]
    C -- No --> D["Prepare one or more case groups"]

    D --> E{"Does the same case contain Splint and non-Splint models?"}
    E -- Yes --> E1["Split the case into two groups<br/>1. Splint only<br/>2. Everything else"]
    E -- No --> E2["Keep the whole case together as one group"]

    E1 --> F["Work out the workflow rules for each group"]
    E2 --> F
    F --> G{"Do the rules say this group needs manual review?"}
    G -- Yes --> MR2["Send case group to manual review"]
    G -- No --> H["Create a build candidate for this case group"]

    H --> I{"Does this case group exceed the allowed file limit for one build?"}
    I -- Yes --> MR3["Send case group to manual review<br/>too many files for one build"]
    I -- No --> J{"Do we know the size of every model?"}

    J -- No --> K["Keep it eligible, but only for limited packing options later"]
    J -- Yes --> L{"Does it look like the whole case group can fit on one build plate?"}
    L -- No --> MR4["Send case group to manual review<br/>it does not fit on one build"]
    L -- Yes --> M["Accept this case group for packing"]
    K --> M

    M --> N["Separate accepted groups by build type<br/>Ortho/Tooth and Splint"]
    N --> O["Try larger case groups first"]

    O --> P["Take the next case group"]
    P --> Q{"Is there another open build to try?"}

    Q --> R{"Is it the same build type?"}
    R -- No --> Q
    R -- Yes --> S{"Would the combined file count stay within the limit?"}
    S -- No --> RJ1["Do not add it to this build<br/>file limit would be exceeded"]
    RJ1 --> Q
    S -- Yes --> T{"Do both the build and the new case group have full size data?"}

    T -- No --> U{"Does this build already contain other cases?"}
    U -- Yes --> RJ2["Do not add it to this build<br/>not enough size data to merge safely"]
    RJ2 --> Q
    U -- No --> V["Allow it because this would be the first case in the build"]

    T -- Yes --> W{"Does the quick fit estimate say they still fit together?"}
    W -- Yes --> X["Add the case group to this build"]
    W -- No --> Y{"Is a deeper fit check available?"}
    Y -- No --> RJ3["Do not add it to this build<br/>quick fit estimate says no"]
    RJ3 --> Q
    Y -- Yes --> Z{"Does the deeper fit check approve the merge?"}
    Z -- No --> RJ4["Do not add it to this build<br/>deeper fit check says no"]
    RJ4 --> Q
    Z -- Yes --> X

    V --> X
    X --> X1["Update the build with the new case group"]
    X1 --> X2["If the build contains tooth models, mark it as needing supports"]
    X2 --> AA{"Are there more case groups in this build type?"}

    Q -- No --> AC["Start a new build with this case group"]
    AC --> AD["Keep notes on why it did not fit into earlier builds"]
    AD --> AA

    AA -- Yes --> P
    AA -- No --> AE{"Are there more build types to process?"}
    AE -- Yes --> O
    AE -- No --> AF["Return the build plan list and the manual review list"]

    MR1 --> AF
    MR2 --> AF
    MR3 --> AF
    MR4 --> AF
```

## Current behavior summary
- The planner works at the case-group level, not one model at a time.
- A mixed same-case `Splint + Ortho/Tooth` input is split into two groups before packing.
- All other compatible files from the same case stay together.
- If a whole case group cannot fit on one build, it goes to manual review instead of being split further.
- The planner uses a simple first-fit approach within each build type:
  - try larger case groups first
  - try existing builds one by one
  - if none work, start a new build
- `max_batch_size` is currently `10` files per build, not `10` cases.
- Missing model dimensions are only tolerated for a brand-new build; they block merging into a build that already has content.

## What determines "how many / what models go into a build" currently
- Workflow-family compatibility:
  - `Splint` never shares a build with `Ortho/Tooth`
  - `Ortho` and `Tooth` may share a build
- Hard file-count cap:
  - total files on a build cannot exceed `10`
- Build-plate fit heuristic:
  - combined model dimensions must pass the packing estimate
- Safe-merge rule for unknown dimensions:
  - unknown dimensions cannot be merged into an already non-empty build
- Case cohesion:
  - the planner packs whole case candidates, not partial cases

## What "packing heuristic" means
- A packing heuristic is a quick best-effort fit estimate.
- In this planner, it means the system uses model dimensions to estimate whether a set of models should fit on the build plate before doing any real scene creation.
- It is faster than a full placement simulation, but it is still an estimate, not a guarantee.
