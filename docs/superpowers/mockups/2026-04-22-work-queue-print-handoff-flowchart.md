# Work Queue Print Handoff Flowchart

```mermaid
flowchart TD
    A[User reviews files in File Analysis] --> B[Select Ready files]
    B --> C[Click Send to Print]
    C --> D[Show short success or mixed-result message]
    D --> E[Stay on Work Queue]
    E --> F[Move successful files into In Progress]
    F --> G[Show backend step in Status cell]

    G --> H{Handoff outcome}

    H -->|Success| I[Briefly show Queued in In Progress]
    I --> J[Create print job in Print Queue]
    J --> K{Screenshot ready}
    K -->|No| L[Show Generating preview placeholder]
    K -->|Yes| M[Show clickable thumbnail]
    L --> M
    I --> N[Move file rows to History]
    N --> O[History row shows linked Job ID]
    O --> P[Click Job ID]
    P --> Q[Switch to Print Queue and highlight matching job]

    H -->|Failure| R[Return file row to top of File Analysis]
    R --> S[Set Status to Needs Review with short reason]

    C -. If mixed result .-> T[Some rows move to In Progress, some return to File Analysis]
```

## Reading Guide

- `File Analysis` = needs user attention
- `In Progress` = system is handling the file, read-only
- `Print Queue` = real print jobs only
- `History` = completed file-level traceability

## Swimlane Version

```mermaid
flowchart LR
    subgraph U[User]
        U1[Review files in File Analysis]
        U2[Select Ready files]
        U3[Click Send to Print]
        U4[Stay on Work Queue]
        U5[Later click Job ID from History]
    end

    subgraph WQ[Work Queue]
        W1[Show short success or mixed-result message]
        W2[Move successful rows to In Progress]
        W3[Update Status cell with Processing / Importing / Layout / Validating]
        W4{Handoff result}
        W5[Briefly show Queued]
        W6[Move file rows to History]
        W7[Return failed rows to top of File Analysis]
        W8[Set failed rows to Needs Review]
        W9[History row shows linked Job ID]
    end

    subgraph PQ[Print Queue and History]
        P1[Create Print Queue job row]
        P2{Screenshot ready}
        P3[Show Generating preview placeholder]
        P4[Show clickable thumbnail]
        P5[Switch to Print Queue and highlight matching job]
    end

    U1 --> U2 --> U3 --> W1 --> U4
    W1 --> W2 --> W3 --> W4

    W4 -->|Success| W5 --> P1
    W5 --> W6 --> W9 --> U5 --> P5
    P1 --> P2
    P2 -->|No| P3
    P2 -->|Yes| P4
    P3 --> P4

    W4 -->|Failure| W7 --> W8
```

## Screen-State Version

```mermaid
flowchart LR
    A[Work Queue\nFile Analysis] -->|Send to Print| B[Work Queue\nIn Progress]
    B -->|Queued briefly| C[History]
    B -->|Create job| D[Print Queue]
    B -->|Failed| E[Work Queue\nFile Analysis\nNeeds Review at top]
    C -->|View Job| D
    D -->|Preview ready| F[Print Queue\nClickable thumbnail]
    D -->|Preview pending| G[Print Queue\nGenerating preview]
    G -->|Screenshot available| F
```
