# ADR 0002: Lap-Time Delta Sign Convention

## Status
Accepted

## Context
Motorsport analysis tools frequently confuse users by inverting the sign of $\Delta T$. Some software defines $\Delta T > 0$ as "ahead", while others define it as "slower" (higher elapsed time).

## Decision
Apex adopts a mathematically rigorous, unambiguous sign convention across all CLI commands, backend schemas, frontend charts, and report exports:

For any distance coordinate $s$, let $T_A(s)$ be the elapsed time from lap start for Lap A, and $T_B(s)$ be the elapsed time from lap start for Lap B:
$$\Delta T(s) = T_A(s) - T_B(s)$$

### Interpretation
- **$\Delta T(s) < 0$**: Lap A has spent **less elapsed time** than Lap B to reach distance $s$. Lap A is **faster / ahead**.
- **$\Delta T(s) > 0$**: Lap A has spent **more elapsed time** than Lap B to reach distance $s$. Lap A is **slower / behind**.
- **$\Delta T(s) = 0$**: Equal cumulative elapsed time.

### UI & Visualization Rule
Charts will display the label:
`Cumulative Time Delta: T_A(s) - T_B(s) [s] (Negative = Driver A faster)`
This convention is non-negotiable and invariant across all views.
